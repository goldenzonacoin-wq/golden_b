from django.urls import path
from . import views

app_name = 'wallet'

urlpatterns = [
    # Wallet management
    path('create/', views.create_wallet, name='create_wallet'),
    path('recover/', views.recover_wallet, name='recover_wallet'),
    path('info/', views.wallet_info, name='wallet_info'),
    
    # Transaction management
    path('transaction/create/', views.create_transaction, name='create_transaction'),
    
    # Session management
    path('sessions/', views.wallet_sessions, name='wallet_sessions'),
    path('sessions/end/', views.end_wallet_session, name='end_wallet_session'),
]
