from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import WalletSession, WalletCreationLog, WalletRecoveryAttempt


@admin.register(WalletSession)
class WalletSessionAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'session_token_short', 'is_active', 'is_expired',
        'last_used', 'expires_at', 'created_at'
    )
    list_filter = ('is_active', 'created_at', 'expires_at')
    search_fields = ('user__email', 'session_token')
    readonly_fields = ('session_token', 'created_at', 'last_used', 'is_expired')
    
    fieldsets = (
        ('Session Info', {
            'fields': ('user', 'session_token', 'is_active')
        }),
        ('Security', {
            'fields': ('encrypted_private_key',),
            'classes': ('collapse',)
        }),
        ('Timing', {
            'fields': ('created_at', 'last_used', 'expires_at', 'is_expired')
        }),
    )
    
    def session_token_short(self, obj):
        return f"{obj.session_token[:8]}..."
    session_token_short.short_description = "Session Token"
    
    def is_expired(self, obj):
        expired = timezone.now() > obj.expires_at
        if expired:
            return format_html('<span style="color: red;">Expired</span>')
        return format_html('<span style="color: green;">Active</span>')
    is_expired.short_description = "Status"
    
    def has_change_permission(self, request, obj=None):
        # Prevent editing encrypted private keys
        return False


@admin.register(WalletCreationLog)
class WalletCreationLogAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'wallet_address_short', 'ip_address',
        'user_agent_short', 'created_at'
    )
    list_filter = ('created_at',)
    search_fields = ('user__email', 'wallet_address', 'ip_address')
    readonly_fields = ('recovery_phrase_hash', 'created_at')
    
    fieldsets = (
        ('Wallet Info', {
            'fields': ('user', 'wallet_address')
        }),
        ('Security', {
            'fields': ('recovery_phrase_hash',),
            'classes': ('collapse',)
        }),
        ('Audit Trail', {
            'fields': ('ip_address', 'user_agent', 'created_at')
        }),
    )
    
    def wallet_address_short(self, obj):
        return f"{obj.wallet_address[:6]}...{obj.wallet_address[-4:]}"
    wallet_address_short.short_description = "Wallet Address"
    
    def user_agent_short(self, obj):
        if obj.user_agent:
            return obj.user_agent[:50] + "..." if len(obj.user_agent) > 50 else obj.user_agent
        return "-"
    user_agent_short.short_description = "User Agent"
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(WalletRecoveryAttempt)
class WalletRecoveryAttemptAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'success_status', 'ip_address',
        'error_message_short', 'created_at'
    )
    list_filter = ('success', 'created_at')
    search_fields = ('user__email', 'ip_address')
    readonly_fields = ('created_at',)
    
    def success_status(self, obj):
        if obj.success:
            return format_html('<span style="color: green;">✓ Success</span>')
        return format_html('<span style="color: red;">✗ Failed</span>')
    success_status.short_description = "Status"
    
    def error_message_short(self, obj):
        if obj.error_message:
            return obj.error_message[:50] + "..." if len(obj.error_message) > 50 else obj.error_message
        return "-"
    error_message_short.short_description = "Error"
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
