import json
import logging
import os
from decimal import Decimal

import boto3
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.serialization import load_der_public_key
from django.conf import settings
from eth_keys import keys
from eth_utils import keccak, to_checksum_address
from web3 import Web3
from web3.middleware import geth_poa_middleware
import rlp

SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

logger = logging.getLogger(__name__)

class KMSWeb3Signer:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(settings.ETHEREUM_RPC_URL))
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)        
        if not self.w3.is_connected():
            raise ConnectionError("Cannot connect to RPC")

        self.chain_id = int(settings.KYC_REWARD_CHAIN_ID)
        self.kms_key_id = settings.KYC_REWARD_KMS_KEY_ID
        self.kms_region = settings.KYC_REWARD_KMS_REGION

        # ── Create kms_client FIRST ──
        self.kms_client = boto3.client("kms", region_name=self.kms_region)
        

        self.sender_address = self._get_kms_signer_address()
        print(f"🔗 Connected to chain ID: {self.w3.eth.chain_id}")
        print(f"💰 Derived KMS wallet address: {self.sender_address}")
        if self.sender_address != "0xBfb33b5CC42C20De1dfc11CfdDa89C1CAd393e79":
            raise ValueError("Wrong KMS key! Expected funded address 0xBfb33b5..., got " + self.sender_address)

        if self.sender_address.lower() != "0xbfb33b5cc42c20de1dfc11cfdda89c1cad393e79":
            raise RuntimeError(
                f"CRITICAL: Using wrong KMS key! "
                f"Derived {self.sender_address} but expected funded 0xBfb33b5... "
                "Check KYC_REWARD_KMS_KEY_ID in .env"
            )

        env_sender = getattr(settings, 'KYC_REWARD_SENDER_ADDRESS', None)
        if env_sender and to_checksum_address(env_sender) != self.sender_address:
            print(f"Warning: Env KYC_REWARD_SENDER_ADDRESS {env_sender} does NOT match derived KMS address {self.sender_address}. Using derived address.")

        self.token_address = Web3.to_checksum_address(settings.TOKEN_CONTRACT_ADDRESS)
        token_abi_path = os.path.join(settings.BASE_DIR, 'subapps/smart_contract/gzc.json')
        with open(token_abi_path, 'r') as f:
            self.token_abi = json.load(f)
        self.token_contract = self.w3.eth.contract(address=self.token_address, abi=self.token_abi)

        balance_wei = self.token_contract.functions.balanceOf(self.sender_address).call()
        print(f"🏦 Derived KMS address token balance: {balance_wei / 10**18:.4f}")

        pol_balance = self.w3.eth.get_balance(self.sender_address)
        print(f"💵 Derived KMS address POL balance: {pol_balance / 1e18:.4f}")

    def _get_kms_signer_address(self) -> str:
        response = self.kms_client.get_public_key(KeyId=self.kms_key_id)
        public_key = load_der_public_key(response["PublicKey"])
        public_numbers = public_key.public_numbers()
        x = public_numbers.x.to_bytes(32, byteorder="big")
        y = public_numbers.y.to_bytes(32, byteorder="big")
        return self._pubkey_bytes_to_address(x + y)

    @staticmethod
    def _pubkey_bytes_to_address(pubkey_bytes: bytes) -> str:
        # Ethereum address is the last 20 bytes of keccak(uncompressed_pubkey)
        # where the uncompressed key is 0x04 || X || Y
        return to_checksum_address(keccak(b"\x04" + pubkey_bytes)[12:])

    def get_address(self) -> str:
        return self.sender_address

    def recover_v(self, tx_hash: bytes, r: int, s: int) -> int:
        for v in [0, 1]:
            try:
                signature = keys.Signature(vrs=(v, r, s))
                recovered_pubkey = signature.recover_public_key_from_msg_hash(tx_hash)
                recovered_addr = self._pubkey_bytes_to_address(recovered_pubkey.to_bytes())
                print(f"  Tried v={v}: recovered: {recovered_addr}")
                if recovered_addr == self.sender_address:
                    print(f"✅ Recovered correct address with v={v}")
                    return v
            except Exception as e:
                print(f"Recovery failed for v={v}: {e}")
        raise ValueError("Signature recovery failed—check KMS key, chain_id, or tx hash integrity")

    def sign_transaction(self, tx_dict: dict) -> bytes:
        if tx_dict.get('type') != 0x02:
            raise ValueError("Only EIP-1559 supported")

        tx = {
            'chainId': int(tx_dict['chainId']),
            'nonce': tx_dict['nonce'],                     # ← FIX: use from tx_dict
            'maxFeePerGas': tx_dict['maxFeePerGas'],       # ← FIX
            'maxPriorityFeePerGas': tx_dict['maxPriorityFeePerGas'],  # ← FIX
            'gas': int(tx_dict['gas']),
            'to': tx_dict.get('to'),
            'value': int(tx_dict.get('value', 0)),
            'data': tx_dict.get('data', '0x'),
            'accessList': tx_dict.get('accessList', []),
        }


        to_bytes = b'' if tx['to'] is None else bytes.fromhex(tx['to'][2:])
        data_bytes = b'' if tx['data'] == '0x' else bytes.fromhex(tx['data'][2:])
        
        unsigned_payload = [
            tx['chainId'], tx['nonce'], tx['maxPriorityFeePerGas'], tx['maxFeePerGas'],
            tx['gas'], to_bytes, tx['value'], data_bytes, tx['accessList']
        ]

        rlp_unsigned = rlp.encode(unsigned_payload)
        to_sign = b'\x02' + rlp_unsigned
        tx_hash = keccak(to_sign)
        print(f"📝 Tx hash: {tx_hash.hex()}")

        # KMS Sign
        response = self.kms_client.sign(
            KeyId=self.kms_key_id, 
            Message=tx_hash, 
            MessageType="DIGEST", 
            SigningAlgorithm="ECDSA_SHA_256"
        )
        
        r, s = decode_dss_signature(response['Signature'])
        if s > SECP256K1_N // 2:
            s = SECP256K1_N - s
            
        print(f"🔐 r={hex(r)}, s={hex(s)}")
        
        # Recover v dynamically
        v_final = self.recover_v(tx_hash, r, s)
        
        signed_payload = unsigned_payload + [v_final, r, s]
        rlp_signed = rlp.encode(signed_payload)
        raw_tx = b'\x02' + rlp_signed
        return raw_tx

