from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.pagination import PageNumberPagination
from django.db.models import Sum, Count, Q
from django.utils import timezone
from decimal import Decimal
from .models import (
    SmartContractTransaction, VestingSchedule, CommitRevealTransfer,
    WhaleProtectionLimit, FeeExemption, BlacklistedAddress, MiningReward
)
from .serializers import (
    TransferRequestSerializer, VestingScheduleSerializer, CommitRevealTransferSerializer,
    WhaleProtectionLimitSerializer, FeeExemptionSerializer, BlacklistedAddressSerializer,
    MiningRewardSerializer, TokenStatsSerializer, SmartContractTransactionSerializer,
    CommitTransferRequestSerializer
)
from .services import SmartContractService


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


# Token Operations (User endpoints)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def prepare_transfer(request):
    """Prepare transfer transaction data for frontend signing"""
    serializer = TransferRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    from_address = request.data.get('from_address')
    to_address = serializer.validated_data['to_address']
    amount = serializer.validated_data['amount']
    
    if not from_address:
        return Response({
            'error': 'from_address is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        service = SmartContractService()
        result = service.prepare_transfer_transaction(
            from_address=from_address,
            to_address=to_address,
            amount=amount
        )
        
        return Response({
            'success': True,
            'transaction_data': result['transaction_data'],
            'estimated_gas': result['estimated_gas'],
            'gas_price': result['gas_price'],
            'nonce': result['nonce']
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_signed_transaction(request):
    """Submit a signed transaction and record it"""
    signed_tx = request.data.get('signed_transaction')
    transaction_type = request.data.get('transaction_type')
    from_address = request.data.get('from_address')
    to_address = request.data.get('to_address')
    amount = request.data.get('amount')
    
    if not all([signed_tx, transaction_type, from_address, to_address, amount]):
        return Response({
            'error': 'All fields are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        service = SmartContractService()
        
        # Send the signed transaction
        tx_hash = service.w3.eth.send_raw_transaction(signed_tx)
        
        # Record the transaction
        contract_tx = service.record_transaction(
            user=request.user,
            transaction_type=transaction_type,
            from_address=from_address,
            to_address=to_address,
            amount=amount,
            tx_hash=tx_hash.hex()
        )
        
        return Response({
            'success': True,
            'transaction_hash': tx_hash.hex(),
            'transaction_id': contract_tx.id,
            'message': 'Transaction submitted successfully'
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def prepare_commit_transfer(request):
    """Prepare commit transfer transaction for frontend signing"""
    serializer = CommitTransferRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    from_address = request.data.get('from_address')
    to_address = serializer.validated_data['to_address']
    amount = serializer.validated_data['amount']
    nonce = serializer.validated_data.get('nonce')
    
    if not from_address:
        return Response({
            'error': 'from_address is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        service = SmartContractService()
        result = service.prepare_commit_transaction(
            from_address=from_address,
            to_address=to_address,
            amount=amount,
            nonce=nonce
        )
        
        return Response({
            'success': True,
            'transaction_data': result['transaction_data'],
            'commitment': result['commitment'],
            'nonce': result['nonce'],
            'estimated_gas': result['estimated_gas'],
            'gas_price': result['gas_price']
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reveal_transfer(request):
    """Reveal a committed transfer (second phase)"""
    commit_hash = request.data.get('commit_hash')
    to_address = request.data.get('to_address')
    amount = request.data.get('amount')
    nonce = request.data.get('nonce')
    
    if not all([commit_hash, to_address, amount, nonce]):
        return Response({
            'error': 'All fields are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        service = SmartContractService()
        result = service.reveal_transfer(
            from_user=request.user,
            commit_hash=commit_hash,
            to_address=to_address,
            amount=Decimal(str(amount)),
            nonce=int(nonce)
        )
        
        return Response({
            'success': True,
            'transaction_hash': result['transaction_hash'],
            'message': 'Transfer revealed and executed successfully'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


# Vesting Operations

class UserVestingScheduleListView(generics.ListAPIView):
    """List user's vesting schedules"""
    serializer_class = VestingScheduleSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return VestingSchedule.objects.filter(
            beneficiary_address=self.request.user.wallet_address,
            is_revoked=False
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def release_vested_tokens(request, schedule_id):
    """Release vested tokens"""
    try:
        schedule = VestingSchedule.objects.get(
            id=schedule_id,
            beneficiary_address=request.user.wallet_address,
            is_revoked=False
        )
    except VestingSchedule.DoesNotExist:
        return Response({
            'error': 'Vesting schedule not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    try:
        service = SmartContractService()
        result = service.release_vested_tokens(schedule)
        
        return Response({
            'success': True,
            'released_amount': result['released_amount'],
            'transaction_hash': result['transaction_hash'],
            'message': 'Vested tokens released successfully'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


# Mining Operations

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def claim_mining_reward(request):
    """Claim mining reward for block validation"""
    block_hash = request.data.get('block_hash')
    
    if not block_hash:
        return Response({
            'error': 'Block hash is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        service = SmartContractService()
        result = service.claim_mining_reward(
            user=request.user,
            block_hash=block_hash
        )
        
        return Response({
            'success': True,
            'reward_amount': result['reward_amount'],
            'transaction_hash': result['transaction_hash'],
            'message': 'Mining reward claimed successfully'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


# User Transaction History

class UserTransactionListView(generics.ListAPIView):
    """List user's smart contract transactions"""
    serializer_class = SmartContractTransactionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        user = self.request.user
        return SmartContractTransaction.objects.filter(
            Q(from_address=user.wallet_address) | Q(to_address=user.wallet_address)
        ).order_by('-created_at')


# Statistics

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_token_stats(request):
    """Get user's token statistics"""
    user = request.user
    
    # Transaction stats
    sent_transactions = SmartContractTransaction.objects.filter(
        from_address=user.wallet_address,
        status='completed'
    )
    received_transactions = SmartContractTransaction.objects.filter(
        to_address=user.wallet_address,
        status='completed'
    )
    
    total_sent = sent_transactions.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    total_received = received_transactions.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    
    # Vesting stats
    vesting_schedules = VestingSchedule.objects.filter(
        beneficiary_address=user.wallet_address,
        is_revoked=False
    )
    total_vesting = vesting_schedules.aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0')
    total_released = vesting_schedules.aggregate(Sum('amount_released'))['amount_released__sum'] or Decimal('0')
    
    # Mining stats
    mining_rewards = MiningReward.objects.filter(miner=user)
    total_mining_rewards = mining_rewards.aggregate(Sum('reward_amount'))['reward_amount__sum'] or Decimal('0')
    
    stats = {
        'total_sent': total_sent,
        'total_received': total_received,
        'transaction_count': sent_transactions.count() + received_transactions.count(),
        'total_vesting': total_vesting,
        'total_released': total_released,
        'total_mining_rewards': total_mining_rewards,
        'mining_blocks_validated': mining_rewards.count(),
    }
    
    serializer = TokenStatsSerializer(stats)
    return Response(serializer.data)


# Admin endpoints

@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_mint_tokens(request):
    """Admin: Mint new tokens"""
    to_address = request.data.get('to_address')
    amount = request.data.get('amount')
    
    if not all([to_address, amount]):
        return Response({
            'error': 'to_address and amount are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        service = SmartContractService()
        result = service.mint_tokens(
            to_address=to_address,
            amount=Decimal(str(amount))
        )
        
        return Response({
            'success': True,
            'transaction_hash': result['transaction_hash'],
            'message': f'Minted {amount} tokens to {to_address}'
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_burn_tokens(request):
    """Admin: Burn tokens from an address"""
    from_address = request.data.get('from_address')
    amount = request.data.get('amount')
    
    if not all([from_address, amount]):
        return Response({
            'error': 'from_address and amount are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        service = SmartContractService()
        result = service.burn_tokens(
            from_address=from_address,
            amount=Decimal(str(amount))
        )
        
        return Response({
            'success': True,
            'transaction_hash': result['transaction_hash'],
            'message': f'Burned {amount} tokens from {from_address}'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_pause_contract(request):
    """Admin: Pause the contract"""
    try:
        service = SmartContractService()
        result = service.pause_contract()
        
        return Response({
            'success': True,
            'transaction_hash': result['transaction_hash'],
            'message': 'Contract paused successfully'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_unpause_contract(request):
    """Admin: Unpause the contract"""
    try:
        service = SmartContractService()
        result = service.unpause_contract()
        
        return Response({
            'success': True,
            'transaction_hash': result['transaction_hash'],
            'message': 'Contract unpaused successfully'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


# Whale Protection Management

class WhaleProtectionLimitListView(generics.ListAPIView):
    """List whale protection limits"""
    serializer_class = WhaleProtectionLimitSerializer
    permission_classes = [IsAdminUser]
    queryset = WhaleProtectionLimit.objects.filter(is_active=True)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_set_whale_limit(request):
    """Admin: Set whale protection limit"""
    serializer = WhaleProtectionLimitSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    try:
        service = SmartContractService()
        result = service.set_whale_protection_limit(
            limit_amount=serializer.validated_data['limit_amount'],
            time_period_hours=serializer.validated_data['time_period_hours']
        )
        
        return Response({
            'success': True,
            'transaction_hash': result['transaction_hash'],
            'message': 'Whale protection limit set successfully'
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


# Fee Management

class FeeExemptionListView(generics.ListAPIView):
    """List fee exemptions"""
    serializer_class = FeeExemptionSerializer
    permission_classes = [IsAdminUser]
    queryset = FeeExemption.objects.filter(is_active=True)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_add_fee_exemption(request):
    """Admin: Add fee exemption for an address"""
    serializer = FeeExemptionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    try:
        service = SmartContractService()
        result = service.add_fee_exemption(
            address=serializer.validated_data['address'],
            reason=serializer.validated_data.get('reason', '')
        )
        
        return Response({
            'success': True,
            'transaction_hash': result['transaction_hash'],
            'message': 'Fee exemption added successfully'
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


# Blacklist Management

class BlacklistedAddressListView(generics.ListAPIView):
    """List blacklisted addresses"""
    serializer_class = BlacklistedAddressSerializer
    permission_classes = [IsAdminUser]
    queryset = BlacklistedAddress.objects.filter(is_active=True)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_blacklist_address(request):
    """Admin: Blacklist an address"""
    serializer = BlacklistedAddressSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    try:
        service = SmartContractService()
        result = service.blacklist_address(
            address=serializer.validated_data['address'],
            reason=serializer.validated_data.get('reason', '')
        )
        
        return Response({
            'success': True,
            'transaction_hash': result['transaction_hash'],
            'message': 'Address blacklisted successfully'
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_unblacklist_address(request, address_id):
    """Admin: Remove address from blacklist"""
    try:
        blacklisted = BlacklistedAddress.objects.get(
            id=address_id,
            is_active=True
        )
    except BlacklistedAddress.DoesNotExist:
        return Response({
            'error': 'Blacklisted address not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    try:
        service = SmartContractService()
        result = service.unblacklist_address(blacklisted.address)
        
        return Response({
            'success': True,
            'transaction_hash': result['transaction_hash'],
            'message': 'Address removed from blacklist successfully'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


# Admin Transaction Management

class AdminTransactionListView(generics.ListAPIView):
    """Admin: List all smart contract transactions"""
    serializer_class = SmartContractTransactionSerializer
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination
    queryset = SmartContractTransaction.objects.all().order_by('-created_at')


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_contract_stats(request):
    """Admin: Get contract statistics"""
    # Transaction stats
    total_transactions = SmartContractTransaction.objects.count()
    completed_transactions = SmartContractTransaction.objects.filter(status='completed').count()
    failed_transactions = SmartContractTransaction.objects.filter(status='failed').count()
    
    # Token stats
    total_supply = SmartContractTransaction.objects.filter(
        transaction_type='mint',
        status='completed'
    ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    
    total_burned = SmartContractTransaction.objects.filter(
        transaction_type='burn',
        status='completed'
    ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    
    # Vesting stats
    total_vesting_schedules = VestingSchedule.objects.filter(is_revoked=False).count()
    total_vesting_amount = VestingSchedule.objects.filter(
        is_revoked=False
    ).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0')
    
    # Mining stats
    total_mining_rewards = MiningReward.objects.aggregate(
        Sum('reward_amount')
    )['reward_amount__sum'] or Decimal('0')
    
    # Protection stats
    active_whale_limits = WhaleProtectionLimit.objects.filter(is_active=True).count()
    fee_exemptions = FeeExemption.objects.filter(is_active=True).count()
    blacklisted_addresses = BlacklistedAddress.objects.filter(is_active=True).count()
    
    stats = {
        'total_transactions': total_transactions,
        'completed_transactions': completed_transactions,
        'failed_transactions': failed_transactions,
        'total_supply': total_supply,
        'total_burned': total_burned,
        'circulating_supply': total_supply - total_burned,
        'total_vesting_schedules': total_vesting_schedules,
        'total_vesting_amount': total_vesting_amount,
        'total_mining_rewards': total_mining_rewards,
        'active_whale_limits': active_whale_limits,
        'fee_exemptions': fee_exemptions,
        'blacklisted_addresses': blacklisted_addresses,
    }
    
    return Response(stats)
