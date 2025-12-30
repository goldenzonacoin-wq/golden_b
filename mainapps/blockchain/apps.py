from django.apps import AppConfig


class BlockchainConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "mainapps.blockchain"
    def ready(self):
        import mainapps.blockchain.signals  # noqa F401
        
