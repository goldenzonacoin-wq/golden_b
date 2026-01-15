import boto3
from web3 import Web3
from eth_account import Account
from eth_account._utils.legacy_transactions import serializable_unsigned_transaction_from_dict
from decimal import Decimal
from django.conf import settings
try:
    from web3.middleware.proof_of_authority import ExtraDataToPOAMiddleware
except ImportError:
    try:
        from web3.middleware import geth_poa_middleware
    except ImportError:
        from web3.middleware.geth_poa import geth_poa_middleware
        ExtraDataToPOAMiddleware = None
    else:
        ExtraDataToPOAMiddleware = None
import rlp
from eth_utils import to_bytes
import logging
import os
import json


logger = logging.getLogger(__name__)


class KmsTokenTransfer:
    """Service for transferring ATC tokens using KMS signing"""
    
    def __init__(self):
        # Web3 setup
        self.w3 = Web3(Web3.HTTPProvider(settings.ETHEREUM_RPC_URL))
        # Add POA middleware for chains with Proof of Authority
        if ExtraDataToPOAMiddleware:
            self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        else:
            self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        if not self.w3.is_connected():
            raise ConnectionError("Cannot connect to Ethereum RPC")
        
        self.kms = boto3.client(
            'kms',
            region_name=settings.KYC_REWARD_KMS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )
        
        self.kms_key_id = settings.KYC_REWARD_KMS_KEY_ID
        self.kms_wallet = Web3.to_checksum_address(settings.KYC_REWARD_SENDER_ADDRESS)
        self.chain_id = int(settings.KYC_REWARD_CHAIN_ID)
        
        self.token_address = Web3.to_checksum_address(settings.TOKEN_CONTRACT_ADDRESS)
        
        abi_path = os.path.join(settings.BASE_DIR, "subapps", "data", "atc_token.json")

        try:
            with open(abi_path, "r", encoding="utf-8") as abi_file:
                token_data = json.load(abi_file)
        except Exception as exc:
            logger.error(f"Failed to load token ABI from {abi_path}: {exc}")
            raise

        if isinstance(token_data, dict) and "abi" in token_data:
            self.token_abi = token_data["abi"]
        elif isinstance(token_data, list):
            self.token_abi = token_data
        else:
            raise ValueError(f"Invalid token ABI format in {abi_path}")
        
        self.token_contract = self.w3.eth.contract(
            address=self.token_address,
            abi=self.token_abi
        )
        
        logger.info(f"TokenTransferService initialized")
        logger.info(f"KMS Wallet: {self.kms_wallet}")
        logger.info(f"Chain ID: {self.chain_id}")
        logger.info(f"Token: {self.token_address}")
    
    def _sign_with_kms(self, message_hash):
        """Sign a message hash with KMS and recover the correct v value"""
        logger.debug(f"Signing with KMS: {message_hash.hex()[:20]}...")
        
        response = self.kms.sign(
            KeyId=self.kms_key_id,
            Message=message_hash,
            MessageType='DIGEST',
            SigningAlgorithm='ECDSA_SHA_256'
        )
        
        sig = response['Signature']
        logger.debug(f"Received KMS signature: {len(sig)} bytes")
        
        # Parse DER signature
        if sig[0] != 0x30:
            raise ValueError("Invalid DER signature format")
        
        # Extract r
        r_offset = 4
        r_length = sig[3]
        r_bytes = sig[r_offset:r_offset + r_length]
        r = int.from_bytes(r_bytes, 'big')
        
        # Extract s
        s_offset = r_offset + r_length + 2
        s_length = sig[s_offset - 1]
        s_bytes = sig[s_offset:s_offset + s_length]
        s = int.from_bytes(s_bytes, 'big')
        
        # Normalize s to low value (BIP-62)
        secp256k1_n = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
        if s > secp256k1_n // 2:
            s = secp256k1_n - s
            logger.debug(f"Normalized s value")
        
        # Try recovery with EIP-155 format
        for recovery_id in [1, 0]:  # Try 1 first (works for this KMS key)
            v_eip155 = recovery_id + 35 + (self.chain_id * 2)
            
            try:
                recovered = Account._recover_hash(message_hash, vrs=(v_eip155, r, s))
                if recovered.lower() == self.kms_wallet.lower():
                    logger.debug(f"Signature verified with v={v_eip155}")
                    return (v_eip155, r, s)
            except Exception:
                pass
        
        # Try legacy format
        for v_legacy in [27, 28]:
            try:
                recovered = Account._recover_hash(message_hash, vrs=(v_legacy, r, s))
                if recovered.lower() == self.kms_wallet.lower():
                    logger.debug(f"Signature verified with v={v_legacy} (legacy)")
                    return (v_legacy, r, s)
            except Exception:
                pass
        
        raise ValueError("Signature recovery failed for all v values")
    
    def get_balance(self, address=None):
        """Get token balance for an address (defaults to KMS wallet)"""
        if address is None:
            address = self.kms_wallet
        else:
            address = Web3.to_checksum_address(address)
        
        try:
            balance_wei = self.token_contract.functions.balanceOf(address).call()
            balance_tokens = Decimal(balance_wei) / Decimal(10**18)
            logger.info(f"Balance for {address}: {balance_tokens} tokens")
            return balance_tokens
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            raise
    
    def get_eth_balance(self, address=None):
        """Get ETH/native token balance"""
        if address is None:
            address = self.kms_wallet
        else:
            address = Web3.to_checksum_address(address)
        
        balance_wei = self.w3.eth.get_balance(address)
        balance_eth = Decimal(balance_wei) / Decimal(10**18)
        return balance_eth
    
    def transfer_tokens(self, recipient, amount_tokens, purpose="transfer"):
        """
        Transfer tokens from KMS wallet to recipient
        
        Args:
            recipient: Recipient Ethereum address
            amount_tokens: Amount of tokens to send (not wei)
            purpose: Description of the transfer
            
        Returns:
            dict: Transaction receipt with tx_hash, status, gas_used, block_number
        """
        logger.info(f"{'='*60}")
        logger.info(f"Transfer: {amount_tokens} tokens to {recipient}")
        logger.info(f"Purpose: {purpose}")
        logger.info(f"{'='*60}")
        
        try:
            recipient = Web3.to_checksum_address(recipient)
            
            # Check balance
            balance = self.get_balance()
            logger.info(f"KMS wallet balance: {balance} tokens")
            
            if balance < amount_tokens:
                raise ValueError(f"Insufficient balance. Have: {balance}, Need: {amount_tokens}")
            
            # Prepare transaction
            amount_wei = int(Decimal(amount_tokens) * Decimal(10**18))
            nonce = self.w3.eth.get_transaction_count(self.kms_wallet)
            gas_price = self.w3.eth.gas_price
            
            tx = {
                'nonce': nonce,
                'to': self.token_address,
                'value': 0,
                'gas': 100000,
                'gasPrice': gas_price,
                'data': self.token_contract.functions.transfer(recipient, amount_wei).build_transaction({'from': self.kms_wallet})['data'],
                'chainId': self.chain_id
            }
            
            logger.info(f"Nonce: {nonce}, Chain: {self.chain_id}")
            logger.info(f"Gas: {tx['gas']}, Price: {self.w3.from_wei(gas_price, 'gwei'):.6f} gwei")
            
            unsigned_tx = serializable_unsigned_transaction_from_dict(tx)
            tx_hash = unsigned_tx.hash()
            
            logger.info(f"Transaction hash: {tx_hash.hex()}")
            
            # Sign with KMS
            logger.info("Signing with KMS...")
            v, r, s = self._sign_with_kms(tx_hash)
            
            # Encode signed transaction
            tx_fields = [
                tx['nonce'],
                tx['gasPrice'],
                tx['gas'],
                to_bytes(hexstr=tx['to']),
                tx['value'],
                to_bytes(hexstr=tx['data'].hex()) if isinstance(tx['data'], bytes) else to_bytes(hexstr=tx['data']),
                v, r, s
            ]
            
            signed_tx_bytes = rlp.encode(tx_fields)
            
            # Verify signature
            sender_from_tx = Account.recover_transaction(signed_tx_bytes)
            logger.info(f"Verified sender: {sender_from_tx}")
            
            if sender_from_tx.lower() != self.kms_wallet.lower():
                raise ValueError(f"Signature verification failed! Expected: {self.kms_wallet}, Got: {sender_from_tx}")
            
            # Broadcast transaction
            logger.info("Broadcasting transaction...")
            tx_hash_result = self.w3.eth.send_raw_transaction(signed_tx_bytes)
            logger.info(f"TX broadcast: {tx_hash_result.hex()}")
            
            # Wait for confirmation
            logger.info("Waiting for confirmation...")
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash_result, timeout=120)
            
            result = {
                'tx_hash': tx_hash_result.hex(),
                'status': receipt['status'],
                'gas_used': receipt['gasUsed'],
                'block_number': receipt['blockNumber'],
                'recipient': recipient,
                'amount': amount_tokens,
                'explorer_url': self._get_explorer_url(tx_hash_result.hex())
            }
            
            if receipt['status'] == 1:
                logger.info(f"✅ SUCCESS! Gas used: {receipt['gasUsed']}")
                logger.info(f"Explorer: {result['explorer_url']}")
            else:
                logger.error(f"❌ Transaction FAILED!")
            
            return result
            
        except Exception as e:
            logger.error(f"Transfer failed: {e}", exc_info=True)
            raise
    
    def _get_explorer_url(self, tx_hash):
        """Get block explorer URL for transaction"""
        if self.chain_id == 80002:
            return f"https://amoy.polygonscan.com/tx/{tx_hash}"
        elif self.chain_id == 84532:
            return f"https://sepolia.basescan.org/tx/{tx_hash}"
        else:
            return f"Chain {self.chain_id} - TX: {tx_hash}"
    
    def discover_kms_address(self):
        """
        Discover which address the KMS key controls
        Returns the address that KMS can sign for
        """
        logger.info("Discovering KMS wallet address...")
        
        dummy_tx = {
            'nonce': 0,
            'to': '0x0000000000000000000000000000000000000000',
            'value': 0,
            'gas': 21000,
            'gasPrice': 1000000000,
            'data': b'',
            'chainId': self.chain_id
        }
        
        unsigned_tx = serializable_unsigned_transaction_from_dict(dummy_tx)
        tx_hash = unsigned_tx.hash()
        
        v, r, s = self._sign_with_kms(tx_hash)
        recovered = Account._recover_hash(tx_hash, vrs=(v, r, s))
        
        balance_wei = self.token_contract.functions.balanceOf(recovered).call()
        balance = Decimal(balance_wei) / Decimal(10**18)
        
        logger.info(f"✅ KMS controls address: {recovered}")
        logger.info(f"Balance: {balance} tokens")
        
        return {
            'address': recovered,
            'balance': balance,
            'matches_config': recovered.lower() == self.kms_wallet.lower()
        }
