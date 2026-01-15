from rest_framework import serializers
from decimal import Decimal
from .models import (
    BlockchainNetwork, TokenContract, WalletBalance, Transaction,
    StakingPool, UserStake, VestingSchedule, BlockchainEvent,
    TokenPurchase
)
from web3 import Web3


class BlockchainNetworkSerializer(serializers.ModelSerializer):
    """Serializer for blockchain networks"""
    
    class Meta:
        model = BlockchainNetwork
        fields = (
            'id', 'name', 'chain_id', 'rpc_url', 'explorer_url',
            'native_currency_symbol', 'is_testnet', 'is_active'
        )


class TokenContractSerializer(serializers.ModelSerializer):
    """Serializer for token contracts"""
    network_name = serializers.CharField(source='network.name', read_only=True)
    
    class Meta:
        model = TokenContract
        fields = (
            'id', 'network', 'network_name', 'contract_address',
            'token_name', 'token_symbol', 'decimals', 'total_supply',
            'deployment_block', 'deployment_tx_hash', 'is_active', 'created_at'
        )


class WalletBalanceSerializer(serializers.ModelSerializer):
    """Serializer for wallet balances"""
    network_name = serializers.CharField(source='network.name', read_only=True)
    token_symbol = serializers.CharField(source='token_contract.token_symbol', read_only=True)
    is_whale = serializers.ReadOnlyField()
    
    class Meta:
        model = WalletBalance
        fields = (
            'id', 'network', 'network_name', 'token_contract', 'token_symbol',
            'balance', 'is_whale', 'last_updated', 'block_number'
        )


class TransactionSerializer(serializers.ModelSerializer):
    """Serializer for blockchain transactions"""
    network_name = serializers.CharField(source='network.name', read_only=True)
    token_symbol = serializers.CharField(source='token_contract.token_symbol', read_only=True)
    from_user_email = serializers.CharField(source='from_user.email', read_only=True)
    to_user_email = serializers.CharField(source='to_user.email', read_only=True)
    
    class Meta:
        model = Transaction
        fields = (
            'id', 'tx_hash', 'network', 'network_name', 'block_number',
            'from_address', 'to_address', 'from_user_email', 'to_user_email',
            'amount', 'token_contract', 'token_symbol', 'transaction_type',
            'status', 'gas_used', 'gas_price', 'transaction_fee',
            'metadata', 'created_at', 'confirmed_at'
        )


class StakingPoolSerializer(serializers.ModelSerializer):
    """Serializer for staking pools"""
    token_symbol = serializers.CharField(source='token_contract.token_symbol', read_only=True)
    network_name = serializers.CharField(source='token_contract.network.name', read_only=True)
    is_full = serializers.ReadOnlyField()
    utilization_rate = serializers.ReadOnlyField()
    
    class Meta:
        model = StakingPool
        fields = (
            'id', 'name', 'pool_type', 'token_contract', 'token_symbol',
            'network_name', 'minimum_stake', 'maximum_stake',
            'annual_percentage_yield', 'lock_period_days', 'total_staked',
            'max_pool_size', 'is_full', 'utilization_rate', 'is_active',
            'staking_contract_address', 'created_at'
        )


class UserStakeSerializer(serializers.ModelSerializer):
    """Serializer for user stakes"""
    pool_name = serializers.CharField(source='staking_pool.name', read_only=True)
    pool_apy = serializers.DecimalField(
        source='staking_pool.annual_percentage_yield',
        max_digits=5,
        decimal_places=2,
        read_only=True
    )
    token_symbol = serializers.CharField(
        source='staking_pool.token_contract.token_symbol',
        read_only=True
    )
    pending_rewards = serializers.ReadOnlyField()
    total_rewards = serializers.ReadOnlyField()
    is_locked = serializers.ReadOnlyField()
    
    class Meta:
        model = UserStake
        fields = (
            'id', 'staking_pool', 'pool_name', 'pool_apy', 'token_symbol',
            'staked_amount', 'rewards_earned', 'rewards_claimed',
            'pending_rewards', 'total_rewards', 'staked_at', 'unlock_at',
            'unstaked_at', 'status', 'is_locked', 'stake_tx_hash', 'unstake_tx_hash'
        )


