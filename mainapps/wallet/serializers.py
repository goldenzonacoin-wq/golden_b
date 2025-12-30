from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import WalletSession, WalletCreationLog, WalletRecoveryAttempt

User = get_user_model()

class WalletCreateSerializer(serializers.Serializer):
    """Serializer for wallet creation request"""
    
    def validate(self, attrs):
        user = self.context['request'].user
        if user.wallet_address:
            raise serializers.ValidationError("User already has a wallet")
        return attrs


class WalletRecoverySerializer(serializers.Serializer):
    """Serializer for wallet recovery using mnemonic phrase"""
    
    recovery_phrase = serializers.CharField(
        max_length=500,
        help_text="12 or 24 word recovery phrase"
    )
    
    def validate_recovery_phrase(self, value):
        words = value.strip().split()
        if len(words) not in [12, 24]:
            raise serializers.ValidationError(
                "Recovery phrase must be 12 or 24 words"
            )
        return value


class WalletSessionSerializer(serializers.ModelSerializer):
    """Serializer for wallet session data"""
    
    class Meta:
        model = WalletSession
        fields = ['session_token', 'expires_at', 'created_at', 'last_used']
        read_only_fields = ['session_token', 'expires_at', 'created_at', 'last_used']


class WalletInfoSerializer(serializers.Serializer):
    """Serializer for wallet information response"""
    
    wallet_address = serializers.CharField(read_only=True)
    has_wallet = serializers.BooleanField(read_only=True)
    atc_balance = serializers.DecimalField(max_digits=20, decimal_places=8, read_only=True)
    session_active = serializers.BooleanField(read_only=True)


class TransactionSerializer(serializers.Serializer):
    """Serializer for transaction creation"""
    
    to_address = serializers.CharField(
        max_length=42,
        help_text="Recipient wallet address"
    )
    amount = serializers.DecimalField(
        max_digits=30,
        decimal_places=18,
        help_text="Amount to send"
    )
    gas_price = serializers.DecimalField(
        max_digits=30,
        decimal_places=9,
        required=False,
        help_text="Gas price in Gwei"
    )
    
    def validate_to_address(self, value):
        if not value.startswith('0x') or len(value) != 42:
            raise serializers.ValidationError("Invalid wallet address format")
        return value.lower()
    
    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0")
        return value
