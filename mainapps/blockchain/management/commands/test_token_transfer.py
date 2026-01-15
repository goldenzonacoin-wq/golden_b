from django.core.management.base import BaseCommand, CommandError
from ...kms_signer import KmsTokenTransfer
from decimal import Decimal


class Command(BaseCommand):
    help = 'Transfer ATC tokens using KMS wallet'

    def add_arguments(self, parser):
        parser.add_argument(
            '--recipient',
            type=str,
            help='Recipient Ethereum address',
        )
        parser.add_argument(
            '--amount',
            type=float,
            help='Amount of tokens to send',
        )
        parser.add_argument(
            '--purpose',
            type=str,
            default='manual_transfer',
            help='Purpose of transfer (e.g., kyc_reward, purchase)',
        )
        parser.add_argument(
            '--balance',
            action='store_true',
            help='Check KMS wallet balance only',
        )
        parser.add_argument(
            '--discover',
            action='store_true',
            help='Discover which address KMS controls',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('='*60))
        self.stdout.write(self.style.SUCCESS('🪙  ATC Token Transfer Service'))
        self.stdout.write(self.style.SUCCESS('='*60))
        
        try:
            service = KmsTokenTransfer()
            
            # Discover mode
            if options['discover']:
                self.stdout.write('\n🔍 Discovering KMS address...')
                result = service.discover_kms_address()
                
                self.stdout.write(self.style.SUCCESS(f"\n✅ KMS Address: {result['address']}"))
                self.stdout.write(f"Token Balance: {result['balance']} GZC")
                self.stdout.write(f"Matches Config: {result['matches_config']}")
                
                if not result['matches_config']:
                    self.stdout.write(self.style.WARNING(
                        f"\n⚠️  Update KMS_SIGNER_SENDER_ADDRESS in settings to: {result['address']}"
                    ))
                return
            
            # Balance mode
            if options['balance']:
                self.stdout.write('\n💰 Checking balances...')
                token_balance = service.get_balance()
                eth_balance = service.get_eth_balance()
                
                self.stdout.write(self.style.SUCCESS(f"\nKMS Wallet: {service.kms_wallet}"))
                self.stdout.write(f"Chain ID: {service.chain_id}")
                self.stdout.write(f"Token Balance: {token_balance} ATC")
                self.stdout.write(f"ETH Balance: {eth_balance} ETH")
                return
            
            # Transfer mode
            recipient = options.get('recipient')
            amount = options.get('amount')
            
            if not recipient or not amount:
                raise CommandError('--recipient and --amount are required for transfers')
            
            # Confirmation
            self.stdout.write(f"\n{'='*60}")
            self.stdout.write('📋 TRANSFER DETAILS')
            self.stdout.write(f"{'='*60}")
            self.stdout.write(f"From:      {service.kms_wallet}")
            self.stdout.write(f"To:        {recipient}")
            self.stdout.write(f"Amount:    {amount} ATC")
            self.stdout.write(f"Purpose:   {options['purpose']}")
            self.stdout.write(f"{'='*60}")
            
            confirm = input('\n⚠️  Proceed with transfer? (yes/no): ').strip().lower()
            
            if confirm not in ['yes', 'y']:
                self.stdout.write(self.style.WARNING('❌ Transfer cancelled'))
                return
            
            # Execute transfer
            self.stdout.write('\n🚀 Executing transfer...\n')
            result = service.transfer_tokens(
                recipient=recipient,
                amount_tokens=amount,
                purpose=options['purpose']
            )
            
            # Display results
            self.stdout.write(f"\n{'='*60}")
            self.stdout.write('📋 TRANSACTION RESULT')
            self.stdout.write(f"{'='*60}")
            self.stdout.write(f"TX Hash:      {result['tx_hash']}")
            self.stdout.write(f"Status:       {'✅ SUCCESS' if result['status'] == 1 else '❌ FAILED'}")
            self.stdout.write(f"Gas Used:     {result['gas_used']}")
            self.stdout.write(f"Block:        {result['block_number']}")
            self.stdout.write(f"Explorer:     {result['explorer_url']}")
            self.stdout.write(f"{'='*60}")
            
            if result['status'] == 1:
                new_balance = service.get_balance()
                self.stdout.write(f"\n💰 New KMS balance: {new_balance} ATC")
                self.stdout.write(self.style.SUCCESS('\n✅ Transfer completed successfully!'))
            else:
                raise CommandError('Transaction failed - check explorer for details')
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Error: {str(e)}'))
            raise CommandError(str(e))