class StakeCreateSerializer(serializers.Serializer):
    """Serializer for creating stakes"""
    staking_pool_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=30, decimal_places=18)
    
    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0")
        return value
    
    def validate(self, attrs):
        try:
            pool = StakingPool.objects.get(
                id=attrs['staking_pool_id'],
                is_active=True
            )
        except StakingPool.DoesNotExist:
            raise serializers.ValidationError("Invalid staking pool")
        
        amount = attrs['amount']
        
        # Check minimum stake
        if amount < pool.minimum_stake:
            raise serializers.ValidationError(
                f"Minimum stake is {pool.minimum_stake} {pool.token_contract.token_symbol}"
            )
        
        # Check maximum stake
        if pool.maximum_stake and amount > pool.maximum_stake:
            raise serializers.ValidationError(
                f"Maximum stake is {pool.maximum_stake} {pool.token_contract.token_symbol}"
            )
        
        # Check pool capacity
        if pool.max_pool_size and (pool.total_staked + amount) > pool.max_pool_size:
            raise serializers.ValidationError("Pool capacity exceeded")
        
        attrs['staking_pool'] = pool
        return attrs


class TokenPurchaseSerializer(serializers.ModelSerializer):
    """Serializer for token purchase records."""

    class Meta:
        model = TokenPurchase
        fields = (
            'id', 'user_id', 'wallet_address', 'token_amount',
            'usd_price_per_token', 'usd_amount', 'charge_amount',
            'currency', 'tx_ref', 'flw_ref', 'status', 'payment_link',
            'paid_at', 'transfer_status', 'transfer_tx_hash',
            'transfer_error', 'created_at', 'updated_at'
        )


class TokenPurchaseInitiateSerializer(serializers.Serializer):
    """Serializer for initiating token purchases."""

    token_amount = serializers.DecimalField(max_digits=30, decimal_places=18)
    currency = serializers.CharField(max_length=10)
    wallet_address = serializers.CharField(max_length=64)
    redirect_url = serializers.URLField(required=False, allow_blank=True)

    def validate_token_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Token amount must be greater than 0.")
        return value

    def validate_wallet_address(self, value):
        if not Web3.is_address(value):
            raise serializers.ValidationError("Invalid wallet address.")
        return value


class VestingScheduleSerializer(serializers.ModelSerializer):
    """Serializer for vesting schedules"""
    beneficiary_email = serializers.CharField(source='beneficiary.email', read_only=True)
    token_symbol = serializers.CharField(source='token_contract.token_symbol', read_only=True)
    vested_amount = serializers.ReadOnlyField()
    releasable_amount = serializers.ReadOnlyField()
    
    class Meta:
        model = VestingSchedule
        fields = (
            'id', 'beneficiary', 'beneficiary_email', 'token_contract',
            'token_symbol', 'total_amount', 'vesting_type', 'start_date',
            'cliff_duration_days', 'vesting_duration_days', 'amount_released',
            'vested_amount', 'releasable_amount', 'is_revoked', 'revoked_at',
            'vesting_contract_address', 'created_at'
        )


class BlockchainEventSerializer(serializers.ModelSerializer):
    """Serializer for blockchain events"""
    network_name = serializers.CharField(source='network.name', read_only=True)
    
    class Meta:
        model = BlockchainEvent
        fields = (
            'id', 'tx_hash', 'log_index', 'network', 'network_name',
            'contract_address', 'event_type', 'event_data', 'block_number',
            'block_timestamp', 'is_processed', 'processed_at', 'created_at'
        )


class WalletStatsSerializer(serializers.Serializer):
    """Serializer for wallet statistics"""
    total_balance = serializers.DecimalField(max_digits=30, decimal_places=18)
    total_staked = serializers.DecimalField(max_digits=30, decimal_places=18)
    total_rewards = serializers.DecimalField(max_digits=30, decimal_places=18)
    total_vesting = serializers.DecimalField(max_digits=30, decimal_places=18)
    whale_status = serializers.BooleanField()
    transaction_count = serializers.IntegerField()
    first_transaction_date = serializers.DateTimeField()


class NetworkStatsSerializer(serializers.Serializer):
    """Serializer for network statistics"""
    total_holders = serializers.IntegerField()
    total_transactions = serializers.IntegerField()
    total_staked = serializers.DecimalField(max_digits=30, decimal_places=18)
    total_rewards_distributed = serializers.DecimalField(max_digits=30, decimal_places=18)
    whale_count = serializers.IntegerField()
    average_balance = serializers.DecimalField(max_digits=30, decimal_places=18)
