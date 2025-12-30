from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.pagination import PageNumberPagination
from django.db.models import Sum, Count, Avg, Q
from django.utils import timezone
from decimal import Decimal
from .models import (
    BlockchainNetwork, TokenContract, WalletBalance, Transaction,
    StakingPool, UserStake, VestingSchedule, BlockchainEvent
)
from .serializers import (
    BlockchainNetworkSerializer, TokenContractSerializer,
    WalletBalanceSerializer, TransactionSerializer, StakingPoolSerializer,
    UserStakeSerializer, StakeCreateSerializer, VestingScheduleSerializer,
    BlockchainEventSerializer, WalletStatsSerializer, NetworkStatsSerializer
)


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class BlockchainNetworkListView(generics.ListAPIView):
    """List supported blockchain networks"""
    queryset = BlockchainNetwork.objects.filter(is_active=True)
    serializer_class = BlockchainNetworkSerializer
    permission_classes = [permissions.AllowAny]


class TokenContractListView(generics.ListAPIView):
    """List token contracts"""
    queryset = TokenContract.objects.filter(is_active=True)
    serializer_class = TokenContractSerializer
    permission_classes = [permissions.AllowAny]


class UserWalletBalanceView(generics.ListAPIView):
    """Get user's wallet balances across all networks"""
    serializer_class = WalletBalanceSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return WalletBalance.objects.filter(user=self.request.user)


class UserTransactionListView(generics.ListAPIView):
    """List user's transactions"""
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        user = self.request.user
        return Transaction.objects.filter(
            Q(from_user=user) | Q(to_user=user)
        ).order_by('-created_at')


class StakingPoolListView(generics.ListAPIView):
    """List available staking pools"""
    serializer_class = StakingPoolSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return StakingPool.objects.filter(is_active=True)


