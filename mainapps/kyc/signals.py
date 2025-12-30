from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from .models import KYCApplication, ComplianceCheck


@receiver(pre_save, sender=KYCApplication)
def update_submission_timestamp(sender, instance, **kwargs):
    """Update submitted_at when status changes to submitted"""
    if instance.pk:
        try:
            old_instance = KYCApplication.objects.get(pk=instance.pk)
            if (old_instance.status != 'submitted' and 
                instance.status == 'submitted' and 
                not instance.submitted_at):
                instance.submitted_at = timezone.now()
        except KYCApplication.DoesNotExist:
            pass


@receiver(post_save, sender=KYCApplication)
def trigger_compliance_checks(sender, instance, created, **kwargs):
    """Trigger automated compliance checks when application is submitted"""
    if instance.status == 'submitted' and not instance.compliance_checks.exists():
        # Create placeholder compliance checks
        check_types = [
            'sanctions', 'pep', 'adverse_media', 
            'document_verification', 'face_match'
        ]
        
        for check_type in check_types:
            ComplianceCheck.objects.create(
                kyc_application=instance,
                check_type=check_type,
                result='manual_review',  # Default to manual review
                details={'status': 'pending_review'}
            )


@receiver(post_save, sender=KYCApplication)
def update_user_kyc_status(sender, instance, **kwargs):
    """Update user's KYC verification status"""
    if instance.status == 'approved':
        instance.user.is_kyc_verified = True
        instance.user.save()
    elif instance.status in ['rejected', 'expired']:
        instance.user.is_kyc_verified = False
        instance.user.save()
