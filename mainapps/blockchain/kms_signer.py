import json
import logging
import os
from decimal import Decimal

import boto3
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.serialization import load_der_public_key
from django.conf import settings
from eth_account._utils.legacy_transactions import (
    serializable_unsigned_transaction_from_dict,
)
from eth_keys import constants, keys
from eth_utils import keccak, to_checksum_address
from web3 import Web3

logger = logging.getLogger(__name__)


class KMSWeb3Signer:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(settings.ETHEREUM_RPC_URL))
        self.chain_id = int(settings.KYC_REWARD_CHAIN_ID)
        self.gas_limit = int(settings.KYC_REWARD_GAS_LIMIT)
        self.kms_key_id = settings.KYC_REWARD_KMS_KEY_ID
        self.kms_region = settings.KYC_REWARD_KMS_REGION
        self.sender_address = to_checksum_address(settings.KYC_REWARD_SENDER_ADDRESS)
        self.token_contract_address = to_checksum_address(settings.KYC_REWARD_TOKEN_CONTRACT_ADDRESS)
        self.token_decimals = int(settings.KYC_REWARD_TOKEN_DECIMALS)
        self.kms_client = boto3.client("kms", region_name=self.kms_region)
        self._kms_address = self._get_kms_signer_address()
        if self._kms_address != self.sender_address:
            raise ValueError("KMS key does not match reward sender address")

        self.contract = self._load_token_contract()

    def _load_token_contract(self):
        abi_path = os.path.join(settings.BASE_DIR, "subapps", "data", "atc_token.json")
        with open(abi_path, "r") as handle:
            contract_data = json.load(handle)
        return self.w3.eth.contract(address=self.token_contract_address, abi=contract_data["abi"])

    def _get_kms_signer_address(self):
        response = self.kms_client.get_public_key(KeyId=self.kms_key_id)
        public_key = load_der_public_key(response["PublicKey"])
        public_numbers = public_key.public_numbers()
        x = public_numbers.x.to_bytes(32, byteorder="big")
        y = public_numbers.y.to_bytes(32, byteorder="big")
        uncompressed = b"\x04" + x + y
        return to_checksum_address(keccak(uncompressed)[-20:])

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
