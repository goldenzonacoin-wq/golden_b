from django.core.management.base import BaseCommand
import boto3
from cryptography.hazmat.primitives.serialization import load_der_public_key
from eth_utils import keccak, to_checksum_address
from eth_keys import keys
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from django.conf import settings

SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


class Command(BaseCommand):
    help = 'Verify KMS key address and test signing'

    def handle(self, *args, **options):
        self.stdout.write("=" * 80)
        self.stdout.write("KMS ADDRESS VERIFICATION")
        self.stdout.write("=" * 80)

        # Your settings
        kms_key_id = settings.KYC_REWARD_KMS_KEY_ID
        kms_region = settings.KYC_REWARD_KMS_REGION
        expected_address = settings.KYC_REWARD_SENDER_ADDRESS

        self.stdout.write(f"\n📋 Configuration:")
        self.stdout.write(f"   KMS Key ID: {kms_key_id}")
        self.stdout.write(f"   KMS Region: {kms_region}")
        self.stdout.write(f"   Expected Address: {expected_address}")

        # Connect to KMS
        kms_client = boto3.client("kms", region_name=kms_region)

        # Get public key
        self.stdout.write(f"\n🔑 Fetching KMS public key...")
        response = kms_client.get_public_key(KeyId=kms_key_id)
        public_key = load_der_public_key(response["PublicKey"])
        public_numbers = public_key.public_numbers()

        x = public_numbers.x.to_bytes(32, byteorder="big")
        y = public_numbers.y.to_bytes(32, byteorder="big")

        self.stdout.write(f"   Public key X: {x.hex()}")
        self.stdout.write(f"   Public key Y: {y.hex()}")

        # Derive Ethereum address
        uncompressed = b"\x04" + x + y
        hash1 = keccak(uncompressed)
        actual_kms_address = to_checksum_address(hash1[-20:])

        self.stdout.write(f"\n🔍 Address Derivation:")
        self.stdout.write(f"   Uncompressed pubkey: 04{x.hex()}{y.hex()}")
        self.stdout.write(f"   Keccak256 hash: {hash1.hex()}")
        self.stdout.write(f"   Ethereum Address: {actual_kms_address}")

        # Final comparison
        self.stdout.write(f"\n" + "=" * 80)
        self.stdout.write(f"RESULT:")
        self.stdout.write(f"=" * 80)
        self.stdout.write(f"KMS Key Controls:  {actual_kms_address}")
        self.stdout.write(f"Expected Address:  {expected_address}")
        
        if actual_kms_address.lower() == expected_address.lower():
            self.stdout.write(self.style.SUCCESS(f"\n✅ ADDRESSES MATCH - Configuration is correct!"))
        else:
            self.stdout.write(self.style.ERROR(f"\n❌ ADDRESS MISMATCH!"))
            self.stdout.write(f"\n⚠️  ACTION REQUIRED:")
            self.stdout.write(f"   Your KMS key controls: {actual_kms_address}")
            self.stdout.write(f"   But settings expect:   {expected_address}")
            self.stdout.write(f"\n   You need to either:")
            self.stdout.write(f"   1. Update KYC_REWARD_SENDER_ADDRESS to {actual_kms_address}")
            self.stdout.write(f"   2. Fund the KMS-controlled address: {actual_kms_address}")
            self.stdout.write(f"   3. Use a different KMS key")

        # Test signature
        self.stdout.write(f"\n" + "=" * 80)
        self.stdout.write(f"SIGNATURE TEST")
        self.stdout.write(f"=" * 80)

        test_message = b"Hello Ethereum!"
        test_hash = keccak(test_message)
        self.stdout.write(f"Test message: {test_message.decode()}")
        self.stdout.write(f"Test hash: {test_hash.hex()}")

        # Test DIGEST mode
        self.stdout.write(f"\n🔐 Test 1: DIGEST mode (KMS applies SHA256)")
        try:
            sign_response = kms_client.sign(
                KeyId=kms_key_id,
                Message=test_hash,
                MessageType="DIGEST",
                SigningAlgorithm="ECDSA_SHA_256",
            )
            
            r, s = decode_dss_signature(sign_response['Signature'])
            if s > SECP256K1_N // 2:
                s = SECP256K1_N - s
            
            self.stdout.write(f"   Signature r: {hex(r)[:20]}...")
            self.stdout.write(f"   Signature s: {hex(s)[:20]}...")
            
            # Try recovery against keccak256 hash
            self.stdout.write(f"\n   Recovery against keccak256(message):")
            digest_works = False
            for v in [0, 1]:
                try:
                    sig = keys.Signature(vrs=(v, r, s))
                    recovered = sig.recover_public_key_from_msg_hash(test_hash)
                    recovered_addr = recovered.to_checksum_address()
                    
                    if recovered_addr == actual_kms_address:
                        self.stdout.write(self.style.SUCCESS(f"   v={v}: {recovered_addr} ✅ MATCHES!"))
                        digest_works = True
                    else:
                        self.stdout.write(f"   v={v}: {recovered_addr}")
                except Exception as e:
                    self.stdout.write(f"   v={v}: Failed - {e}")
            
            if not digest_works:
                self.stdout.write(self.style.WARNING(f"   ❌ DIGEST mode doesn't work for Ethereum"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ DIGEST mode failed: {e}"))

        # Test MESSAGE mode
        self.stdout.write(f"\n🔐 Test 2: MESSAGE mode (no additional hashing)")
        try:
            sign_response = kms_client.sign(
                KeyId=kms_key_id,
                Message=test_hash,
                MessageType="MESSAGE",
                SigningAlgorithm="ECDSA_SHA_256",
            )
            
            r, s = decode_dss_signature(sign_response['Signature'])
            if s > SECP256K1_N // 2:
                s = SECP256K1_N - s
            
            self.stdout.write(f"   Signature r: {hex(r)[:20]}...")
            self.stdout.write(f"   Signature s: {hex(s)[:20]}...")
            
            # Try recovery
            self.stdout.write(f"\n   Recovery against keccak256(message):")
            message_works = False
            for v in [0, 1]:
                try:
                    sig = keys.Signature(vrs=(v, r, s))
                    recovered = sig.recover_public_key_from_msg_hash(test_hash)
                    recovered_addr = recovered.to_checksum_address()
                    
                    if recovered_addr == actual_kms_address:
                        self.stdout.write(self.style.SUCCESS(f"   v={v}: {recovered_addr} ✅ MATCHES! USE MESSAGE MODE"))
                        message_works = True
                    else:
                        self.stdout.write(f"   v={v}: {recovered_addr}")
                except Exception as e:
                    self.stdout.write(f"   v={v}: Failed - {e}")
            
            if message_works:
                self.stdout.write(self.style.SUCCESS(f"\n✅ MESSAGE mode works! Update your code to use MessageType='MESSAGE'"))
            
        except Exception as e:
            self.stdout.write(f"   ⚠️ MESSAGE mode not supported: {e}")

        self.stdout.write(f"\n" + "=" * 80)