class RewardDistributorService:
    def __init__(self):
        self.signer = KMSWeb3Signer()
        self.w3 = self.signer.w3
        self.reward_wallet_address = self.signer.get_address()
        self.distributor_address = Web3.to_checksum_address(settings.KYC_REWARD_DISTRIBUTOR_ADDRESS)
        print(f"🎯 Distributor contract: {self.distributor_address}")

        self._load_abis()
        self.chain_id = int(settings.KYC_REWARD_CHAIN_ID)

        self.distributor = self.w3.eth.contract(
            address=self.distributor_address,
            abi=self.distributor_abi
        )

    def _load_abis(self):
        base_dir = settings.BASE_DIR
        with open(os.path.join(base_dir, 'subapps/smart_contract/reward_distributor.json'), 'r') as f:
            self.distributor_abi = json.load(f)
        with open(os.path.join(base_dir, 'subapps/smart_contract/gzc.json'), 'r') as f:
            self.token_abi = json.load(f)

    def get_distributor_balance(self) -> int:
        token = self.w3.eth.contract(address=self.signer.token_address, abi=self.token_abi)
        balance = token.functions.balanceOf(self.distributor_address).call()
        print(f"🔢 Distributor token balance: {balance / 1e18:.4f}")
        return balance

    def _replace_nonce_zero(self):
        """Send a high-fee self-tx at nonce 0 to evict any stuck mempool tx."""
        print("⚙️  Replacing possible stuck nonce 0 with a zero-value self-transfer...")

        # Aggressive fees to outbid any lingering tx in the RPC mempool
        try:
            priority_fee = max(self.w3.eth.max_priority_fee, self.w3.to_wei(80, 'gwei'))
        except Exception:
            priority_fee = self.w3.to_wei(80, 'gwei')
        base_fee = self.w3.eth.get_block('latest')['baseFeePerGas']
        max_fee = max(base_fee * 2 + priority_fee, self.w3.to_wei(120, 'gwei'))

        cancel_tx = {
            'type': 0x02,
            'chainId': self.chain_id,
            'nonce': 0,
            'maxFeePerGas': int(max_fee),
            'maxPriorityFeePerGas': int(priority_fee),
            'gas': 25_000,
            'from': self.reward_wallet_address,
            'to': self.reward_wallet_address,
            'value': 0,
            'data': '0x',
            'accessList': [],
        }

        raw = self.signer.sign_transaction(cancel_tx)
        tx_hash = self.w3.eth.send_raw_transaction(raw)
        print(f"🚀 Sent cancel tx (nonce 0): {tx_hash.hex()}")
        print(f"     Explorer: https://amoy.polygonscan.com/tx/{tx_hash.hex()}")
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
        print(f"Cancel receipt status: {receipt.status}, gas used: {receipt.gasUsed}")
        if receipt.status != 1:
            raise RuntimeError("Nonce-0 replacement failed; cannot proceed with reward tx")

    def distribute_reward(self, recipient: str, amount_ether: float) -> dict:
        recipient = Web3.to_checksum_address(recipient)
        amount_wei = int(Decimal(amount_ether) * 10**18)
        print(f"→ Sending {amount_ether} tokens → {amount_wei} wei")

        # Proper nonce handling
        latest_nonce = self.w3.eth.get_transaction_count(self.reward_wallet_address, "latest")
        pending_nonce = self.w3.eth.get_transaction_count(self.reward_wallet_address, "pending")
        nonce = max(latest_nonce, pending_nonce)        
        print(f" RPC pending nonce: {pending_nonce} (latest: {latest_nonce}, using: {nonce})")

        # If RPC still thinks nonce 0 is occupied, proactively clear it
        if nonce == 0:
            try:
                self._replace_nonce_zero()
                # Refresh nonce after replacement is mined
                # latest_nonce = self.w3.eth.get_transaction_count(self.reward_wallet_address, "latest")
                pending_nonce = self.w3.eth.get_transaction_count(self.reward_wallet_address, "pending")
                # nonce = max(latest_nonce, pending_nonce)
                nonce = pending_nonce
                print(f" After cancel → latest: {latest_nonce}, pending: {pending_nonce}, using: {nonce}")
            except Exception as cancel_err:
                print(f" Cancel attempt failed: {cancel_err}")
                raise

        # No manual bump - trust the RPC unless proven otherwise

        # Simulate call to catch revert reason
        try:
            self.distributor.functions.distributeReward(recipient, amount_wei).call({
                'from': self.reward_wallet_address
            })
            print("Simulation OK - contract would accept the call")
        except Exception as sim_err:
            print(" Contract simulation revert:", str(sim_err))
            print("  → Most likely: missing DISTRIBUTOR_ROLE or wrong caller")
            raise  # Stop for debug

        matic_balance = self.w3.eth.get_balance(self.reward_wallet_address)
        print(f"REAL-TIME BALANCE BEFORE SEND: {matic_balance / 1e18:.6f} ETH")
        print(f"💵 POL for gas: {matic_balance / 1e18:.4f}")

        if matic_balance < self.w3.to_wei(0.01, 'ether'):
            raise ValueError("Too little base sepolia for gas - send more testnet base sepolia")

        # Gas prices - aggressive for testnet
        priority_fee = self.w3.eth.max_priority_fee
        base_fee = self.w3.eth.get_block('latest')['baseFeePerGas']
        max_fee = int((base_fee + priority_fee) * 1.5)  # Safer multiplier

        print(f" Max fee: {max_fee / 1e9:.2f} gwei | Priority: {priority_fee / 1e9:.2f} gwei")

        # Build tx for estimation (without gas)
        tx_for_est = {
            'type': 0x02,
            'chainId': self.chain_id,
            'nonce': nonce,
            'maxFeePerGas': max_fee,
            'maxPriorityFeePerGas': priority_fee,
            'from': self.reward_wallet_address,
            'to': self.distributor_address,
            'value': 0,
            'data': self.distributor.encodeABI(fn_name='distributeReward', args=[recipient, amount_wei]),
            'accessList': [],
        }

        # tx_for_est = {
        #     'type': 0x02,
        #     'chainId': self.chain_id,
        #     'nonce': nonce,
        #     'maxFeePerGas': max_fee,
        #     'maxPriorityFeePerGas': priority_fee,
        #     'gas': 21000,
        #     'to': self.reward_wallet_address,
        #     'value': self.w3.to_wei(0.0001, 'ether'),
        #     'data': '0x',
        #     'accessList': [],
        # }

        # Estimate gas safely
        try:
            gas_est = self.w3.eth.estimate_gas(tx_for_est)
            gas_limit = int(gas_est * 1.3)
            print(f"   Final gas limit: {gas_limit} (est: {gas_est})")
        except Exception as e:
            print(f"Estimation failed: {e} - using fallback 200k")
            gas_limit = 200_000

        # Final tx with gas
        tx = {**tx_for_est, 'gas': gas_limit}

        def _send_once(tx_obj):
            raw = self.signer.sign_transaction(tx_obj)
            return self.w3.eth.send_raw_transaction(raw)

        try:
            tx_hash = _send_once(tx)
        except Exception as send_err:
            msg = str(send_err)
            if 'nonce too low' in msg.lower():
                fresh_pending = self.w3.eth.get_transaction_count(self.reward_wallet_address, "pending")
                bumped_nonce = max(tx['nonce'] + 1, fresh_pending)
                bumped = {**tx, 'nonce': bumped_nonce}
                print(f"Nonce too low – retrying once with nonce={bumped_nonce} (fresh pending={fresh_pending})")
                tx_hash = _send_once(bumped)
                tx = bumped
            else:
                print(f"Send failed: {msg}")
                raise

        print(f" Tx sent: {tx_hash.hex()}")
        print(f" https://amoy.polygonscan.com/tx/{tx_hash.hex()}")

        # Wait
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
        print(f"Receipt status: {receipt.status} | Gas used: {receipt.gasUsed}")

        if receipt.status == 1:
            print(" SUCCESS!")
        else:
            print(" Reverted - check explorer + simulation error above")

        return receipt


