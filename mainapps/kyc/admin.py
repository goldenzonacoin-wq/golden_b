from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db.models import Count, Q
from django.contrib.admin import SimpleListFilter
from django.utils import timezone
from datetime import timedelta

from .models import (
    KYCApplication, 
    KYCDocument, 
    KYCReviewNote, 
    KYCSettings, 
    ComplianceCheck
)


class StatusFilter(SimpleListFilter):
    title = 'Status'
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return KYCApplication.Status.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(status=self.value())
        return queryset


class RiskLevelFilter(SimpleListFilter):
    title = 'Risk Level'
    parameter_name = 'risk_level'

    def lookups(self, request, model_admin):
        return KYCApplication.RiskLevel.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(risk_level=self.value())
        return queryset


class ExpiryFilter(SimpleListFilter):
    title = 'Expiry Status'
    parameter_name = 'expiry'

    def lookups(self, request, model_admin):
        return (
            ('expired', 'Expired'),
            ('expiring_soon', 'Expiring Soon (30 days)'),
            ('valid', 'Valid'),
        )

    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == 'expired':
            return queryset.filter(expires_at__lt=now)
        elif self.value() == 'expiring_soon':
            return queryset.filter(
                expires_at__gte=now,
                expires_at__lt=now + timedelta(days=30)
            )
        elif self.value() == 'valid':
            return queryset.filter(expires_at__gte=now)
        return queryset


class KYCDocumentInline(admin.TabularInline):
    model = KYCDocument
    extra = 0
    readonly_fields = ('uploaded_at',)
    fields = ('category', 'document_name', 'document_file', 'description', 'uploaded_at')


class KYCReviewNoteInline(admin.TabularInline):
    model = KYCReviewNote
    extra = 1
    readonly_fields = ('created_at',)
    fields = ('reviewer', 'note', 'is_internal', 'created_at')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('reviewer')


class ComplianceCheckInline(admin.TabularInline):
    model = ComplianceCheck
    extra = 0
    readonly_fields = ('created_at', 'confidence_score', 'provider')
    fields = ('check_type', 'result', 'confidence_score', 'provider', 'created_at')


