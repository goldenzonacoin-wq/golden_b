import boto3
from cryptography.hazmat.primitives.serialization import load_der_public_key
from eth_utils import keccak, to_checksum_address
from django.conf import settings  

KMS_KEY_ID = "e88e950-32f0-48b9-9574-8df48ae8df48ae8db68"       
KMS_REGION = "us-east-1"                      

kms_client = boto3.client("kms", region_name=KMS_REGION)

def get_kms_signer_address():
    response = kms_client.get_public_key(KeyId=KMS_KEY_ID)
    public_key = load_der_public_key(response["PublicKey"])
    public_numbers = public_key.public_numbers()
    x = public_numbers.x.to_bytes(32, byteorder="big")
    y = public_numbers.y.to_bytes(32, byteorder="big")
    uncompressed = b"\x04" + x + y
    address = to_checksum_address(keccak(uncompressed)[-20:])
    return address

if __name__ == "__main__":
    try:
        derived_address = get_kms_signer_address()
        print(f"Derived Ethereum address from KMS key:")
        print(f"→ {derived_address}")
        print(f"→ Should match your reward wallet: 0xBCB1E2AF36013e8957D4D966df39875e85Ce4b2d")
    except Exception as e:
        print("Error:", str(e))