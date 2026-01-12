from django.core.management.base import BaseCommand
from ...kms_signer import RewardDistributorService
from decimal import Decimal
from web3 import Web3

class Command(BaseCommand):
    help = 'Send a small test reward'

    def add_arguments(self, parser):
        parser.add_argument('--recipient', required=True, help='Recipient address')
        parser.add_argument('--amount', type=float, default=10.0, help='Amount in ether')

    def handle(self, *args, **options):
        service = RewardDistributorService()
        try:
            result = service.distribute_reward(
                recipient=options['recipient'],
                amount_ether=Decimal(str(options['amount']))
            )
            self.stdout.write(self.style.SUCCESS(
                f"Success! Tx hash: {result['tx_hash']}\n"
                f"Gas used: {result['gas_used']}"
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed: {str(e)}"))


# run python manage.py send_test_reward --recipient public_address --amount 10

