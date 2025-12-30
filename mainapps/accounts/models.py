import os
import random
from datetime import datetime
from PIL import Image
from django.db import models
from django.urls import reverse
from django.contrib.auth.models import AbstractUser, BaseUserManager, PermissionsMixin
from django.conf import settings
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
from .validators import validate_city, validate_city_belongs_to_sub_region, validate_country, validate_postal_code, validate_region, validate_region_belongs_to_country, validate_sub_region
from cities_light.models import Country, Region, SubRegion,City


def validate_wallet_address(value):
    """Validate Ethereum-style wallet address"""
    if not value.startswith('0x') or len(value) != 42:
        raise ValidationError('Invalid wallet address format')


def validate_adult(value):
    """Validate user is at least 18 years old"""
    from datetime import date
    today = date.today()
    age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
    if age < 18:
        raise ValidationError('You must be at least 18 years old')


PREFER_NOT_TO_SAY = "not_to_mention"
SEX_CHOICES = (
    ("male", _("Male")),
    ("female", _("Female")),
    (PREFER_NOT_TO_SAY, _("Prefer not to say")),
)

MEMBERSHIP_TIERS = (
    ("bronze", _("Bronze Member")),
    ("silver", _("Silver Member")),
    ("gold", _("Gold Member")),
    ("platinum", _("Platinum Member")),
    ("diamond", _("Diamond Member")),
)

ROLE_CHOICES = (
    ("community_member", _("Community Member")),
    ("investor", _("Investor")),
    ("developer", _("Developer")),
    ("validator", _("Validator")),
    ("moderator", _("Moderator")),
    ("admin", _("Administrator")),
)


def profile_image_path(instance, filename):
    """Generate path for profile images with timestamp"""
    ext = filename.split('.')[-1]
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    username = instance.user.username if hasattr(instance, 'user') and instance.user else 'unknown'
    safe_username = username.replace('@', '_').replace('.', '_')
    new_filename = f"{timestamp}_{safe_username}.{ext}"
    return os.path.join('profile_images', new_filename)


class Address(models.Model):
    
    country = models.ForeignKey(
        Country, 
        on_delete=models.CASCADE,
        verbose_name=_('Country'),
        null=True,
    )
    region = models.ForeignKey(
        Region, 
        on_delete=models.CASCADE,
        verbose_name=_('Region/State'),
        null=True,
    )
    subregion = models.ForeignKey(
        SubRegion, 
        on_delete=models.CASCADE,
        verbose_name=_('Sub region/LGA'),
        null=True,
    )
    city = models.ForeignKey(
        City,
        on_delete=models.CASCADE,
        verbose_name=_('City/Town'),
        null=True,
     )
    apt_number = models.PositiveIntegerField(
        verbose_name=_('Apartment number'),
        null=True,
        blank=True
    )
    street_number = models.PositiveIntegerField(
        verbose_name=_('Street number'),
        null=True,
        blank=True
    )
    street = models.CharField(max_length=255,blank=False,null=True)

    postal_code = models.CharField(
        max_length=10,
        verbose_name=_('Postal code'),
        help_text=_('Postal code'),
        blank=True,
        null=True,
        validators=[validate_postal_code]
    )

    def __str__(self):
        return f'{self.street}, {self.city}, {self.region}, {self.country}'
    def clean(self):
        if self.country:
            validate_country(self.country.id)
            if self.region:
                validate_region(self.region.id)
                if self.subregion:
                    validate_sub_region(self.subregion.id)
                    if self.city:
                        validate_city(self.city.id)
                        validate_region_belongs_to_country(self.region.id, self.country.id)
                        validate_city_belongs_to_sub_region(self.city.id, self.subregion.id)


class CustomUserManager(BaseUserManager):
    """Custom user manager for email-based authentication"""
    
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_verified", True)

        if not extra_fields.get("is_staff"):
            raise ValueError("Superuser must have is_staff=True.")
        if not extra_fields.get("is_superuser"):
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser, PermissionsMixin):
    """Custom user model for ATC blockchain project"""
    
    email = models.EmailField(unique=True, blank=False, null=False)
    username = models.CharField(max_length=150, unique=True, blank=True)
    
    # Personal Information
    sex = models.CharField(
        max_length=20,
        choices=SEX_CHOICES,
        default=PREFER_NOT_TO_SAY,
        blank=True,
        null=True
    )
    date_of_birth = models.DateField(
        validators=[validate_adult],
        verbose_name='Date Of Birth',
        help_text='You must be above 18 years of age.',
        blank=True,
        null=True,
    )
    phone_number = models.CharField(
        max_length=20,
        validators=[RegexValidator(r'^\+?1?\d{9,15}$')],
        blank=True,
        null=True
    )
    
    # Blockchain-specific fields
    wallet_address = models.CharField(
        max_length=42,
        validators=[validate_wallet_address],
        unique=True,
        blank=True,
        null=True,
        help_text="Ethereum-compatible wallet address"
    )
    
    # Status fields
    is_verified = models.BooleanField(default=False)
    is_kyc_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    
    # ATC-specific roles
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="community_member"
    )
    membership_tier = models.CharField(
        max_length=20,
        choices=MEMBERSHIP_TIERS,
        default="bronze"
    )
    
    # Token holdings (for reference, actual balances come from blockchain)
    atc_balance = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        default=0,
        help_text="Cached ATC token balance"
    )
    organisation = models.ForeignKey(
        'Organisation',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='members'
    ) 
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login_ip = models.GenericIPAddressField(blank=True, null=True)
    address = models.OneToOneField(
        Address,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='user'
    )
    
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ['first_name', 'last_name']
    objects = CustomUserManager()
    
    class Meta:
        db_table = 'accounts_user'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['wallet_address']),
            models.Index(fields=['is_verified', 'is_kyc_verified']),
        ]
    
    @property
    def get_full_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.email
    
    @property
    def is_whale(self):
        """Check if user is a whale (holds >5% of total supply)"""
        # This would be calculated based on actual blockchain data
        return self.atc_balance > 50000000  # 5% of 1B tokens
    
    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.email
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.get_full_name


