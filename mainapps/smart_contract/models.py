from django.db import models
from decimal import Decimal
from django.conf import settings

User = settings.AUTH_USER_MODEL

class SmartContractTransaction(models.Model):
    TRANSACTION_TYPES = [
        ('transfer', 'Transfer'),
        ('mint', 'Mint'),
        ('burn', 'Burn'),
        ('approve', 'Approve'),
        ('commit_transfer', 'Commit Transfer'),
        ('reveal_transfer', 'Reveal Transfer'),
        ('setup_vesting', 'Setup Vesting'),
        ('release_vested', 'Release Vested'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('failed', 'Failed'),
    ]
    
    user = models.ForeignKey(User,related_name='smart_contract_transactions', on_delete=models.CASCADE)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    from_address = models.CharField(max_length=42, blank=True)
    to_address = models.CharField(max_length=42, blank=True)
    amount = models.DecimalField(max_digits=36, decimal_places=18, null=True, blank=True)
    gas_price = models.DecimalField(max_digits=36, decimal_places=18, null=True, blank=True)
    gas_limit = models.BigIntegerField(null=True, blank=True)
    transaction_hash = models.CharField(max_length=66, blank=True)
    block_number = models.BigIntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Additional fields for specific transaction types
    nonce = models.BigIntegerField(null=True, blank=True)  # For reveal transfers
    commitment = models.CharField(max_length=66, blank=True)  # For commit transfers
    vesting_duration = models.BigIntegerField(null=True, blank=True)  # For vesting
    
    class Meta:
        ordering = ['-created_at']


class VestingSchedule(models.Model):
    user = models.ForeignKey(User,related_name='vesting_schedule', on_delete=models.CASCADE)
    beneficiary_address = models.CharField(max_length=42)
    total_amount = models.DecimalField(max_digits=36, decimal_places=18)
    released_amount = models.DecimalField(max_digits=36, decimal_places=18, default=0)
    start_time = models.DateTimeField()
    duration = models.BigIntegerField()  # Duration in seconds
    is_whale = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    @property
    def vested_amount(self):
        # Calculate vested amount based on time elapsed
        from django.utils import timezone
        import time
        
        if timezone.now() < self.start_time:
            return Decimal('0')
        
        elapsed = int(time.time()) - int(self.start_time.timestamp())
        if elapsed >= self.duration:
            return self.total_amount
        
        if self.is_whale:
            # Whale release rate is different
            whale_rate = Decimal('0.1')  # 10% per period
            return min(self.total_amount, self.total_amount * whale_rate * elapsed // self.duration)
        
        return self.total_amount * elapsed // self.duration


class CommitRevealTransfer(models.Model):
    user = models.ForeignKey(User,related_name='commit_reveal_transfer', on_delete=models.CASCADE)
    commitment = models.CharField(max_length=66, unique=True)
    to_address = models.CharField(max_length=42)
    amount = models.DecimalField(max_digits=36, decimal_places=18)
    nonce = models.BigIntegerField()
    commit_time = models.DateTimeField(auto_now_add=True)
    revealed = models.BooleanField(default=False)
    reveal_transaction = models.ForeignKey(
        SmartContractTransaction, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )


class WhaleProtectionLimit(models.Model):
    address = models.CharField(max_length=42, unique=True)
    max_transfer_amount = models.DecimalField(max_digits=36, decimal_places=18)
    max_balance_percentage = models.DecimalField(max_digits=5, decimal_places=2)  # e.g., 5.00 for 5%
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class FeeExemption(models.Model):
    address = models.CharField(max_length=42, unique=True)
    exemption_type = models.CharField(max_length=20, choices=[
        ('full', 'Full Exemption'),
        ('partial', 'Partial Exemption'),
    ])
    exemption_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=100)  # 100% = full exemption
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class BlacklistedAddress(models.Model):
    address = models.CharField(max_length=42, unique=True)
    reason = models.TextField(blank=True)
    blacklisted_by = models.ForeignKey(User,related_name='blacklisted_address', on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class MiningReward(models.Model):
    miner_address = models.CharField(max_length=42)
    block_number = models.BigIntegerField()
    reward_amount = models.DecimalField(max_digits=36, decimal_places=18)
    transaction_hash = models.CharField(max_length=66)
    claimed = models.BooleanField(default=False)
    claim_transaction = models.ForeignKey(
        SmartContractTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['miner_address', 'block_number']
