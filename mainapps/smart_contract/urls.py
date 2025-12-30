from django.urls import path
from . import views

app_name = 'smartcontract'

urlpatterns = [
    # Token Operations (User endpoints)
    path('transfer/prepare/', views.prepare_transfer, name='prepare_transfer'),
    path('transfer/submit/', views.submit_signed_transaction, name='submit_signed_transaction'),
    path('commit-transfer/prepare/', views.prepare_commit_transfer, name='prepare_commit_transfer'),
    path('reveal-transfer/', views.reveal_transfer, name='reveal_transfer'),
    
    # Vesting Operations
    path('vesting/schedules/', views.UserVestingScheduleListView.as_view(), name='user_vesting_schedules'),
    path('vesting/release/<int:schedule_id>/', views.release_vested_tokens, name='release_vested_tokens'),
    
    # Mining Operations
    path('mining/claim-reward/', views.claim_mining_reward, name='claim_mining_reward'),
    
    # User Statistics and History
    path('transactions/', views.UserTransactionListView.as_view(), name='user_transactions'),
    path('stats/', views.user_token_stats, name='user_token_stats'),
    
    # Admin Token Management
    path('admin/mint/', views.admin_mint_tokens, name='admin_mint_tokens'),
    path('admin/burn/', views.admin_burn_tokens, name='admin_burn_tokens'),
    path('admin/pause/', views.admin_pause_contract, name='admin_pause_contract'),
    path('admin/unpause/', views.admin_unpause_contract, name='admin_unpause_contract'),
    
    # Admin Whale Protection
    path('admin/whale-limits/', views.WhaleProtectionLimitListView.as_view(), name='whale_protection_limits'),
    path('admin/whale-limits/set/', views.admin_set_whale_limit, name='admin_set_whale_limit'),
    
    # Admin Fee Management
    path('admin/fee-exemptions/', views.FeeExemptionListView.as_view(), name='fee_exemptions'),
    path('admin/fee-exemptions/add/', views.admin_add_fee_exemption, name='admin_add_fee_exemption'),
    
    # Admin Blacklist Management
    path('admin/blacklist/', views.BlacklistedAddressListView.as_view(), name='blacklisted_addresses'),
    path('admin/blacklist/add/', views.admin_blacklist_address, name='admin_blacklist_address'),
    path('admin/blacklist/remove/<int:address_id>/', views.admin_unblacklist_address, name='admin_unblacklist_address'),
    
    # Admin Statistics and Management
    path('admin/transactions/', views.AdminTransactionListView.as_view(), name='admin_transactions'),
    path('admin/stats/', views.admin_contract_stats, name='admin_contract_stats'),
]
