import json
import logging
import os
from decimal import Decimal

import boto3
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.serialization import load_der_public_key
from django.conf import settings
from eth_account._utils.legacy_transactions import serializable_unsigned_transaction_from_dict
from eth_keys import constants, keys
from eth_utils import keccak, to_checksum_address
from web3 import Web3

logger = logging.getLogger(__name__)


class KMSWeb3Signer:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(settings.ETHEREUM_RPC_URL))
        if not self.w3.is_connected():
            raise ConnectionError("Cannot connect to RPC")

        self.chain_id = int(settings.KYC_REWARD_CHAIN_ID)
        self.kms_key_id = settings.KYC_REWARD_KMS_KEY_ID
        self.kms_region = settings.KYC_REWARD_KMS_REGION
        self.sender_address = to_checksum_address(settings.KYC_REWARD_SENDER_ADDRESS)

        self.kms_client = boto3.client("kms", region_name=self.kms_region)

        kms_addr = self._get_kms_signer_address()
        if kms_addr != self.sender_address:
            raise ValueError(
                f"KMS key controls {kms_addr}, but expected reward wallet is {self.sender_address}"
            )

        logger.info(f"KMS signer initialized for address: {self.sender_address}")

    def _get_kms_signer_address(self) -> str:
        """Derive Ethereum address from KMS public key"""
        response = self.kms_client.get_public_key(KeyId=self.kms_key_id)
        public_key = load_der_public_key(response["PublicKey"])
        public_numbers = public_key.public_numbers()
        x = public_numbers.x.to_bytes(32, byteorder="big")
        y = public_numbers.y.to_bytes(32, byteorder="big")
        uncompressed = b"\x04" + x + y
        return to_checksum_address(keccak(uncompressed)[-20:])

    def get_address(self) -> str:
        """Public method to get the controlled address"""
        return self.sender_address

    def _sign_digest(self, digest: bytes):
        response = self.kms_client.sign(
            KeyId=self.kms_key_id,
            Message=digest,
            MessageType="DIGEST",
            SigningAlgorithm="ECDSA_SHA_256",
        )
        r, s = decode_dss_signature(response["Signature"])
        if s > constants.SECPK1_N // 2:
            s = constants.SECPK1_N - s
        return r, s

    def _resolve_recovery_id(self, digest: bytes, r: int, s: int) -> int:
        for recovery_id in (0, 1):
            signature = keys.Signature(vrs=(recovery_id, r, s))
            recovered = signature.recover_public_key_from_msg_hash(digest)
            if recovered.to_checksum_address() == self._kms_address:
                return recovery_id
        raise ValueError("Unable to recover signer address from signature")

    def sign_transaction(self, tx_dict: dict) -> bytes:
        unsigned_tx = serializable_unsigned_transaction_from_dict(tx_dict)
        tx_hash = keccak(unsigned_tx.encode())
        r, s = self._sign_digest(tx_hash)
        recovery_id = self._resolve_recovery_id(tx_hash, r, s)
        v = recovery_id + self.chain_id * 2 + 35
        signed_tx = unsigned_tx.as_signed_transaction(v=v, r=r, s=s)
        return signed_tx.rawTransaction

    def sign_and_send(self, tx_dict: dict) -> str:
        raw_tx = self.sign_transaction(tx_dict)
        tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
        return tx_hash.hex()

    def build_transfer_tx(self, to_address: str, amount: Decimal) -> dict:
        amount_wei = int(amount * (10 ** self.token_decimals))
        return self.contract.functions.transfer(
            to_checksum_address(to_address), amount_wei
        ).build_transaction(
            {
                "from": self.sender_address,
                "gas": self.gas_limit,
                "gasPrice": self.w3.eth.gas_price,
                "nonce": self.w3.eth.get_transaction_count(self.sender_address, "pending"),
                "chainId": self.chain_id,
            }
        )

    def send_token_transfer(self, to_address: str, amount: Decimal) -> str:
        tx_dict = self.build_transfer_tx(to_address, amount)
        return self.sign_and_send(tx_dict)

        

