import re
from rest_framework import serializers
from django.utils import timezone
from cities_light.models import Country
from django.core.files.base import ContentFile
from mainapps.accounts.models import Address
from .models import (
    KYCApplication, KYCDocument, KYCReviewNote, 
    ComplianceCheck, KYCSettings, KYCPayment
)


class KYCApplicationSerializer(serializers.ModelSerializer):
    """Serializer for KYC applications"""
    user_email = serializers.EmailField(source='user.email', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    document_type_display = serializers.CharField(source='get_document_type_display', read_only=True)
    days_until_expiry = serializers.ReadOnlyField()
    is_expired = serializers.ReadOnlyField()
    nationality_name = serializers.ReadOnlyField(source='nationality.name')
    
    class Meta:
        model = KYCApplication
        fields = (
            'id', 'application_id', 'user_email', 'status', 'status_display',
            'risk_level', 'first_name', 'middle_name', 'last_name', 'full_name',
            'date_of_birth', 'nationality','address', 'origin_details',
            'document_number', 'document_expiry_date', 'document_issuing_country',
            'document_front', 'document_back', 'selfie_image', 'proof_of_address',
            'occupation', 'employer', 'annual_income_range', 'source_of_funds',
            'intended_use', 'crypto_experience', 'other_wallets','document_type',
            'submitted_at', 'reviewed_at', 'expires_at', 'days_until_expiry',
            'is_expired', 'created_at', 'updated_at','nationality_name','document_type_display','phone_number'
        )
        read_only_fields = (
            'id', 'application_id', 'user_email', 'status_display',
            'document_type_display', 'submitted_at', 'reviewed_at',
            'expires_at', 'days_until_expiry', 'is_expired',
            'created_at', 'updated_at','nationality_name'
        )
    
    def validate(self, attrs):
        # Ensure user can only have one active application
        user = self.context['request'].user
        if not self.instance:  # Creating new application
            existing = KYCApplication.objects.filter(
                user=user,
                status__in=['draft', 'submitted', 'under_review']
            ).exists()
            if existing:
                raise serializers.ValidationError(
                    "You already have an active KYC application"
                )
        first_name = attrs.get('first_name') or getattr(self.instance, 'first_name', None)
        middle_name = attrs.get('middle_name') or getattr(self.instance, 'middle_name', None)
        last_name = attrs.get('last_name') or getattr(self.instance, 'last_name', None)
        if first_name or middle_name or last_name:
            name_parts = [first_name, middle_name, last_name]
            attrs['full_name'] = " ".join([part for part in name_parts if part])
        return attrs

    def validate_date_of_birth(self, value):
        if not value:
            return value
        if value > timezone.now().date():
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        return value

    def validate_phone_number(self, value):
        if value in (None, ""):
            return value
        phone = value.strip()
        if not phone:
            return value
        if not re.match(r"^\+?[0-9]{7,15}$", phone):
            raise serializers.ValidationError(
                "Enter a valid phone number with country code (digits only)."
            )
        return phone

    def validate_document_expiry_date(self, value):
        if not value:
            return value
        if value < timezone.now().date():
            raise serializers.ValidationError("Your ID appears to be expired; upload a valid document.")
        return value

    def validate_document_number(self, value):
        if not value:
            return value
        cleaned = value.strip().upper()
        if len(cleaned) < 5:
            raise serializers.ValidationError("ID number looks too short—double check and re-enter.")
        if not re.match(r"^[A-Za-z0-9\\-\\/]+$", cleaned):
            raise serializers.ValidationError("Use only letters, numbers, dashes or slashes for the ID number.")
        qs = KYCApplication.objects.filter(document_number__iexact=cleaned)
        user = self.context['request'].user if self.context.get('request') else None
        if user:
            qs = qs.exclude(user=user)
        if qs.exists():
            raise serializers.ValidationError("This document number is already associated with another application.")
        return cleaned

    def validate_source_of_funds(self, value):
        if value is None:
            return value
        trimmed = value.strip()
        if not trimmed:
            return trimmed
        if len(trimmed) < 10:
            raise serializers.ValidationError("Add a short description of where your funds come from.")
        return trimmed

    def validate_intended_use(self, value):
        if value is None:
            return value
        trimmed = value.strip()
        if not trimmed:
            return trimmed
        if len(trimmed) < 10:
            raise serializers.ValidationError("Describe how you plan to use E-ATC in a few words.")
        return trimmed

    def validate_other_wallets(self, value):
        cleaned = []
        for wallet in value or []:
            wallet_trimmed = wallet.strip()
            if not wallet_trimmed:
                continue
            if not wallet_trimmed.startswith('0x') or len(wallet_trimmed) not in [42, 66]:
                raise serializers.ValidationError("Wallet addresses should start with 0x and be a valid length.")
            cleaned.append(wallet_trimmed)
        return cleaned
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class KYCApplicationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating KYC applications"""

    first_name = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True,
        help_text="Your legal first name as it appears on your ID.",
        error_messages={
            "required": "First name is required to start your KYC.",
            "blank": "Enter your first name exactly as it is on your ID.",
        },
    )
    middle_name = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True,
        help_text="Optional middle name (leave empty if not on your ID).",
    )
    last_name = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True,
        help_text="Your legal surname as it appears on your ID.",
        error_messages={
            "required": "Last name is required to start your KYC.",
            "blank": "Enter your last name exactly as it is on your ID.",
        },
    )
    date_of_birth = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Date of birth in YYYY-MM-DD format.",
        error_messages={
            "required": "Your date of birth is required to verify your age.",
        },
    )
    nationality = serializers.PrimaryKeyRelatedField(
        queryset=Country.objects.all(),
        required=False,
        allow_null=True,
        help_text="Country of citizenship shown on your passport/ID.",
        error_messages={"required": "Select the country that issued your ID."},
    )
    phone_number = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=20,
        help_text="Include country code (e.g. +2348012345678).",
    )
    address = serializers.PrimaryKeyRelatedField(
        queryset=Address.objects.all(),
        required=False,
        allow_null=True,
        help_text="Select the saved residential address that matches your ID.",
        error_messages={"required": "Residential address is required."},
    )
    origin_details = serializers.PrimaryKeyRelatedField(
        queryset=Address.objects.all(),
        required=False,
        allow_null=True,
        help_text="Origin address (if different from your current residence).",
    )
    document_type = serializers.ChoiceField(
        choices=KYCApplication.DocumentType.choices,
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Type of ID you will upload (passport, driver’s license, etc).",
        error_messages={"required": "Choose the ID document you are submitting."},
    )
    document_number = serializers.CharField(
        max_length=50,
        required=False,
        allow_blank=True,
        help_text="ID number exactly as printed on your document.",
    )
    document_expiry_date = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Expiry date on your ID (YYYY-MM-DD).",
    )
    document_issuing_country = serializers.PrimaryKeyRelatedField(
        queryset=Country.objects.all(),
        required=False,
        allow_null=True,
        help_text="Country or authority that issued the ID.",
    )
    occupation = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Your current job title (optional).",
    )
    employer = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Name of your employer or business (optional).",
    )
    annual_income_range = serializers.ChoiceField(
        choices=KYCApplication._meta.get_field("annual_income_range").choices,
        required=False,
        allow_blank=True,
        help_text="Approximate annual income band (optional but helps risk checks).",
    )
    source_of_funds = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        help_text="Describe where your funds come from (e.g. salary, business revenue).",
    )
    intended_use = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        help_text="How you plan to use E-ATC (e.g. staking, trading, payments).",
    )
    crypto_experience = serializers.ChoiceField(
        choices=KYCApplication._meta.get_field("crypto_experience").choices,
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Your experience level with crypto (for suitability checks).",
    )
    other_wallets = serializers.ListField(
        child=serializers.CharField(max_length=120, allow_blank=True),
        required=False,
        allow_empty=True,
        allow_null=True,
        help_text="List any other wallet addresses you own (leave empty if none).",
    )

    class Meta:
        model = KYCApplication
        fields = (
            'first_name', 'middle_name', 'last_name', 'date_of_birth', 'nationality',
            'document_type', 'document_number', 'document_expiry_date',
            'document_issuing_country', 'occupation', 'employer',
            'annual_income_range', 'source_of_funds', 'intended_use',
            'crypto_experience', 'other_wallets', 'address', 'origin_details', 'phone_number'
        )
    
    def validate_date_of_birth(self, value):
        if not value:
            return value
        if value > timezone.now().date():
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        return value

    def validate_phone_number(self, value):
        if value in (None, ""):
            return value
        phone = value.strip()
        if not phone:
            return value
        if not re.match(r"^\+?[0-9]{7,15}$", phone):
            raise serializers.ValidationError(
                "Enter a valid phone number with country code (digits only)."
            )
        return phone

    def validate_document_expiry_date(self, value):
        if not value:
            return value
        if value < timezone.now().date():
            raise serializers.ValidationError("Your ID appears to be expired; upload a valid document.")
        return value

    def validate_document_number(self, value):
        if not value:
            return value
        cleaned = value.strip().upper()
        if len(cleaned) < 5:
            raise serializers.ValidationError("ID number looks too short—double check and re-enter.")
        if not re.match(r"^[A-Za-z0-9\\-\\/]+$", cleaned):
            raise serializers.ValidationError("Use only letters, numbers, dashes or slashes for the ID number.")
        qs = KYCApplication.objects.filter(document_number__iexact=cleaned)
        user = self.context['request'].user if self.context.get('request') else None
        if user:
            qs = qs.exclude(user=user)
        if qs.exists():
            raise serializers.ValidationError("This document number is already associated with another application.")
        return cleaned

    def validate_source_of_funds(self, value):
        if value is None:
            return value
        trimmed = value.strip()
        if not trimmed:
            return trimmed
        if len(trimmed) < 10:
            raise serializers.ValidationError("Add a short description of where your funds come from.")
        return trimmed

    def validate_intended_use(self, value):
        if value is None:
            return value
        trimmed = value.strip()
        if not trimmed:
            return trimmed
        if len(trimmed) < 10:
            raise serializers.ValidationError("Describe how you plan to use E-ATC in a few words.")
        return trimmed

    def validate_other_wallets(self, value):
        cleaned = []
        for wallet in value or []:
            wallet_trimmed = wallet.strip()
            if not wallet_trimmed:
                continue
            if not wallet_trimmed.startswith('0x') or len(wallet_trimmed) not in [42, 66]:
                raise serializers.ValidationError("Wallet addresses should start with 0x and be a valid length.")
            cleaned.append(wallet_trimmed)
        return cleaned

    def validate(self, attrs):
        first_name = attrs.get('first_name')
        middle_name = attrs.get('middle_name')
        last_name = attrs.get('last_name')
        if first_name or middle_name or last_name:
            name_parts = [first_name, middle_name, last_name]
            attrs['full_name'] = " ".join([part for part in name_parts if part])
        return attrs


class KYCDocumentUploadSerializer(serializers.ModelSerializer):
    """Serializer for uploading KYC documents"""
    
    class Meta:
        model = KYCApplication
        fields = ('document_front', 'document_back', 'selfie_image', 'proof_of_address')
    
    def validate_document_front(self, value):
        if value and value.size > 5 * 1024 * 1024:  # 5MB
            raise serializers.ValidationError("File size cannot exceed 5MB")
        return value
    
    def validate_document_back(self, value):
        if value and value.size > 5 * 1024 * 1024:  # 5MB
            raise serializers.ValidationError("File size cannot exceed 5MB")
        return value
    
    def validate_selfie_image(self, value):
        if value and value.size > 5 * 1024 * 1024:  # 5MB
            raise serializers.ValidationError("File size cannot exceed 5MB")
        return value
    
    def validate_proof_of_address(self, value):
        if value and value.size > 5 * 1024 * 1024:  # 5MB
            raise serializers.ValidationError("File size cannot exceed 5MB")
        return value


class KYCApplicationSubmitSerializer(serializers.Serializer):
    """Serializer for submitting KYC applications"""
    terms_accepted = serializers.BooleanField()
    data_processing_consent = serializers.BooleanField()
    
    def validate_terms_accepted(self, value):
        if not value:
            raise serializers.ValidationError("You must accept the terms and conditions")
        return value
    
    def validate_data_processing_consent(self, value):
        if not value:
            raise serializers.ValidationError("You must consent to data processing")
        return value


class KYCDocumentSerializer(serializers.ModelSerializer):
    """Serializer for additional KYC documents"""
    
    class Meta:
        model = KYCDocument
        fields = (
            'id', 'category', 'document_name', 'document_file',
            'description', 'uploaded_at'
        )
        read_only_fields = ('id', 'uploaded_at')
    
    def create(self, validated_data):
        validated_data['kyc_application'] = self.context['kyc_application']
        return super().create(validated_data)


class KYCReviewNoteSerializer(serializers.ModelSerializer):
    """Serializer for KYC review notes"""
    reviewer_name = serializers.CharField(source='reviewer.get_full_name', read_only=True)
    
    class Meta:
        model = KYCReviewNote
        fields = (
            'id', 'note', 'is_internal', 'reviewer_name', 'created_at'
        )
        read_only_fields = ('id', 'reviewer_name', 'created_at')
    
    def create(self, validated_data):
        validated_data['kyc_application'] = self.context['kyc_application']
        validated_data['reviewer'] = self.context['request'].user
        return super().create(validated_data)


class ComplianceCheckSerializer(serializers.ModelSerializer):
    """Serializer for compliance checks"""
    check_type_display = serializers.CharField(source='get_check_type_display', read_only=True)
    result_display = serializers.CharField(source='get_result_display', read_only=True)
    
    class Meta:
        model = ComplianceCheck
        fields = (
            'id', 'check_type', 'check_type_display', 'result', 'result_display',
            'confidence_score', 'details', 'provider', 'created_at'
        )
        read_only_fields = ('id', 'check_type_display', 'result_display', 'created_at')


class KYCApplicationReviewSerializer(serializers.ModelSerializer):
    """Serializer for reviewing KYC applications (admin only)"""
    
    class Meta:
        model = KYCApplication
        fields = ('status', 'review_notes', 'rejection_reason')
    
    def validate_status(self, value):
        if value not in ['approved', 'rejected', 'flagged', 'under_review']:
            raise serializers.ValidationError("Invalid status for review")
        return value
    
    def validate(self, attrs):
        if attrs.get('status') == 'rejected' and not attrs.get('rejection_reason'):
            raise serializers.ValidationError(
                "Rejection reason is required when rejecting an application"
            )
        return attrs
    
    def update(self, instance, validated_data):
        status = validated_data.get('status')
        reviewer = self.context['request'].user
        
        if status == 'approved':
            instance.approve(reviewer, validated_data.get('review_notes'))
        elif status == 'rejected':
            instance.reject(reviewer, validated_data.get('rejection_reason'))
        else:
            instance.status = status
            instance.reviewed_by = reviewer
            instance.review_notes = validated_data.get('review_notes')
            instance.save()
        
        return instance


class KYCSettingsSerializer(serializers.ModelSerializer):
    """Serializer for KYC settings"""
    
    class Meta:
        model = KYCSettings
        fields = (
            'enable_auto_approval', 'auto_approval_countries',
            'max_auto_approval_amount', 'require_manual_review_for_high_risk',
            'review_expiry_days', 'require_proof_of_address',
            'require_selfie', 'require_source_of_funds',
            'notify_on_submission', 'notify_on_approval',
            'notify_on_rejection', 'notify_on_expiry'
        )


class KYCPaymentSerializer(serializers.ModelSerializer):
    """Serializer for initiating and viewing KYC payments"""
    is_successful = serializers.BooleanField(read_only=True)

    class Meta:
        model = KYCPayment
        fields = (
            'id', 'tx_ref', 'flw_ref', 'amount', 'currency', 'status',
            'payment_link', 'paid_at', 'payment_receipt', 'payment_confirmed',
            'payment_rejection_reason', 'created_at', 'updated_at', 'is_successful'
        )
        read_only_fields = (
            'id', 'tx_ref', 'flw_ref', 'amount', 'currency', 'status',
            'payment_link', 'paid_at', 'payment_receipt', 'payment_confirmed',
            'payment_rejection_reason', 'created_at', 'updated_at', 'is_successful'
        )


class KYCPaymentInitiateSerializer(serializers.Serializer):
    """Serializer used when starting a Flutterwave payment."""
    redirect_url = serializers.URLField(
        required=False,
        help_text="Where Flutterwave should redirect the user after payment."
    )
    currency = serializers.CharField(
        required=False,
        max_length=10,
        help_text="Preferred payment currency (e.g. USD, NGN, GHS)."
    )

    def validate_currency(self, value):
        value = value.upper()
        if not value.isalpha():
            raise serializers.ValidationError("Currency must contain only alphabetic characters.")
        return value


class KYCStatsSerializer(serializers.Serializer):
    """Serializer for KYC statistics"""
    total_applications = serializers.IntegerField()
    pending_applications = serializers.IntegerField()
    approved_applications = serializers.IntegerField()
    rejected_applications = serializers.IntegerField()
    flagged_applications = serializers.IntegerField()
    approval_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    average_review_time_hours = serializers.DecimalField(max_digits=10, decimal_places=2)
    applications_by_country = serializers.DictField()
    applications_by_month = serializers.DictField()


class DocumentNumberCheckSerializer(serializers.Serializer):
    """Lightweight serializer for validating document number uniqueness on the fly."""

    document_number = serializers.CharField(
        max_length=50,
        required=True,
        allow_blank=True,
        help_text="ID number exactly as printed on your document.",
        error_messages={
            "required": "Enter the ID number from your document.",
            "blank": "ID number cannot be empty.",
        },
    )
    document_type = serializers.ChoiceField(
        choices=KYCApplication.DocumentType.choices,
        required=True,
        help_text="Type of ID you will upload (passport, driver’s license, etc).",
    )
    document_issuing_country = serializers.PrimaryKeyRelatedField(
        queryset=Country.objects.all(),
        required=True,
        help_text="Country or authority that issued the ID.",
    )
    current_application_id = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Existing application ID to exclude (when editing).",
    )

    def validate_document_number(self, value):
        cleaned = value.strip().upper()
        if len(cleaned) < 5:
            raise serializers.ValidationError("ID number looks too short—double check and re-enter.")
        if not re.match(r"^[A-Za-z0-9\\-\\/]+$", cleaned):
            raise serializers.ValidationError("Use only letters, numbers, dashes or slashes for the ID number.")
        return cleaned

    def validate(self, attrs):
        number = attrs.get("document_number")
        current_id = attrs.get("current_application_id")

        qs = KYCApplication.objects.filter(document_number__iexact=number)
        if current_id:
            qs = qs.exclude(application_id=current_id)

        attrs["duplicate_ids"] = list(qs.values_list("application_id", flat=True))
        attrs["is_unique"] = not bool(attrs["duplicate_ids"])
        return attrs
