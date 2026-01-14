from django.core.management.base import BaseCommand
from decimal import Decimal

from ...kms_signer import KmsTokenTransfer 


class Command(BaseCommand):
    help = 'Send tokens directly from KMS wallet (bypassing distributor)'

    def add_arguments(self, parser):
        parser.add_argument('--recipient', required=True, help='Recipient address')
        parser.add_argument('--amount', type=float, default=1.0, help='Amount in tokens')
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
        service = KmsTokenTransfer()
        try:
            recipient = options.get('recipient')
            amount = options.get('amount')

            
            result = service.transfer_tokens(
                recipient=recipient,
                amount_tokens=amount,
                purpose=options['purpose']
            )
            if result['status'] == 1:
                self.stdout.write(self.style.SUCCESS(
                    f"Success! Tx: {result['tx_hash']}\nGas used: {result['gas_used']}"
                ))
            else:
                self.stdout.write(self.style.ERROR("Transaction failed"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed: {str(e)}"))