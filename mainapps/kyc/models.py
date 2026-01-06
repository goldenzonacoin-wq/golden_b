import os
import uuid
from datetime import datetime, timedelta
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError
from PIL import Image

from mainapps.accounts.models import Address


def validate_file_size(value):
    """Validate file size is under 5MB"""
    filesize = value.size
    if filesize > 5 * 1024 * 1024:  # 5MB
        raise ValidationError("File size cannot exceed 5MB")


def kyc_document_path(instance, filename):
    """Generate secure path for KYC documents"""
    ext = filename.split('.')[-1]
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_id = str(uuid.uuid4())[:8]
    new_filename = f"kyc_{instance.user.id}_{timestamp}_{unique_id}.{ext}"
    return os.path.join('kyc_documents', str(instance.user.id), new_filename)


class KYCApplication(models.Model):
    """Main KYC application model"""
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SUBMITTED = 'submitted', 'Submitted'
        UNDER_REVIEW = 'under_review', 'Under Review'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        FLAGGED = 'flagged', 'Flagged for Investigation'
        EXPIRED = 'expired', 'Expired'
    
    class DocumentType(models.TextChoices):
        PASSPORT = 'passport', 'Passport'
        DRIVERS_LICENSE = 'drivers_license', 'Driver\'s License'
        NATIONAL_ID = 'national_id', 'National ID Card'
        RESIDENCE_PERMIT = 'residence_permit', 'Residence Permit'
    
    class RiskLevel(models.TextChoices):
        LOW = 'low', 'Low Risk'
        MEDIUM = 'medium', 'Medium Risk'
        HIGH = 'high', 'High Risk'
        CRITICAL = 'critical', 'Critical Risk'
    
    # Basic Information
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='kyc_application'
    )
    application_id = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        help_text="Auto-generated KYC application ID"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )
    risk_level = models.CharField(
        max_length=20,
        choices=RiskLevel.choices,
        default=RiskLevel.LOW
    )
    
    # Personal Information
    full_name = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=16,null=True)
    date_of_birth = models.DateField()
    nationality = models.ForeignKey('cities_light.Country', on_delete=models.PROTECT, related_name='kyc_application', null=True)
    address =models.ForeignKey(Address, on_delete=models.PROTECT, related_name='kyc_application', null=True)
    # Document Information
    document_type = models.CharField(
        max_length=20,
        choices=DocumentType.choices,
        null=True, blank=True
    )
    document_number = models.CharField(max_length=50,blank=True, null=True)
    document_expiry_date = models.DateField(blank=True, null=True,)
    document_issuing_country = models.ForeignKey('cities_light.Country',on_delete=models.PROTECT, blank=True, null=True)
    
    # Document Images
    document_front = models.ImageField(
        upload_to=kyc_document_path,
        validators=[
            FileExtensionValidator(['jpg', 'jpeg', 'png', 'pdf']),
            validate_file_size
        ],
        help_text="Front side of ID document (max 5MB)"
    )
    document_back = models.ImageField(
        upload_to=kyc_document_path,
        validators=[
            FileExtensionValidator(['jpg', 'jpeg', 'png', 'pdf']),
            validate_file_size
        ],
        blank=True,
        null=True,
        help_text="Back side of ID document (if applicable, max 5MB)"
    )
    selfie_image = models.ImageField(
        upload_to=kyc_document_path,
        validators=[
            FileExtensionValidator(['jpg', 'jpeg', 'png']),
            validate_file_size
        ],
        help_text="Selfie with ID document (max 5MB)"
    )
    
    # Proof of Address
    proof_of_address = models.ImageField(
        upload_to=kyc_document_path,
        validators=[
            FileExtensionValidator(['jpg', 'jpeg', 'png', 'pdf']),
            validate_file_size
        ],
        blank=True,
        null=True,
        help_text="Utility bill or bank statement (max 5MB)"
    )
    
    # Additional Information
    occupation = models.CharField(max_length=100, blank=True, null=True)
    employer = models.CharField(max_length=100, blank=True, null=True)
    annual_income_range = models.CharField(
        max_length=50,
        choices=[
            ('0-25k', '$0 - $25,000'),
            ('25k-50k', '$25,000 - $50,000'),
            ('50k-100k', '$50,000 - $100,000'),
            ('100k-250k', '$100,000 - $250,000'),
            ('250k+', '$250,000+'),
        ],
        blank=True,
        null=True
    )
    source_of_funds = models.TextField(
        blank=True,
        null=True,
        help_text="Describe the source of your cryptocurrency funds"
    )
    
    # Blockchain-specific fields
    intended_use = models.TextField(
        help_text="Describe your intended use of ATC tokens",
        blank=True,
        null=True
    )
    crypto_experience = models.CharField(
        max_length=20,
        choices=[
            ('beginner', 'Beginner (< 1 year)'),
            ('intermediate', 'Intermediate (1-3 years)'),
            ('advanced', 'Advanced (3+ years)'),
        ],
        default='beginner',
        null=True, blank=True
        
    )
    other_wallets = models.JSONField(
        default=list,
        help_text="List of other wallet addresses you own",
        null=True, blank=True

    )
    
    # Review Information
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='reviewed_kyc_applications'
    )
    review_notes = models.TextField(blank=True, null=True)
    rejection_reason = models.TextField(blank=True, null=True)
    
    # Timestamps
    submitted_at = models.DateTimeField(blank=True, null=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'kyc_application'
        verbose_name = 'KYC Application'
        verbose_name_plural = 'KYC Applications'
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['application_id']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.application_id:
            self.application_id = self.generate_application_id()
        
        if self.status == self.Status.APPROVED and not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=365)
        
        super().save(*args, **kwargs)
    
    def generate_application_id(self):
        """Generate unique application ID"""
        import random
        import string
        
        while True:
            # Format: KYC-YYYYMMDD-XXXX
            date_part = datetime.now().strftime('%Y%m%d')
            random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            app_id = f"KYC-{date_part}-{random_part}"
            
            if not KYCApplication.objects.filter(application_id=app_id).exists():
                return app_id
    
    @property
    def is_expired(self):
        """Check if KYC approval has expired"""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False
    
    @property
    def days_until_expiry(self):
        """Days until KYC expires"""
        if self.expires_at:
            delta = self.expires_at - timezone.now()
            return max(0, delta.days)
        return None
    
    def approve(self, reviewer, notes=None):
        """Approve KYC application"""
        self.status = self.Status.APPROVED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.review_notes = notes
        self.expires_at = timezone.now() + timedelta(days=365)
        self.save()
        
        # Update user KYC status
        self.user.is_kyc_verified = True
        self.user.save()
    
    def reject(self, reviewer, reason):
        """Reject KYC application"""
        self.status = self.Status.REJECTED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.rejection_reason = reason
        self.save()
        
        # Update user KYC status
        self.user.is_kyc_verified = False
        self.user.save()
    
    def __str__(self):
        return f"{self.application_id} - {self.user.email} - {self.status}"


