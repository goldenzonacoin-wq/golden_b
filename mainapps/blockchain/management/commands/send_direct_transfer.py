from django.core.management.base import BaseCommand
from decimal import Decimal

from ...kms_signer import KmsTokenTransfer 


class Command(BaseCommand):
    help = 'Send tokens directly from KMS wallet (bypassing distributor)'

    def add_arguments(self, parser):
        parser.add_argument('recipient', nargs='?', help='Recipient address')
        parser.add_argument('amount', nargs='?', type=float, help='Amount in tokens')
        parser.add_argument('--recipient', dest='recipient_kw', help='Recipient address')
        parser.add_argument('--amount', dest='amount_kw', type=float, help='Amount in tokens')
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
            recipient = options.get('recipient_kw') or options.get('recipient')
            amount = options.get('amount_kw')
            if amount is None:
                amount = options.get('amount')
            if amount is None:
                amount = 1.0

            
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
