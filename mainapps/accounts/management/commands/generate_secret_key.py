# your_app/management/commands/generate_secret_key.py

from django.core.management.base import BaseCommand
from django.core.management.utils import get_random_secret_key


class Command(BaseCommand):
    help = "Generate a secure Django SECRET_KEY"

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=1,
            help="Number of secret keys to generate (default: 1)",
        )

    def handle(self, *args, **options):
        count = options["count"]

        self.stdout.write(self.style.SUCCESS("Generated SECRET_KEY(s):\n"))

        for i in range(count):
            key = get_random_secret_key()
            self.stdout.write(f"{i + 1}. {key}")
