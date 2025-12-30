from django.apps import AppConfig


class KycConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "mainapps.kyc"
    def ready(self):
        import mainapps.kyc.signals  # noqa F401
        
        
