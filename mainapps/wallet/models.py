from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import RegexValidator
from django.utils import timezone
from cryptography.fernet import Fernet
from django.conf import settings
import secrets
import hashlib

User = get_user_model()

class WalletSession(models.Model):
    """Temporary wallet session for frontend wallet access"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wallet_sessions')
    session_token = models.CharField(max_length=64, unique=True)
    encrypted_private_key = models.TextField()  # Temporarily encrypted for session
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'wallet_session'
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['session_token']),
            models.Index(fields=['expires_at']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.session_token:
            self.session_token = secrets.token_urlsafe(32)
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(hours=24)
        super().save(*args, **kwargs)
    
    def is_valid(self):
        return self.is_active and timezone.now() < self.expires_at
    
    def __str__(self):
        return f"Wallet session for {self.user.email}"


class WalletCreationLog(models.Model):
    """Log wallet creation events for security auditing"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wallet_creation_logs')
    wallet_address = models.CharField(max_length=42)
    recovery_phrase_hash = models.CharField(max_length=64)  # SHA256 hash for verification
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'wallet_creation_log'
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"Wallet created for {self.user.email} at {self.created_at}"


class WalletRecoveryAttempt(models.Model):
    """Track wallet recovery attempts for security"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recovery_attempts')
    ip_address = models.GenericIPAddressField()
    success = models.BooleanField(default=False)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'wallet_recovery_attempt'
        indexes = [
            models.Index(fields=['user', 'success']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        status = "Success" if self.success else "Failed"
        return f"Recovery attempt for {self.user.email} - {status}"