@admin.register(KYCApplication)
class KYCApplicationAdmin(admin.ModelAdmin):
    list_display = [
        'application_id', 
        'user_info', 
        'status_badge', 
        'risk_level_badge',
        'document_status',
        'submitted_at', 
        'reviewed_at',
        'expiry_status',
        'reviewed_by'
    ]
    
    list_filter = [
        StatusFilter,
        RiskLevelFilter,
        ExpiryFilter,
        'document_type',
        'nationality',
        'crypto_experience',
        'created_at',
        'submitted_at',
        'reviewed_at'
    ]
    
    search_fields = [
        'application_id',
        'user__email',
        'user__first_name',
        'user__last_name',
        'full_name',
        'document_number'
    ]
    
    readonly_fields = [
        'application_id',
        'created_at',
        'updated_at',
        'user_link',
        'document_preview',
        'compliance_summary'
    ]
    
    fieldsets = (
        ('Application Info', {
            'fields': (
                'application_id',
                'user_link',
                'status',
                'risk_level',
                'created_at',
                'updated_at'
            )
        }),
        ('Personal Information', {
            'fields': (
                'full_name',
                'date_of_birth',
                'nationality',
                'address'
            )
        }),
        ('Document Information', {
            'fields': (
                'document_type',
                'document_number',
                'document_expiry_date',
                'document_issuing_country',
                'document_preview'
            )
        }),
        ('Employment & Financial', {
            'fields': (
                'occupation',
                'employer',
                'annual_income_range',
                'source_of_funds'
            ),
            'classes': ('collapse',)
        }),
        ('Crypto Information', {
            'fields': (
                'intended_use',
                'crypto_experience',
                'other_wallets'
            ),
            'classes': ('collapse',)
        }),
        ('Review Information', {
            'fields': (
                'reviewed_by',
                'review_notes',
                'rejection_reason',
                'submitted_at',
                'reviewed_at',
                'expires_at'
            )
        }),
        ('Compliance', {
            'fields': ('compliance_summary',),
            'classes': ('collapse',)
        })
    )
    
    inlines = [KYCReviewNoteInline, KYCDocumentInline, ComplianceCheckInline]
    
    actions = ['approve_applications', 'reject_applications', 'flag_for_review']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'user', 'reviewed_by', 'nationality', 'address'
        ).prefetch_related('compliance_checks', 'kyc_review_notes')
    
    def user_info(self, obj):
        return format_html(
            '<strong>{}</strong><br/><small>{}</small>',
            obj.user.get_full_name or obj.user.email,
            obj.user.email
        )
    user_info.short_description = 'User'
    
    def user_link(self, obj):
        if obj.user:
            url = reverse('admin:accounts_user_change', args=[obj.user.pk])
            return format_html('<a href="{}">{}</a>', url, obj.user.email)
        return '-'
    user_link.short_description = 'User Account'
    
    def status_badge(self, obj):
        colors = {
            'draft': '#6c757d',
            'submitted': '#007bff',
            'under_review': '#ffc107',
            'approved': '#28a745',
            'rejected': '#dc3545',
            'flagged': '#fd7e14',
            'expired': '#6f42c1'
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def risk_level_badge(self, obj):
        colors = {
            'low': '#28a745',
            'medium': '#ffc107',
            'high': '#fd7e14',
            'critical': '#dc3545'
        }
        color = colors.get(obj.risk_level, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color, obj.get_risk_level_display()
        )
    risk_level_badge.short_description = 'Risk Level'
    
    def document_status(self, obj):
        docs = []
        if obj.document_front:
            docs.append('✓ Front')
        if obj.document_back:
            docs.append('✓ Back')
        if obj.selfie_image:
            docs.append('✓ Selfie')
        if obj.proof_of_address:
            docs.append('✓ Address')
        
        return format_html('<br/>'.join(docs)) if docs else 'No documents'
    document_status.short_description = 'Documents'
    
    def expiry_status(self, obj):
        if not obj.expires_at:
            return '-'
        
        now = timezone.now()
        if obj.expires_at < now:
            return format_html('<span style="color: red;">Expired</span>')
        elif obj.expires_at < now + timedelta(days=30):
            days = (obj.expires_at - now).days
            return format_html('<span style="color: orange;">Expires in {} days</span>', days)
        else:
            return format_html('<span style="color: green;">Valid</span>')
    expiry_status.short_description = 'Expiry'
    
    def document_preview(self, obj):
        previews = []
        
        if obj.document_front:
            previews.append(f'<div><strong>Front:</strong> <a href="{obj.document_front.url}" target="_blank">View</a></div>')
        if obj.document_back:
            previews.append(f'<div><strong>Back:</strong> <a href="{obj.document_back.url}" target="_blank">View</a></div>')
        if obj.selfie_image:
            previews.append(f'<div><strong>Selfie:</strong> <a href="{obj.selfie_image.url}" target="_blank">View</a></div>')
        if obj.proof_of_address:
            previews.append(f'<div><strong>Address:</strong> <a href="{obj.proof_of_address.url}" target="_blank">View</a></div>')
        
        return mark_safe(''.join(previews)) if previews else 'No documents uploaded'
    document_preview.short_description = 'Document Files'
    
    def compliance_summary(self, obj):
        checks = obj.compliance_checks.all()
        if not checks:
            return 'No compliance checks performed'
        
        summary = []
        for check in checks:
            color = 'green' if check.result == 'pass' else 'red' if check.result == 'fail' else 'orange'
            summary.append(
                f'<div style="color: {color};">'
                f'{check.get_check_type_display()}: {check.get_result_display()}'
                f'{f" ({check.confidence_score}%)" if check.confidence_score else ""}'
                f'</div>'
            )
        
        return mark_safe(''.join(summary))
    compliance_summary.short_description = 'Compliance Checks'
    
    def approve_applications(self, request, queryset):
        count = 0
        for application in queryset.filter(status__in=['submitted', 'under_review']):
            application.approve(request.user, "Bulk approved via admin")
            count += 1
        
        self.message_user(request, f'{count} applications approved successfully.')
    approve_applications.short_description = 'Approve selected applications'
    
    def reject_applications(self, request, queryset):
        count = 0
        for application in queryset.filter(status__in=['submitted', 'under_review']):
            application.reject(request.user, "Bulk rejected via admin")
            count += 1
        
        self.message_user(request, f'{count} applications rejected.')
    reject_applications.short_description = 'Reject selected applications'
    
    def flag_for_review(self, request, queryset):
        count = queryset.update(status=KYCApplication.Status.FLAGGED)
        self.message_user(request, f'{count} applications flagged for investigation.')
    flag_for_review.short_description = 'Flag for investigation'


@admin.register(KYCDocument)
class KYCDocumentAdmin(admin.ModelAdmin):
    list_display = ['kyc_application', 'category', 'document_name', 'file_size', 'uploaded_at']
    list_filter = ['category', 'uploaded_at']
    search_fields = ['kyc_application__application_id', 'document_name']
    readonly_fields = ['uploaded_at', 'file_size']
    
    def file_size(self, obj):
        if obj.document_file:
            size = obj.document_file.size
            if size < 1024:
                return f'{size} bytes'
            elif size < 1024 * 1024:
                return f'{size / 1024:.1f} KB'
            else:
                return f'{size / (1024 * 1024):.1f} MB'
        return 'No file'
    file_size.short_description = 'File Size'


@admin.register(KYCReviewNote)
class KYCReviewNoteAdmin(admin.ModelAdmin):
    list_display = ['kyc_application', 'reviewer', 'note_preview', 'is_internal', 'created_at']
    list_filter = ['is_internal', 'created_at']
    search_fields = ['kyc_application__application_id', 'note', 'reviewer__email']
    readonly_fields = ['created_at']
    
    def note_preview(self, obj):
        return obj.note[:100] + '...' if len(obj.note) > 100 else obj.note
    note_preview.short_description = 'Note'


@admin.register(KYCSettings)
class KYCSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ('Auto-Approval Settings', {
            'fields': (
                'enable_auto_approval',
                'auto_approval_countries',
                'max_auto_approval_amount'
            )
        }),
        ('Review Settings', {
            'fields': (
                'require_manual_review_for_high_risk',
                'review_expiry_days'
            )
        }),
        ('Document Requirements', {
            'fields': (
                'require_proof_of_address',
                'require_selfie',
                'require_source_of_funds'
            )
        }),
        ('Notifications', {
            'fields': (
                'notify_on_submission',
                'notify_on_approval',
                'notify_on_rejection',
                'notify_on_expiry'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    readonly_fields = ['created_at', 'updated_at']
    
    def has_add_permission(self, request):
        # Only allow one settings instance
        return not KYCSettings.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        # Don't allow deletion of settings
        return False


@admin.register(ComplianceCheck)
class ComplianceCheckAdmin(admin.ModelAdmin):
    list_display = [
        'kyc_application', 
        'check_type', 
        'result_badge', 
        'confidence_score', 
        'provider', 
        'created_at'
    ]
    list_filter = ['check_type', 'result', 'provider', 'created_at']
    search_fields = ['kyc_application__application_id']
    readonly_fields = ['created_at']
    
    def result_badge(self, obj):
        colors = {
            'pass': '#28a745',
            'fail': '#dc3545',
            'manual_review': '#ffc107',
            'error': '#6c757d'
        }
        color = colors.get(obj.result, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color, obj.get_result_display()
        )
    result_badge.short_description = 'Result'


# Customize admin site header
admin.site.site_header = 'ATC Platform KYC Administration'
admin.site.site_title = 'KYC Admin'
admin.site.index_title = 'KYC Management Dashboard'