class RewardDistributorService:
    """Business logic for reward distribution using KMS signer"""

    def __init__(self):
        self.signer = KMSWeb3Signer()  
        self.w3 = self.signer.w3
        self.reward_wallet_address = self.signer.get_address()

        self.distributor_address = Web3.to_checksum_address(settings.REWARD_DISTRIBUTOR_ADDRESS)
        self.token_address = Web3.to_checksum_address(settings.TOKEN_CONTRACT_ADDRESS)

        self._load_abis()

        self.distributor = self.w3.eth.contract(
            address=self.distributor_address,
            abi=self.distributor_abi
        )

    def _load_abis(self):
        base_dir = settings.BASE_DIR
        with open(os.path.join(base_dir, 'abis/reward_distributor.json'), 'r') as f:
            self.distributor_abi = json.load(f)
        with open(os.path.join(base_dir, 'abis/gzc_token.json'), 'r') as f:
            self.token_abi = json.load(f)

    def get_distributor_balance(self) -> int:
        token = self.w3.eth.contract(address=self.token_address, abi=self.token_abi)
        return token.functions.balanceOf(self.distributor_address).call()

    def distribute_reward(self, recipient: str, amount_ether: float | int | Decimal) -> dict:
        recipient = Web3.to_checksum_address(recipient)
        amount_wei = int(Decimal(str(amount_ether)) * 10**18)

        if amount_wei <= 0:
            raise ValueError("Amount must be > 0")

        balance = self.get_distributor_balance()
        if balance < amount_wei:
            raise ValueError(f"Insufficient distributor balance: {balance / 1e18:.4f} < {amount_ether}")

        nonce = self.w3.eth.get_transaction_count(self.reward_wallet_address, "pending")

        tx = self.distributor.functions.distributeReward(recipient, amount_wei).build_transaction({
            'type': '0x2',
            'from': self.reward_wallet_address,
            'nonce': nonce,
            'maxFeePerGas': self.w3.eth.max_priority_fee + (self.w3.eth.get_block('latest')['baseFeePerGas'] * 110 // 100),
            'maxPriorityFeePerGas': self.w3.eth.max_priority_fee,
            'chainId': self.w3.eth.chain_id,
        })

        gas_est = self.w3.eth.estimate_gas(tx)
        tx['gas'] = int(gas_est * 1.15)

        # Sign & send using KMS
        try:
            raw_signed = self.signer.sign_transaction(tx) 
            tx_hash = self.w3.eth.send_raw_transaction(raw_signed)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=240)

            logger.info(f"Reward distributed: {amount_ether} to {recipient} - tx: {tx_hash.hex()}")

            return {
                "status": "success",
                "tx_hash": tx_hash.hex(),
                "block_number": receipt.blockNumber,
                "gas_used": receipt.gasUsed,
                "recipient": recipient,
                "amount_ether": float(amount_ether),
            }

        except Exception as e:
            logger.error(f"Distribution failed: {str(e)}", exc_info=True)
            raise

    def distribute_token(self, recipient: str, amount_ether: float | int | Decimal) -> dict:
        recipient = Web3.to_checksum_address(recipient)
        amount_wei = int(Decimal(str(amount_ether)) * 10**18)

        if amount_wei <= 0:
            raise ValueError("Amount must be > 0")

        balance = self.get_distributor_balance()
        if balance < amount_wei:
            raise ValueError(f"Insufficient distributor balance: {balance / 1e18:.4f} < {amount_ether}")

        nonce = self.w3.eth.get_transaction_count(self.reward_wallet_address, "pending")

        tx = self.distributor.functions.distributeReward(recipient, amount_wei).build_transaction({
            'type': '0x2',
            'from': self.reward_wallet_address,
            'nonce': nonce,
            'maxFeePerGas': self.w3.eth.max_priority_fee + (self.w3.eth.get_block('latest')['baseFeePerGas'] * 110 // 100),
            'maxPriorityFeePerGas': self.w3.eth.max_priority_fee,
            'chainId': self.w3.eth.chain_id,
        })

        gas_est = self.w3.eth.estimate_gas(tx)
        tx['gas'] = int(gas_est * 1.15)

        # Sign & send using KMS
        try:
            raw_signed = self.signer.sign_transaction(tx) 
            tx_hash = self.w3.eth.send_raw_transaction(raw_signed)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=240)

            logger.info(f"Reward distributed: {amount_ether} to {recipient} - tx: {tx_hash.hex()}")

            return {
                "status": "success",
                "tx_hash": tx_hash.hex(),
                "block_number": receipt.blockNumber,
                "gas_used": receipt.gasUsed,
                "recipient": recipient,
                "amount_ether": float(amount_ether),
            }

        except Exception as e:
            logger.error(f"Distribution failed: {str(e)}", exc_info=True)
            raise