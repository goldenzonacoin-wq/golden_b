from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal
import uuid


class BlockchainNetwork(models.Model):
    """Supported blockchain networks"""
    
    name = models.CharField(max_length=50, unique=True)
    chain_id = models.PositiveIntegerField(unique=True)
    rpc_url = models.URLField()
    explorer_url = models.URLField()
    native_currency_symbol = models.CharField(max_length=10)
    is_testnet = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'blockchain_network'
        verbose_name = 'Blockchain Network'
        verbose_name_plural = 'Blockchain Networks'
    
    def __str__(self):
        return f"{self.name} ({'Testnet' if self.is_testnet else 'Mainnet'})"


class TokenContract(models.Model):
    """ATC token contract information"""
    
    network = models.ForeignKey(BlockchainNetwork, on_delete=models.CASCADE)
    contract_address = models.CharField(max_length=42)
    token_name = models.CharField(max_length=100, default="AtlanteanCrown")
    token_symbol = models.CharField(max_length=10, default="ATC")
    decimals = models.PositiveIntegerField(default=18)
    total_supply = models.DecimalField(
        max_digits=30,
        decimal_places=18,
        default=Decimal('1000000000')  # 1 billion tokens
    )
    deployment_block = models.PositiveIntegerField(blank=True, null=True)
    deployment_tx_hash = models.CharField(max_length=66, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'blockchain_token_contract'
        unique_together = ['network', 'contract_address']
        verbose_name = 'Token Contract'
        verbose_name_plural = 'Token Contracts'
    
    def __str__(self):
        return f"{self.token_symbol} on {self.network.name}"


class WalletBalance(models.Model):
    """Cached wallet balances for users"""
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    network = models.ForeignKey(BlockchainNetwork, on_delete=models.CASCADE)
    token_contract = models.ForeignKey(TokenContract, on_delete=models.CASCADE)
    balance = models.DecimalField(
        max_digits=30,
        decimal_places=18,
        default=Decimal('0')
    )
    last_updated = models.DateTimeField(auto_now=True)
    block_number = models.PositiveIntegerField(blank=True, null=True)
    
    class Meta:
        db_table = 'blockchain_wallet_balance'
        unique_together = ['user', 'network', 'token_contract']
        indexes = [
            models.Index(fields=['user', 'network']),
            models.Index(fields=['last_updated']),
        ]
    
    @property
    def is_whale(self):
        """Check if balance qualifies as whale (>5% of total supply)"""
        if self.token_contract.total_supply > 0:
            whale_threshold = self.token_contract.total_supply * Decimal('0.05')
            return self.balance >= whale_threshold
        return False
    
    def __str__(self):
        return f"{self.user.email} - {self.balance} {self.token_contract.token_symbol}"


class Transaction(models.Model):
    """Blockchain transaction records"""
    
    class TransactionType(models.TextChoices):
        TRANSFER = 'transfer', 'Transfer'
        MINT = 'mint', 'Mint'
        BURN = 'burn', 'Burn'
        STAKE = 'stake', 'Stake'
        UNSTAKE = 'unstake', 'Unstake'
        REWARD = 'reward', 'Reward'
        VESTING = 'vesting', 'Vesting Release'
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        FAILED = 'failed', 'Failed'
    
    # Transaction identifiers
    tx_hash = models.CharField(max_length=66, unique=True)
    network = models.ForeignKey(BlockchainNetwork, on_delete=models.CASCADE)
    block_number = models.PositiveIntegerField(blank=True, null=True)
    block_hash = models.CharField(max_length=66, blank=True, null=True)
    transaction_index = models.PositiveIntegerField(blank=True, null=True)
    
    # Transaction details
    from_address = models.CharField(max_length=42)
    to_address = models.CharField(max_length=42)
    amount = models.DecimalField(max_digits=30, decimal_places=18)
    gas_used = models.PositiveIntegerField(blank=True, null=True)
    gas_price = models.DecimalField(max_digits=30, decimal_places=0, blank=True, null=True)
    transaction_fee = models.DecimalField(max_digits=30, decimal_places=18, blank=True, null=True)
    
    # ATC-specific fields
    token_contract = models.ForeignKey(TokenContract, on_delete=models.CASCADE)
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    
    # User associations
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='sent_transactions'
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='received_transactions'
    )
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        db_table = 'blockchain_transaction'
        indexes = [
            models.Index(fields=['tx_hash']),
            models.Index(fields=['from_address', 'to_address']),
            models.Index(fields=['from_user', 'to_user']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['transaction_type']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.tx_hash[:10]}... - {self.transaction_type} - {self.amount} {self.token_contract.token_symbol}"


class StakingPool(models.Model):
    """Staking pools for ATC tokens"""
    
    class PoolType(models.TextChoices):
        FIXED = 'fixed', 'Fixed Term'
        FLEXIBLE = 'flexible', 'Flexible'
        VALIDATOR = 'validator', 'Validator Pool'
    
    name = models.CharField(max_length=100)
    pool_type = models.CharField(max_length=20, choices=PoolType.choices)
    token_contract = models.ForeignKey(TokenContract, on_delete=models.CASCADE)
    
    # Pool parameters
    minimum_stake = models.DecimalField(
        max_digits=30,
        decimal_places=18,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    maximum_stake = models.DecimalField(
        max_digits=30,
        decimal_places=18,
        blank=True,
        null=True
    )
    annual_percentage_yield = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="APY percentage (e.g., 12.50 for 12.5%)"
    )
    lock_period_days = models.PositiveIntegerField(
        default=0,
        help_text="Lock period in days (0 for flexible staking)"
    )
    
    # Pool status
    total_staked = models.DecimalField(
        max_digits=30,
        decimal_places=18,
        default=Decimal('0')
    )
    max_pool_size = models.DecimalField(
        max_digits=30,
        decimal_places=18,
        blank=True,
        null=True
    )
    is_active = models.BooleanField(default=True)
    
    # Contract information
    staking_contract_address = models.CharField(max_length=42, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'blockchain_staking_pool'
        verbose_name = 'Staking Pool'
        verbose_name_plural = 'Staking Pools'
    
    @property
    def is_full(self):
        """Check if pool has reached maximum capacity"""
        if self.max_pool_size:
            return self.total_staked >= self.max_pool_size
        return False
    
    @property
    def utilization_rate(self):
        """Calculate pool utilization rate"""
        if self.max_pool_size and self.max_pool_size > 0:
            return (self.total_staked / self.max_pool_size) * 100
        return 0
    
    def __str__(self):
        return f"{self.name} - {self.annual_percentage_yield}% APY"


class UserStake(models.Model):
    """User staking positions"""
    
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        UNSTAKING = 'unstaking', 'Unstaking'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    staking_pool = models.ForeignKey(StakingPool, on_delete=models.CASCADE)
    
    # Stake details
    staked_amount = models.DecimalField(max_digits=30, decimal_places=18)
    rewards_earned = models.DecimalField(
        max_digits=30,
        decimal_places=18,
        default=Decimal('0')
    )
    rewards_claimed = models.DecimalField(
        max_digits=30,
        decimal_places=18,
        default=Decimal('0')
    )
    
    # Timing
    staked_at = models.DateTimeField(auto_now_add=True)
    unlock_at = models.DateTimeField(blank=True, null=True)
    unstaked_at = models.DateTimeField(blank=True, null=True)
    last_reward_calculation = models.DateTimeField(auto_now_add=True)
    
    # Status
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    
    # Transaction references
    stake_tx_hash = models.CharField(max_length=66, blank=True, null=True)
    unstake_tx_hash = models.CharField(max_length=66, blank=True, null=True)
    
    class Meta:
        db_table = 'blockchain_user_stake'
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['staking_pool', 'status']),
            models.Index(fields=['staked_at']),
        ]
    
    @property
    def pending_rewards(self):
        """Calculate pending rewards since last calculation"""
        from django.utils import timezone
        from datetime import timedelta
        
        if self.status != self.Status.ACTIVE:
            return Decimal('0')
        
        now = timezone.now()
        time_diff = now - self.last_reward_calculation
        days_elapsed = Decimal(str(time_diff.total_seconds() / 86400))  # Convert to days
        
        daily_rate = self.staking_pool.annual_percentage_yield / Decimal('365') / Decimal('100')
        pending = self.staked_amount * daily_rate * days_elapsed
        
        return pending
    
    @property
    def total_rewards(self):
        """Total rewards (earned + pending)"""
        return self.rewards_earned + self.pending_rewards
    
    @property
    def is_locked(self):
        """Check if stake is still locked"""
        if self.unlock_at:
            from django.utils import timezone
            return timezone.now() < self.unlock_at
        return False
    
    def __str__(self):
        return f"{self.user.email} - {self.staked_amount} {self.staking_pool.token_contract.token_symbol}"


