from django.contrib import admin
from django.utils.html import format_html
from .models import (
    SmartContractTransaction, VestingSchedule, CommitRevealTransfer,
    WhaleProtectionLimit, FeeExemption, BlacklistedAddress, MiningReward
)


@admin.register(SmartContractTransaction)
class SmartContractTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'transaction_type', 'from_address_short', 'to_address_short',
        'amount', 'status', 'transaction_hash_short', 'created_at'
    )
    list_filter = ('transaction_type', 'status', 'created_at')
    search_fields = ('user__email', 'transaction_hash', 'from_address', 'to_address')
    readonly_fields = ('transaction_hash', 'block_number', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Transaction Info', {
            'fields': ('user', 'transaction_type', 'from_address', 'to_address', 'amount')
        }),
        ('Gas & Fees', {
            'fields': ('gas_price', 'gas_limit')
        }),
        ('Blockchain Data', {
            'fields': ('transaction_hash', 'block_number', 'status', 'error_message')
        }),
        ('Special Fields', {
            'fields': ('nonce', 'commitment', 'vesting_duration'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def from_address_short(self, obj):
        if obj.from_address:
            return f"{obj.from_address[:6]}...{obj.from_address[-4:]}"
        return "-"
    from_address_short.short_description = "From"
    
    def to_address_short(self, obj):
        if obj.to_address:
            return f"{obj.to_address[:6]}...{obj.to_address[-4:]}"
        return "-"
    to_address_short.short_description = "To"
    
    def transaction_hash_short(self, obj):
        if obj.transaction_hash:
            return f"{obj.transaction_hash[:10]}..."
        return "-"
    transaction_hash_short.short_description = "Tx Hash"


@admin.register(VestingSchedule)
class VestingScheduleAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'beneficiary_address_short', 'total_amount', 'released_amount',
        'vested_amount_display', 'is_whale', 'start_time'
    )
    list_filter = ('is_whale', 'start_time', 'created_at')
    search_fields = ('user__email', 'beneficiary_address')
    readonly_fields = ('vested_amount_display', 'created_at')
    
    def beneficiary_address_short(self, obj):
        return f"{obj.beneficiary_address[:6]}...{obj.beneficiary_address[-4:]}"
    beneficiary_address_short.short_description = "Beneficiary"
    
    def vested_amount_display(self, obj):
        return f"{obj.vested_amount:.8f}"
    vested_amount_display.short_description = "Vested Amount"


@admin.register(CommitRevealTransfer)
class CommitRevealTransferAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'to_address_short', 'amount', 'commitment_short',
        'revealed', 'commit_time'
    )
    list_filter = ('revealed', 'commit_time')
    search_fields = ('user__email', 'to_address', 'commitment')
    readonly_fields = ('commit_time',)
    
    def to_address_short(self, obj):
        return f"{obj.to_address[:6]}...{obj.to_address[-4:]}"
    to_address_short.short_description = "To Address"
    
    def commitment_short(self, obj):
        return f"{obj.commitment[:10]}..."
    commitment_short.short_description = "Commitment"


@admin.register(WhaleProtectionLimit)
class WhaleProtectionLimitAdmin(admin.ModelAdmin):
    list_display = (
        'address_short', 'max_transfer_amount', 'max_balance_percentage',
        'is_active', 'created_at'
    )
    list_filter = ('is_active', 'created_at')
    search_fields = ('address',)
    readonly_fields = ('created_at', 'updated_at')
    
    def address_short(self, obj):
        return f"{obj.address[:6]}...{obj.address[-4:]}"
    address_short.short_description = "Address"


@admin.register(FeeExemption)
class FeeExemptionAdmin(admin.ModelAdmin):
    list_display = (
        'address_short', 'exemption_type', 'exemption_percentage',
        'is_active', 'created_at'
    )
    list_filter = ('exemption_type', 'is_active', 'created_at')
    search_fields = ('address',)
    readonly_fields = ('created_at', 'updated_at')
    
    def address_short(self, obj):
        return f"{obj.address[:6]}...{obj.address[-4:]}"
    address_short.short_description = "Address"


@admin.register(BlacklistedAddress)
class BlacklistedAddressAdmin(admin.ModelAdmin):
    list_display = (
        'address_short', 'reason_short', 'blacklisted_by',
        'is_active', 'created_at'
    )
    list_filter = ('is_active', 'blacklisted_by', 'created_at')
    search_fields = ('address', 'reason')
    readonly_fields = ('created_at', 'updated_at')
    
    def address_short(self, obj):
        return f"{obj.address[:6]}...{obj.address[-4:]}"
    address_short.short_description = "Address"
    
    def reason_short(self, obj):
        if obj.reason:
            return obj.reason[:50] + "..." if len(obj.reason) > 50 else obj.reason
        return "-"
    reason_short.short_description = "Reason"


@admin.register(MiningReward)
class MiningRewardAdmin(admin.ModelAdmin):
    list_display = (
        'miner_address_short', 'block_number', 'reward_amount',
        'claimed', 'transaction_hash_short', 'created_at'
    )
    list_filter = ('claimed', 'created_at')
    search_fields = ('miner_address', 'block_number', 'transaction_hash')
    readonly_fields = ('created_at',)
    
    def miner_address_short(self, obj):
        return f"{obj.miner_address[:6]}...{obj.miner_address[-4:]}"
    miner_address_short.short_description = "Miner"
    
    def transaction_hash_short(self, obj):
        if obj.transaction_hash:
            return f"{obj.transaction_hash[:10]}..."
        return "-"
    transaction_hash_short.short_description = "Tx Hash"
