from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from .models import User, UserProfile, VerificationCode, UserActivity


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        'email', 'get_full_name', 'role', 'membership_tier', 
        'is_verified', 'is_kyc_verified', 'wallet_address_short', 
        'created_at'
    )
    list_filter = (
        'role', 'membership_tier', 'is_verified', 'is_kyc_verified', 
        'is_active', 'is_staff', 'created_at'
    )
    search_fields = ('email', 'first_name', 'last_name', 'wallet_address')
    ordering = ('-created_at',)
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {
            'fields': ('first_name', 'last_name', 'sex', 'date_of_birth', 'phone_number')
        }),
        ('Blockchain', {
            'fields': ('wallet_address', 'atc_balance')
        }),
        ('Permissions', {
            'fields': ('role', 'membership_tier', 'is_active', 'is_staff', 'is_superuser', 
                      'is_verified', 'is_kyc_verified', 'groups', 'user_permissions')
        }),
        ('Important dates', {'fields': ('last_login', 'created_at', 'updated_at')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'password1', 'password2'),
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')
    
    def wallet_address_short(self, obj):
        if obj.wallet_address:
            return f"{obj.wallet_address[:6]}...{obj.wallet_address[-4:]}"
        return "-"
    wallet_address_short.short_description = "Wallet"


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'occupation', 
        'reputation_score', 'referral_code', 'created_at'
    )
    list_filter = ('show_wallet_address', 'created_at')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'occupation', 'company')
    readonly_fields = ('referral_code', 'created_at', 'updated_at')
    
    fieldsets = (
        ('User', {'fields': ('user',)}),
        ('Profile', {
            'fields': ('bio', 'profile_image', 'cover_image', 'occupation', 'company', 'website')
        }),
        ('Social Links', {
            'fields': ('twitter_handle', 'linkedin_profile', 'github_profile', 
                      'discord_handle', 'telegram_handle')
        }),
        
        ('Community', {
            'fields': ('reputation_score', 'contribution_points', 'referral_code', 'referred_by')
        }),
        ('Privacy', {
            'fields': ('show_wallet_address', 'show_token_balance', 'allow_direct_messages')
        }),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )



@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ('user', 'activity_type', 'ip_address', 'created_at')
    list_filter = ('activity_type', 'created_at')
    search_fields = ('user__email', 'activity_type', 'ip_address')
    readonly_fields = ('created_at',)
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