class VestingSchedule(models.Model):
    """Token vesting schedules for team, advisors, etc."""
    
    class VestingType(models.TextChoices):
        LINEAR = 'linear', 'Linear Vesting'
        CLIFF = 'cliff', 'Cliff Vesting'
        MILESTONE = 'milestone', 'Milestone-based'
    
    beneficiary = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token_contract = models.ForeignKey(TokenContract, on_delete=models.CASCADE)
    
    # Vesting parameters
    total_amount = models.DecimalField(max_digits=30, decimal_places=18)
    vesting_type = models.CharField(max_length=20, choices=VestingType.choices)
    start_date = models.DateTimeField()
    cliff_duration_days = models.PositiveIntegerField(default=0)
    vesting_duration_days = models.PositiveIntegerField()
    
    # Status tracking
    amount_released = models.DecimalField(
        max_digits=30,
        decimal_places=18,
        default=Decimal('0')
    )
    is_revoked = models.BooleanField(default=False)
    revoked_at = models.DateTimeField(blank=True, null=True)
    
    # Contract information
    vesting_contract_address = models.CharField(max_length=42, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'blockchain_vesting_schedule'
        verbose_name = 'Vesting Schedule'
        verbose_name_plural = 'Vesting Schedules'
    
    @property
    def vested_amount(self):
        """Calculate currently vested amount"""
        from django.utils import timezone
        
        if self.is_revoked:
            return self.amount_released
        
        now = timezone.now()
        
        # Check if cliff period has passed
        cliff_end = self.start_date + timezone.timedelta(days=self.cliff_duration_days)
        if now < cliff_end:
            return Decimal('0')
        
        # Calculate vested amount based on time elapsed
        vesting_end = self.start_date + timezone.timedelta(days=self.vesting_duration_days)
        if now >= vesting_end:
            return self.total_amount
        
        # Linear vesting calculation
        elapsed_days = (now - cliff_end).days
        vesting_days = self.vesting_duration_days - self.cliff_duration_days
        vesting_ratio = Decimal(str(elapsed_days)) / Decimal(str(vesting_days))
        
        return self.total_amount * vesting_ratio
    
    @property
    def releasable_amount(self):
        """Amount that can be released now"""
        return max(Decimal('0'), self.vested_amount - self.amount_released)
    
    def __str__(self):
        return f"{self.beneficiary.email} - {self.total_amount} {self.token_contract.token_symbol}"


class BlockchainEvent(models.Model):
    """Blockchain events and logs"""
    
    class EventType(models.TextChoices):
        TRANSFER = 'transfer', 'Transfer'
        APPROVAL = 'approval', 'Approval'
        STAKE = 'stake', 'Stake'
        UNSTAKE = 'unstake', 'Unstake'
        REWARD_CLAIM = 'reward_claim', 'Reward Claim'
        VESTING_RELEASE = 'vesting_release', 'Vesting Release'
        WHALE_TRANSFER = 'whale_transfer', 'Whale Transfer'
    
    # Event identification
    tx_hash = models.CharField(max_length=66)
    log_index = models.PositiveIntegerField()
    network = models.ForeignKey(BlockchainNetwork, on_delete=models.CASCADE)
    contract_address = models.CharField(max_length=42)
    
    # Event details
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    event_data = models.JSONField(default=dict)
    block_number = models.PositiveIntegerField()
    block_timestamp = models.DateTimeField()
    
    # Processing status
    is_processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'blockchain_event'
        unique_together = ['tx_hash', 'log_index']
        indexes = [
            models.Index(fields=['event_type', 'is_processed']),
            models.Index(fields=['block_number']),
            models.Index(fields=['contract_address']),
        ]
        ordering = ['-block_number', '-log_index']
    
    def __str__(self):
        return f"{self.event_type} - Block {self.block_number} - {self.tx_hash[:10]}..."


class TokenPurchaseSettings(models.Model):
    """Admin-configurable token purchase settings."""

    token_price_usd = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        default=Decimal('0'),
        help_text="Token price in USD."
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'blockchain_token_purchase_settings'
        verbose_name = 'Token Purchase Settings'
        verbose_name_plural = 'Token Purchase Settings'

    def save(self, *args, **kwargs):
        if not self.pk and TokenPurchaseSettings.objects.exists():
            raise ValidationError('Only one Token Purchase Settings instance is allowed')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Token Purchase Settings - {self.token_price_usd} USD"


class TokenPurchase(models.Model):
    """Records token purchases initiated via Flutterwave."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        REVIEW = 'review', 'Review'
        SUCCESSFUL = 'successful', 'Successful'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'

    class TransferStatus(models.TextChoices):
        NOT_STARTED = 'not_started', 'Not Started'
        PROCESSING = 'processing', 'Processing'
        SUCCESSFUL = 'successful', 'Successful'
        FAILED = 'failed', 'Failed'

    user_id = models.PositiveIntegerField(db_index=True)
    wallet_address = models.CharField(max_length=64)
    token_amount = models.DecimalField(max_digits=30, decimal_places=18)
    usd_price_per_token = models.DecimalField(max_digits=20, decimal_places=8)
    usd_amount = models.DecimalField(max_digits=20, decimal_places=2)
    charge_amount = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=10, default='USD')
    tx_ref = models.CharField(max_length=120, unique=True)
    flw_ref = models.CharField(max_length=120, blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    payment_link = models.URLField(blank=True, null=True)
    init_payload = models.JSONField(default=dict, blank=True)
    last_webhook_payload = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    transfer_status = models.CharField(
        max_length=20,
        choices=TransferStatus.choices,
        default=TransferStatus.NOT_STARTED
    )
    transfer_tx_hash = models.CharField(max_length=120, blank=True, null=True)
    transfer_error = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'blockchain_token_purchase'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user_id', 'status']),
            models.Index(fields=['tx_ref']),
        ]

    def __str__(self):
        return f"{self.user_id} - {self.tx_ref} - {self.status}"