class UserStakeListView(generics.ListAPIView):
    """List user's stakes"""
    serializer_class = UserStakeSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return UserStake.objects.filter(user=self.request.user)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_stake(request):
    """Create a new stake"""
    serializer = StakeCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    pool = serializer.validated_data['staking_pool']
    amount = serializer.validated_data['amount']
    
    # Check user balance (this would integrate with actual blockchain)
    try:
        balance = WalletBalance.objects.get(
            user=request.user,
            token_contract=pool.token_contract
        )
        if balance.balance < amount:
            return Response(
                {'error': 'Insufficient balance'},
                status=status.HTTP_400_BAD_REQUEST
            )
    except WalletBalance.DoesNotExist:
        return Response(
            {'error': 'No balance found for this token'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Calculate unlock time for fixed pools
    unlock_at = None
    if pool.pool_type == 'fixed':
        unlock_at = timezone.now() + timezone.timedelta(days=pool.lock_period_days)
    
    # Create stake
    stake = UserStake.objects.create(
        user=request.user,
        staking_pool=pool,
        staked_amount=amount,
        unlock_at=unlock_at
    )
    
    # Update pool total (in real implementation, this would be done via blockchain)
    pool.total_staked += amount
    pool.save()
    
    # Update user balance (in real implementation, tokens would be locked in contract)
    balance.balance -= amount
    balance.save()
    
    return Response({
        'message': 'Stake created successfully',
        'stake': UserStakeSerializer(stake).data
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def unstake(request, stake_id):
    """Unstake tokens"""
    try:
        stake = UserStake.objects.get(
            id=stake_id,
            user=request.user,
            status='active'
        )
    except UserStake.DoesNotExist:
        return Response(
            {'error': 'Stake not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check if stake is locked
    if stake.is_locked:
        return Response(
            {'error': 'Stake is still locked'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Calculate final rewards
    pending_rewards = stake.pending_rewards
    stake.rewards_earned += pending_rewards
    stake.status = 'unstaking'  # In real implementation, this would be 'completed' after blockchain confirmation
    stake.unstaked_at = timezone.now()
    stake.save()
    
    # Update pool total
    stake.staking_pool.total_staked -= stake.staked_amount
    stake.staking_pool.save()
    
    # Return tokens to user balance (in real implementation, this would be done via blockchain)
    balance, created = WalletBalance.objects.get_or_create(
        user=request.user,
        token_contract=stake.staking_pool.token_contract,
        network=stake.staking_pool.token_contract.network
    )
    balance.balance += stake.staked_amount + stake.rewards_earned
    balance.save()
    
    return Response({
        'message': 'Unstaking initiated successfully',
        'returned_amount': stake.staked_amount + stake.rewards_earned
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def claim_rewards(request, stake_id):
    """Claim staking rewards"""
    try:
        stake = UserStake.objects.get(
            id=stake_id,
            user=request.user,
            status='active'
        )
    except UserStake.DoesNotExist:
        return Response(
            {'error': 'Stake not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Calculate and claim rewards
    pending_rewards = stake.pending_rewards
    if pending_rewards <= 0:
        return Response(
            {'error': 'No rewards to claim'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    stake.rewards_earned += pending_rewards
    stake.rewards_claimed += pending_rewards
    stake.last_reward_calculation = timezone.now()
    stake.save()
    
    # Add rewards to user balance
    balance, created = WalletBalance.objects.get_or_create(
        user=request.user,
        token_contract=stake.staking_pool.token_contract,
        network=stake.staking_pool.token_contract.network
    )
    balance.balance += pending_rewards
    balance.save()
    
    return Response({
        'message': 'Rewards claimed successfully',
        'claimed_amount': pending_rewards
    })


class UserVestingScheduleListView(generics.ListAPIView):
    """List user's vesting schedules"""
    serializer_class = VestingScheduleSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return VestingSchedule.objects.filter(
            beneficiary=self.request.user,
            is_revoked=False
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def release_vested_tokens(request, schedule_id):
    """Release vested tokens"""
    try:
        schedule = VestingSchedule.objects.get(
            id=schedule_id,
            beneficiary=request.user,
            is_revoked=False
        )
    except VestingSchedule.DoesNotExist:
        return Response(
            {'error': 'Vesting schedule not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    releasable = schedule.releasable_amount
    if releasable <= 0:
        return Response(
            {'error': 'No tokens available for release'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Release tokens
    schedule.amount_released += releasable
    schedule.save()
    
    # Add to user balance
    balance, created = WalletBalance.objects.get_or_create(
        user=request.user,
        token_contract=schedule.token_contract,
        network=schedule.token_contract.network
    )
    balance.balance += releasable
    balance.save()
    
    return Response({
        'message': 'Tokens released successfully',
        'released_amount': releasable
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def wallet_stats(request):
    """Get user's wallet statistics"""
    user = request.user
    
    # Calculate totals
    balances = WalletBalance.objects.filter(user=user)
    total_balance = balances.aggregate(Sum('balance'))['balance__sum'] or Decimal('0')
    
    stakes = UserStake.objects.filter(user=user, status='active')
    total_staked = stakes.aggregate(Sum('staked_amount'))['staked_amount__sum'] or Decimal('0')
    total_rewards = stakes.aggregate(Sum('rewards_earned'))['rewards_earned__sum'] or Decimal('0')
    
    vesting = VestingSchedule.objects.filter(beneficiary=user, is_revoked=False)
    total_vesting = vesting.aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0')
    
    # Check whale status
    whale_status = any(balance.is_whale for balance in balances)
    
    # Transaction stats
    transactions = Transaction.objects.filter(Q(from_user=user) | Q(to_user=user))
    transaction_count = transactions.count()
    first_transaction = transactions.order_by('created_at').first()
    
    stats = {
        'total_balance': total_balance,
        'total_staked': total_staked,
        'total_rewards': total_rewards,
        'total_vesting': total_vesting,
        'whale_status': whale_status,
        'transaction_count': transaction_count,
        'first_transaction_date': first_transaction.created_at if first_transaction else None,
    }
    
    serializer = WalletStatsSerializer(stats)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def network_stats(request):
    """Get network statistics"""
    # Total holders
    total_holders = WalletBalance.objects.filter(balance__gt=0).values('user').distinct().count()
    
    # Total transactions
    total_transactions = Transaction.objects.count()
    
    # Staking stats
    total_staked = UserStake.objects.filter(status='active').aggregate(
        Sum('staked_amount')
    )['staked_amount__sum'] or Decimal('0')
    
    total_rewards = UserStake.objects.aggregate(
        Sum('rewards_earned')
    )['rewards_earned__sum'] or Decimal('0')
    
    # Whale count
    whale_count = WalletBalance.objects.filter(balance__gt=0).count()  # Simplified
    
    # Average balance
    avg_balance = WalletBalance.objects.filter(balance__gt=0).aggregate(
        Avg('balance')
    )['balance__avg'] or Decimal('0')
    
    stats = {
        'total_holders': total_holders,
        'total_transactions': total_transactions,
        'total_staked': total_staked,
        'total_rewards_distributed': total_rewards,
        'whale_count': whale_count,
        'average_balance': avg_balance,
    }
    
    serializer = NetworkStatsSerializer(stats)
    return Response(serializer.data)


# Admin Views

class AdminTransactionListView(generics.ListAPIView):
    """Admin view for all transactions"""
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination


class AdminBlockchainEventListView(generics.ListAPIView):
    """Admin view for blockchain events"""
    queryset = BlockchainEvent.objects.all()
    serializer_class = BlockchainEventSerializer
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination
