from django.urls import path
from .views import (
    BlockchainNetworkListView,
    TokenContractListView,
    UserWalletBalanceView,
    UserTransactionListView,
    TokenPurchaseListCreateView,
    TokenPurchaseSettingsView,
    StakingPoolListView,
    UserStakeListView,
    create_stake,
    unstake,
    claim_rewards,
    UserVestingScheduleListView,
    release_vested_tokens,
    wallet_stats,
    network_stats,
    AdminTransactionListView,
    AdminBlockchainEventListView,
    TokenTransferView,
    UniswapSupportedChainsView,
    UniswapSwappableTokensView,
    UniswapCheckApprovalView,
    UniswapQuoteView,
    UniswapSwapView,
    UniswapOrderView,
    UniswapSwapStatusView,
    UniswapOrderStatusView,
)


urlpatterns = [
    # General endpoints
    path('networks/', BlockchainNetworkListView.as_view(), name='blockchain-networks'),
    path('tokens/', TokenContractListView.as_view(), name='token-contracts'),
    path('stats/', network_stats, name='network-stats'),

    # User-specific endpoints
    path('wallet/balance/', UserWalletBalanceView.as_view(), name='user-wallet-balance'),
    path('wallet/transactions/', UserTransactionListView.as_view(), name='user-transactions'),
    path('wallet/stats/', wallet_stats, name='user-wallet-stats'),
    path('token-purchases/', TokenPurchaseListCreateView.as_view(), name='token-purchases'),
    path('token-purchases/settings/', TokenPurchaseSettingsView.as_view(), name='token-purchases-settings'),

    # Staking endpoints
    path('staking/pools/', StakingPoolListView.as_view(), name='staking-pools'),
    path('staking/stakes/', UserStakeListView.as_view(), name='user-stakes'),
    path('staking/stake/', create_stake, name='create-stake'),
    path('staking/unstake/<int:stake_id>/', unstake, name='unstake'),
    path('staking/claim/<int:stake_id>/', claim_rewards, name='claim-rewards'),

    # Vesting endpoints
    path('vesting/schedules/', UserVestingScheduleListView.as_view(), name='user-vesting-schedules'),
    path('vesting/release/<int:schedule_id>/', release_vested_tokens, name='release-vested-tokens'),

    # Admin endpoints
    path('admin/transactions/', AdminTransactionListView.as_view(), name='admin-transactions'),
    path('admin/events/', AdminBlockchainEventListView.as_view(), name='admin-blockchain-events'),

    #KMS Token Transfer endpoint
    path('token-transfer/', TokenTransferView.as_view(), name='kms-token-transfer'),
    path('uniswap/chains/', UniswapSupportedChainsView.as_view(), name='uniswap-supported-chains'),
    path('uniswap/swappable-tokens/', UniswapSwappableTokensView.as_view(), name='uniswap-swappable-tokens'),
    path('uniswap/check-approval/', UniswapCheckApprovalView.as_view(), name='uniswap-check-approval'),
    path('uniswap/quote/', UniswapQuoteView.as_view(), name='uniswap-quote'),
    path('uniswap/swap/', UniswapSwapView.as_view(), name='uniswap-swap'),
    path('uniswap/order/', UniswapOrderView.as_view(), name='uniswap-order'),
    path('uniswap/swaps/', UniswapSwapStatusView.as_view(), name='uniswap-swap-status'),
    path('uniswap/orders/', UniswapOrderStatusView.as_view(), name='uniswap-order-status'),
]
