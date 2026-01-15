from django.core.management.base import BaseCommand
import boto3
from cryptography.hazmat.primitives.serialization import load_der_public_key
from eth_utils import keccak, to_checksum_address
from web3 import Web3
from django.conf import settings


class Command(BaseCommand):
    help = 'Setup and verify KMS wallet configuration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--check-balance',
            action='store_true',
            help='Check current balances'
        )
        parser.add_argument(
            '--derive-only',
            action='store_true',
            help='Only derive address, don\'t check balances'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('='*70))
        self.stdout.write(self.style.SUCCESS('🔐 KMS WALLET SETUP'))
        self.stdout.write(self.style.SUCCESS('='*70))
        
        try:
            # Derive address from KMS
            kms = boto3.client(
                'kms',
                region_name=settings.KYC_REWARD_KMS_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
            )
            
            response = kms.get_public_key(KeyId=settings.KYC_REWARD_KMS_KEY_ID)
            public_key = load_der_public_key(response["PublicKey"])
            public_numbers = public_key.public_numbers()
            
            x = public_numbers.x.to_bytes(32, byteorder="big")
            y = public_numbers.y.to_bytes(32, byteorder="big")
            
            derived_address = to_checksum_address(keccak(x + y)[-20:])
            
            self.stdout.write(f"\n📋 Configuration:")
            self.stdout.write(f"KMS Key ID:        {settings.KYC_REWARD_KMS_KEY_ID}")
            self.stdout.write(f"AWS Region:        {settings.KYC_REWARD_KMS_REGION}")
            self.stdout.write(f"Chain ID:          {settings.KYC_REWARD_CHAIN_ID}")
            self.stdout.write(f"\n🔑 Derived Address: {derived_address}")
            
            # Check if it matches settings
            configured_address = getattr(settings, 'KMS_SIGNER_SENDER_ADDRESS', None)
            if configured_address:
                if configured_address.lower() == derived_address.lower():
                    self.stdout.write(self.style.SUCCESS("✅ Matches configured address"))
                else:
                    self.stdout.write(self.style.ERROR(
                        f"❌ MISMATCH! Configured: {configured_address}"
                    ))
                    self.stdout.write(self.style.WARNING(
                        f"\n⚠️  Update KMS_SIGNER_SENDER_ADDRESS to: {derived_address}"
                    ))
            else:
                self.stdout.write(self.style.WARNING(
                    "⚠️  KMS_SIGNER_SENDER_ADDRESS not set in settings"
                ))
            
            if options['derive_only']:
                return
            
            # Check balances
            if options['check_balance'] or not options['derive_only']:
                w3 = Web3(Web3.HTTPProvider(settings.ETHEREUM_RPC_URL))
                
                if not w3.is_connected():
                    self.stdout.write(self.style.ERROR("\n❌ Cannot connect to RPC"))
                    return
                
                chain_id = w3.eth.chain_id
                self.stdout.write(f"\n🌐 Network: Chain ID {chain_id}")
                
                # ETH balance
                eth_wei = w3.eth.get_balance(derived_address)
                eth_balance = float(Web3.from_wei(eth_wei, 'ether'))
                
                self.stdout.write(f"\n💰 Balances:")
                self.stdout.write(f"ETH:              {eth_balance:.6f}")
                
                # Token balance
                try:
                    token_abi = [
                        {
                            "inputs": [{"name": "account", "type": "address"}],
                            "name": "balanceOf",
                            "outputs": [{"name": "", "type": "uint256"}],
                            "stateMutability": "view",
                            "type": "function"
                        }
                    ]
                    token = w3.eth.contract(
                        address=Web3.to_checksum_address(settings.TOKEN_CONTRACT_ADDRESS),
                        abi=token_abi
                    )
                    token_wei = token.functions.balanceOf(derived_address).call()
                    token_balance = float(token_wei / 10**18)
                    self.stdout.write(f"Tokens:           {token_balance:.4f}")
                except Exception as e:
                    self.stdout.write(f"Tokens:           Error - {e}")
                
                # Funding instructions
                if eth_balance < 0.001:
                    self.stdout.write(self.style.WARNING(
                        f"\n⚠️  LOW ETH - Need to fund for gas!"
                    ))
                    
                    faucets = {
                        84532: [
                            'https://www.alchemy.com/faucets/base-sepolia',
                            'https://faucet.quicknode.com/base/sepolia'
                        ],
                        80002: [
                            'https://faucet.polygon.technology/'
                        ]
                    }
                    
                    if chain_id in faucets:
                        self.stdout.write(f"\n🚰 Get testnet ETH from:")
                        for faucet in faucets[chain_id]:
                            self.stdout.write(f"   • {faucet}")
                        self.stdout.write(f"\n📋 Address: {derived_address}")
                else:
                    self.stdout.write(self.style.SUCCESS(
                        "\n✅ ETH balance sufficient for gas"
                    ))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Error: {e}'))
            raise