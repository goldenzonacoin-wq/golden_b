from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mainapps.accounts'
    verbose_name = 'User Accounts'
    
    def ready(self):
        import mainapps.accounts.signals
