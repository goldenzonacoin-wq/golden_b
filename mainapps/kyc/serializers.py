from rest_framework import serializers
from django.core.files.base import ContentFile
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
            'risk_level', 'full_name', 'date_of_birth', 'nationality','address',
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
        return attrs
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class KYCApplicationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating KYC applications"""
    
    class Meta:
        model = KYCApplication
        fields = (
            'full_name', 'date_of_birth', 'nationality',
            'document_type', 'document_number', 'document_expiry_date',
            'document_issuing_country', 'occupation', 'employer',
            'annual_income_range', 'source_of_funds', 'intended_use',
            'crypto_experience', 'other_wallets','address','phone_number'
        )
    
    # def create(self, validated_data):
    #     validated_data['user'] = self.context['request'].user
    #     return super().create(validated_data)


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