class KYCDocument(models.Model):
    """Additional KYC documents"""
    
    class DocumentCategory(models.TextChoices):
        IDENTITY = 'identity', 'Identity Document'
        ADDRESS = 'address', 'Proof of Address'
        INCOME = 'income', 'Proof of Income'
        FUNDS = 'funds', 'Source of Funds'
        OTHER = 'other', 'Other'
    
    kyc_application = models.ForeignKey(
        KYCApplication,
        on_delete=models.CASCADE,
        related_name='additional_documents'
    )
    category = models.CharField(
        max_length=20,
        choices=DocumentCategory.choices
    )
    document_name = models.CharField(max_length=200)
    document_file = models.FileField(
        upload_to=kyc_document_path,
        validators=[
            FileExtensionValidator(['jpg', 'jpeg', 'png', 'pdf']),
            validate_file_size
        ]
    )
    description = models.TextField(blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'kyc_document'
        verbose_name = 'KYC Document'
        verbose_name_plural = 'KYC Documents'
    
    def __str__(self):
        return f"{self.kyc_application.application_id} - {self.document_name}"


class KYCReviewNote(models.Model):
    """Review notes and comments for KYC applications"""
    
    kyc_application = models.ForeignKey(
        KYCApplication,
        on_delete=models.CASCADE,
        related_name='kyc_review_notes'
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='kyc_review_notes'
    )
    note = models.TextField()
    is_internal = models.BooleanField(
        default=True,
        help_text="Internal notes not visible to applicant"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'kyc_review_note'
        ordering = ['-created_at']
        verbose_name = 'KYC Review Note'
        verbose_name_plural = 'KYC Review Notes'
    
    def __str__(self):
        return f"{self.kyc_application.application_id} - Note by {self.reviewer.email}"


class KYCSettings(models.Model):
    """Global KYC settings and configuration"""
    
    # Auto-approval settings
    enable_auto_approval = models.BooleanField(default=False)
    auto_approval_countries = models.JSONField(
        default=list,
        help_text="List of countries eligible for auto-approval"
    )
    max_auto_approval_amount = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        default=1000,
        help_text="Maximum token amount for auto-approval"
    )
    
    # Review settings
    require_manual_review_for_high_risk = models.BooleanField(default=True)
    review_expiry_days = models.PositiveIntegerField(
        default=365,
        help_text="Days until KYC approval expires"
    )
    
    # Document requirements
    require_proof_of_address = models.BooleanField(default=True)
    require_selfie = models.BooleanField(default=True)
    require_source_of_funds = models.BooleanField(default=False)
    
    # Notification settings
    notify_on_submission = models.BooleanField(default=True)
    notify_on_approval = models.BooleanField(default=True)
    notify_on_rejection = models.BooleanField(default=True)
    notify_on_expiry = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'kyc_settings'
        verbose_name = 'KYC Settings'
        verbose_name_plural = 'KYC Settings'
    
    def save(self, *args, **kwargs):
        # Ensure only one settings instance exists
        if not self.pk and KYCSettings.objects.exists():
            raise ValidationError('Only one KYC Settings instance is allowed')
        super().save(*args, **kwargs)
    
    def __str__(self):
        return "KYC Settings"


class ComplianceCheck(models.Model):
    """Automated compliance checks for KYC applications"""
    
    class CheckType(models.TextChoices):
        SANCTIONS = 'sanctions', 'Sanctions Screening'
        PEP = 'pep', 'Politically Exposed Person'
        ADVERSE_MEDIA = 'adverse_media', 'Adverse Media'
        DOCUMENT_VERIFICATION = 'document_verification', 'Document Verification'
        FACE_MATCH = 'face_match', 'Face Matching'
        ADDRESS_VERIFICATION = 'address_verification', 'Address Verification'
    
    class Result(models.TextChoices):
        PASS = 'pass', 'Pass'
        FAIL = 'fail', 'Fail'
        MANUAL_REVIEW = 'manual_review', 'Manual Review Required'
        ERROR = 'error', 'Error'
    
    kyc_application = models.ForeignKey(
        KYCApplication,
        on_delete=models.CASCADE,
        related_name='compliance_checks'
    )
    check_type = models.CharField(
        max_length=30,
        choices=CheckType.choices
    )
    result = models.CharField(
        max_length=20,
        choices=Result.choices
    )
    confidence_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Confidence score (0-100)"
    )
    details = models.JSONField(
        default=dict,
        help_text="Detailed check results"
    )
    provider = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Third-party service provider"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'kyc_compliance_check'
        unique_together = ['kyc_application', 'check_type']
        verbose_name = 'Compliance Check'
        verbose_name_plural = 'Compliance Checks'
    
    def __str__(self):
        return f"{self.kyc_application.application_id} - {self.check_type} - {self.result}"



def payment_receipt_path(instance, filename):
    """Keep payment receipts organized by user and timestamp."""
    ext = filename.split('.')[-1]
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    unique = uuid.uuid4().hex[:8]
    new_filename = f"receipt_{instance.user.id}_{timestamp}_{unique}.{ext}"
    return os.path.join('payment_receipts', str(instance.user.id), new_filename)


class KYCPayment(models.Model):
    """Records one-time Flutterwave payments for KYC."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        REVIEW = 'review', 'Review'
        SUCCESSFUL = 'successful', 'Successful'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='kyc_payments'
    )
    tx_ref = models.CharField(max_length=120, unique=True)
    flw_ref = models.CharField(max_length=120, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='USD')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    payment_link = models.URLField(blank=True, null=True)
    init_payload = models.JSONField(default=dict, blank=True)
    last_webhook_payload = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    payment_receipt = models.FileField(upload_to=payment_receipt_path, blank=True, null=True)
    payment_confirmed = models.BooleanField(default=False)
    payment_rejection_reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'kyc_payment'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['tx_ref']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.tx_ref} - {self.status}"

    @property
    def is_successful(self):
        return self.status == self.Status.SUCCESSFUL

