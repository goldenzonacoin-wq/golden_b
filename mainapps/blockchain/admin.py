from django.contrib import admin
from django.utils.html import format_html
from .models import (
    BlockchainNetwork, TokenContract, WalletBalance, Transaction,
    StakingPool, UserStake, VestingSchedule, BlockchainEvent,
    TokenPurchaseSettings, TokenPurchase
)


@admin.register(BlockchainNetwork)
class BlockchainNetworkAdmin(admin.ModelAdmin):
    list_display = ('name', 'chain_id', 'native_currency_symbol', 'is_testnet', 'is_active')
    list_filter = ('is_testnet', 'is_active')
    search_fields = ('name', 'chain_id')


@admin.register(TokenContract)
class TokenContractAdmin(admin.ModelAdmin):
    list_display = (
        'token_symbol', 'network', 'contract_address_short', 
        'total_supply', 'is_active', 'created_at'
    )
    list_filter = ('network', 'is_active', 'created_at')
    search_fields = ('token_name', 'token_symbol', 'contract_address')
    readonly_fields = ('created_at',)
    
    def contract_address_short(self, obj):
        return f"{obj.contract_address[:6]}...{obj.contract_address[-4:]}"
    contract_address_short.short_description = "Contract Address"


@admin.register(WalletBalance)
class WalletBalanceAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'token_contract', 'balance', 'is_whale', 'last_updated'
    )
    list_filter = ('token_contract', 'network', 'last_updated')
    search_fields = ('user__email', 'user__wallet_address')
    readonly_fields = ('is_whale', 'last_updated')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        'tx_hash_short', 'transaction_type', 'from_address_short', 
        'to_address_short', 'amount', 'status', 'created_at'
    )
    list_filter = ('transaction_type', 'status', 'network', 'created_at')
    search_fields = ('tx_hash', 'from_address', 'to_address')
    readonly_fields = ('created_at', 'confirmed_at')
    
    def tx_hash_short(self, obj):
        return f"{obj.tx_hash[:10]}..."
    tx_hash_short.short_description = "Transaction Hash"
    
    def from_address_short(self, obj):
        return f"{obj.from_address[:6]}...{obj.from_address[-4:]}"
    from_address_short.short_description = "From"
    
    def to_address_short(self, obj):
        return f"{obj.to_address[:6]}...{obj.to_address[-4:]}"
    to_address_short.short_description = "To"


@admin.register(StakingPool)
class StakingPoolAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'pool_type', 'annual_percentage_yield', 'total_staked',
        'utilization_rate', 'is_active', 'created_at'
    )
    list_filter = ('pool_type', 'is_active', 'created_at')
    search_fields = ('name',)
    readonly_fields = ('total_staked', 'utilization_rate', 'is_full', 'created_at', 'updated_at')


@admin.register(UserStake)
class UserStakeAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'staking_pool', 'staked_amount', 'rewards_earned',
        'status', 'is_locked', 'staked_at'
    )
    list_filter = ('status', 'staking_pool', 'staked_at')
    search_fields = ('user__email', 'staking_pool__name')
    readonly_fields = ('pending_rewards', 'total_rewards', 'is_locked', 'staked_at')


@admin.register(VestingSchedule)
class VestingScheduleAdmin(admin.ModelAdmin):
    list_display = (
        'beneficiary', 'total_amount', 'vesting_type', 'vested_amount',
        'releasable_amount', 'is_revoked', 'created_at'
    )
    list_filter = ('vesting_type', 'is_revoked', 'created_at')
    search_fields = ('beneficiary__email',)
    readonly_fields = ('vested_amount', 'releasable_amount', 'created_at')


@admin.register(BlockchainEvent)
class BlockchainEventAdmin(admin.ModelAdmin):
    list_display = (
        'tx_hash_short', 'event_type', 'block_number', 
        'is_processed', 'block_timestamp'
    )
    list_filter = ('event_type', 'is_processed', 'network', 'block_timestamp')
    search_fields = ('tx_hash', 'contract_address')
    readonly_fields = ('created_at',)
    
    def tx_hash_short(self, obj):
        return f"{obj.tx_hash[:10]}..."
    tx_hash_short.short_description = "Transaction Hash"


@admin.register(TokenPurchaseSettings)
class TokenPurchaseSettingsAdmin(admin.ModelAdmin):
    list_display = ('token_price_usd', 'is_active', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(TokenPurchase)
class TokenPurchaseAdmin(admin.ModelAdmin):
    list_display = (
        'tx_ref', 'user_id', 'token_amount', 'usd_amount',
        'currency', 'charge_amount', 'status', 'transfer_status', 'created_at'
    )
    list_filter = ('status', 'transfer_status', 'currency', 'created_at')
    search_fields = ('tx_ref', 'flw_ref', 'wallet_address', 'user_id')
    readonly_fields = ('created_at', 'updated_at')