class UserProfile(models.Model):
    """Extended user profile for ATC community members"""
    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )
       
    # Profile Information
    bio = models.TextField(max_length=500, blank=True, null=True)
    profile_image = models.ImageField(
        upload_to=profile_image_path,
        blank=True,
        null=True
    )
    cover_image = models.ImageField(
        upload_to='cover_images/',
        blank=True,
        null=True
    )
    
    # Social Links
    twitter_handle = models.CharField(max_length=50, blank=True, null=True)
    linkedin_profile = models.URLField(blank=True, null=True)
    github_profile = models.URLField(blank=True, null=True)
    discord_handle = models.CharField(max_length=50, blank=True, null=True)
    telegram_handle = models.CharField(max_length=50, blank=True, null=True)
    
    # Professional Information
    occupation = models.CharField(max_length=100, blank=True, null=True)
    company = models.CharField(max_length=100, blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    
    
    # Community Engagement
    reputation_score = models.PositiveIntegerField(default=0)
    contribution_points = models.PositiveIntegerField(default=0)
    referral_code = models.CharField(
        max_length=10,
        unique=True,
        blank=True,
        null=True
    )
    referred_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='referrals'
    )
    
    # Privacy Settings
    show_wallet_address = models.BooleanField(default=False)
    show_token_balance = models.BooleanField(default=False)
    allow_direct_messages = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'accounts_userprofile'
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'
    
    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = self.generate_referral_code()
        super().save(*args, **kwargs)
    
    def generate_referral_code(self):
        """Generate unique referral code"""
        import string
        import random
        
        while True:
            code = ''.join(random.choices(
                string.ascii_uppercase + string.digits, 
                k=8
            ))
            if not UserProfile.objects.filter(referral_code=code).exists():
                return code
    
    def __str__(self):
        return f"{self.user.get_full_name}'s Profile"


class VerificationCode(models.Model):
    """Email/SMS verification codes"""
    
    VERIFICATION_TYPES = (
        ('email', 'Email Verification'),
        ('sms', 'SMS Verification'),
        ('2fa', 'Two-Factor Authentication'),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    verification_type = models.CharField(
        max_length=10,
        choices=VERIFICATION_TYPES,
        default='email'
    )
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'accounts_verificationcode'
        indexes = [
            models.Index(fields=['user', 'verification_type',]),
        ]
    
    def save(self, *args, **kwargs):
        self.code = ''.join([str(random.randint(1, 9)) for _ in range(6)])
        self.expires_at = timezone.now() + timezone.timedelta(minutes=20)
        super().save(*args, **kwargs)
    
    def is_valid(self):
        return timezone.now() < self.expires_at
    
    def __str__(self):
        return f"{self.user.email} - {self.verification_type} - {self.code}"


class UserActivity(models.Model):
    """Track user activities for security and analytics"""
    
    ACTIVITY_TYPES = (
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('password_change', 'Password Change'),
        ('profile_update', 'Profile Update'),
        ('kyc_submission', 'KYC Submission'),
        ('wallet_connect', 'Wallet Connection'),
        ('token_transfer', 'Token Transfer'),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    description = models.TextField(blank=True, null=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'accounts_useractivity'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'activity_type']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.activity_type} - {self.created_at}"


class Organisation(models.Model):
    name = models.CharField(max_length=255,)
    leader = models.OneToOneField(User, on_delete=models.SET_NULL,related_name='organization', null=True, blank=True,)
    description = models.TextField(blank=True,)
    website = models.URLField(blank=True)
    logo = models.ImageField(upload_to='organisation_logos/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    physical_address = models.OneToOneField(
        Address,
        on_delete=models.PROTECT,
        null=True,
        related_name='organisation'
        )
    wallet_address = models.CharField(
        max_length=42,
        validators=[validate_wallet_address],
        unique=True,
        blank=True,
        null=True,
        help_text="Ethereum-compatible wallet address"
    )


    class Meta:
        db_table = 'accounts_organisation'
        verbose_name = 'Organisation'
        verbose_name_plural = 'Organisations'
    
    def __str__(self):
        return self.name

