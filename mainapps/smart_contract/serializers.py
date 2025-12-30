from rest_framework import serializers
from .models import (
    SmartContractTransaction, VestingSchedule, CommitRevealTransfer,
    WhaleProtectionLimit, FeeExemption, BlacklistedAddress, MiningReward
)


class SmartContractTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SmartContractTransaction
        fields = [
            'id', 'transaction_type', 'from_address', 'to_address', 
            'amount', 'transaction_hash', 'status', 'created_at',
            'block_number', 'gas_price', 'gas_limit', 'error_message'
        ]
        read_only_fields = ['id', 'created_at', 'transaction_hash', 'status']


class VestingScheduleSerializer(serializers.ModelSerializer):
    vested_amount = serializers.ReadOnlyField()
    
    class Meta:
        model = VestingSchedule
        fields = [
            'id', 'beneficiary_address', 'total_amount', 'released_amount',
            'vested_amount', 'start_time', 'duration', 'is_whale', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'vested_amount']


class CommitRevealTransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommitRevealTransfer
        fields = [
            'id', 'commitment', 'to_address', 'amount', 'commit_time',
            'revealed', 'reveal_transaction'
        ]
        read_only_fields = ['id', 'commitment', 'commit_time', 'revealed']


class TransferRequestSerializer(serializers.Serializer):
    to_address = serializers.CharField(max_length=42)
    amount = serializers.DecimalField(max_digits=36, decimal_places=18)


class CommitTransferRequestSerializer(serializers.Serializer):
    to_address = serializers.CharField(max_length=42)
    amount = serializers.DecimalField(max_digits=36, decimal_places=18)
    nonce = serializers.IntegerField(required=False)


class VestingRequestSerializer(serializers.Serializer):
    beneficiary_address = serializers.CharField(max_length=42)
    amount = serializers.DecimalField(max_digits=36, decimal_places=18)
    start_time = serializers.DateTimeField()
    duration = serializers.IntegerField()  # Duration in seconds


class WhaleProtectionLimitSerializer(serializers.ModelSerializer):
    class Meta:
        model = WhaleProtectionLimit
        fields = ['id', 'max_transfer_amount', 'time_window', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class FeeExemptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeeExemption
        fields = ['id', 'address', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class BlacklistedAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlacklistedAddress
        fields = ['id', 'address', 'reason', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class MiningRewardSerializer(serializers.ModelSerializer):
    class Meta:
        model = MiningReward
        fields = ['id', 'miner_address', 'block_number', 'reward_amount', 'created_at']
        read_only_fields = ['id', 'created_at']


class TokenStatsSerializer(serializers.Serializer):
    total_supply = serializers.DecimalField(max_digits=36, decimal_places=18)
    circulating_supply = serializers.DecimalField(max_digits=36, decimal_places=18)
    total_holders = serializers.IntegerField()
    total_transactions = serializers.IntegerField()


class AdminTransactionSerializer(serializers.Serializer):
    transaction_type = serializers.CharField(max_length=50)
    target_address = serializers.CharField(max_length=42, required=False)
    amount = serializers.DecimalField(max_digits=36, decimal_places=18, required=False)
    reason = serializers.CharField(max_length=255, required=False)
