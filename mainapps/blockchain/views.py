from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.pagination import PageNumberPagination
from django.db.models import Sum, Count, Avg, Q
from django.utils import timezone
from django.conf import settings
from decimal import Decimal
from uuid import uuid4
import requests
from .models import (
    BlockchainNetwork, TokenContract, WalletBalance, Transaction,
    StakingPool, UserStake, VestingSchedule, BlockchainEvent,
    TokenPurchase, TokenPurchaseSettings
)
from .serializers import (
    BlockchainNetworkSerializer, TokenContractSerializer,
    WalletBalanceSerializer, TransactionSerializer, StakingPoolSerializer,
    UserStakeSerializer, StakeCreateSerializer, VestingScheduleSerializer,
    BlockchainEventSerializer, WalletStatsSerializer, NetworkStatsSerializer,
    TokenPurchaseSerializer, TokenPurchaseInitiateSerializer
)
from rest_framework.views import APIView
from .kms_signer import KmsTokenTransfer
from django.core.exceptions import ValidationError
from web3 import Web3
import logging

logger = logging.getLogger(__name__)


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


class TokenPurchaseListCreateView(generics.ListCreateAPIView):
    """List and initialize token purchases."""
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return TokenPurchase.objects.filter(user_id=self.request.user.id).order_by('-created_at')

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return TokenPurchaseInitiateSerializer
        return TokenPurchaseSerializer

    def create(self, request, *args, **kwargs):
        init_serializer = TokenPurchaseInitiateSerializer(data=request.data)
        init_serializer.is_valid(raise_exception=True)

        user = request.user
        purchase_settings = self._get_purchase_settings()
        if not purchase_settings.is_active:
            return Response(
                {'detail': 'Token purchase is currently disabled.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            usd_price = Decimal(str(purchase_settings.token_price_usd))
        except Exception:
            usd_price = Decimal('0')

        if usd_price <= 0:
            return Response(
                {'detail': 'Token purchase price is not configured.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        token_amount = init_serializer.validated_data['token_amount']
        usd_amount = (token_amount * usd_price).quantize(Decimal("0.01"))
        requested_currency = init_serializer.validated_data.get('currency')

        secret_key = getattr(settings, 'FLUTTERWAVE_SECRET_KEY', None)
        if not secret_key:
            return Response(
                {'detail': 'Flutterwave secret key is not configured on the server.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        public_key = (
            getattr(settings, 'FLUTTERWAVE_PUBLIC_KEY', None)
            or getattr(settings, 'FLUTTERWAVE_PUB_KEY', None)
        )
        if not public_key:
            return Response(
                {'detail': 'Flutterwave public key is not configured on the server.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        try:
            amount, currency = self._determine_charge_amount(usd_amount, requested_currency)
        except ValidationError as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_400_BAD_REQUEST
            )
        if amount <= 0:
            return Response(
                {'detail': 'Invalid token purchase amount configured.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        tx_ref = f"token-{user.id}-{uuid4().hex[:10]}"
        redirect_url = init_serializer.validated_data.get('redirect_url') or getattr(
            settings, 'FLUTTERWAVE_REDIRECT_URL', None
        )
        wallet_address = init_serializer.validated_data['wallet_address']

        payload = {
            "tx_ref": tx_ref,
            "amount": float(amount),
            "currency": currency,
            "payment_options": "card,account,ussd,banktransfer",
            "redirect_url": redirect_url,
            "customer": {
                "email": user.email,
                "name": user.get_full_name or user.email,
            },
            "meta": {
                "user_id": user.id,
                "token_purchase": True,
                "token_amount": str(token_amount),
                "wallet_address": wallet_address,
                "usd_amount": str(usd_amount),
                "usd_price_per_token": str(usd_price),
            },
            "customizations": {
                "title": getattr(settings, 'SITE_NAME', 'Token Purchase'),
                "description": "Token purchase payment",
            },
            "public_key": public_key,
        }

        phone_number = getattr(getattr(user, 'profile', None), 'phone_number', None) or getattr(user, 'phone_number', None)
        if phone_number:
            payload["customer"]["phone_number"] = phone_number

        base_url = getattr(settings, 'FLUTTERWAVE_BASE_URL', 'https://api.flutterwave.com/v3')
        try:
            gateway_response = requests.post(
                f"{base_url.rstrip('/')}/payments",
                json=payload,
                headers={
                    "Authorization": f"Bearer {secret_key}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            gateway_response.raise_for_status()
            response_data = gateway_response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.exception("Failed to initialize Flutterwave token purchase")
            return Response(
                {'detail': 'Unable to initialize payment at the moment.'},
                status=status.HTTP_502_BAD_GATEWAY
            )

        payment_data = response_data.get('data') if isinstance(response_data, dict) else {}
        payment_link = payment_data.get('link')
        flw_ref = payment_data.get('flw_ref') or payment_data.get('id')

        if not payment_link:
            logger.error("Flutterwave response missing payment link: %s", response_data)
            return Response(
                {'detail': 'Payment link not returned by gateway.'},
                status=status.HTTP_502_BAD_GATEWAY
            )

        purchase = TokenPurchase.objects.create(
            user_id=user.id,
            wallet_address=wallet_address,
            token_amount=token_amount,
            usd_price_per_token=usd_price,
            usd_amount=usd_amount,
            charge_amount=amount,
            currency=currency,
            tx_ref=tx_ref,
            flw_ref=flw_ref,
            status=TokenPurchase.Status.PENDING,
            payment_link=payment_link,
            init_payload={"request": payload, "response": response_data},
        )

        return Response(
            {
                'message': 'Token purchase initialized successfully.',
                'purchase': TokenPurchaseSerializer(purchase).data,
                'flutterwave_payload': payload,
            },
            status=status.HTTP_201_CREATED
        )

    def _get_purchase_settings(self):
        settings_obj, _ = TokenPurchaseSettings.objects.get_or_create()
        return settings_obj

    def _determine_charge_amount(self, usd_amount: Decimal, requested_currency: str):
        base_currency = 'USD'
        target_currency = (requested_currency or base_currency).upper()

        if target_currency == base_currency:
            return usd_amount, base_currency

        converted_amount = self._convert_currency(
            amount=usd_amount,
            from_currency=base_currency,
            to_currency=target_currency
        )
        return converted_amount, target_currency

    def _convert_currency(self, amount: Decimal, from_currency: str, to_currency: str) -> Decimal:
        try:
            return self._convert_currency_with_freecurrencyapi(amount, from_currency, to_currency)
        except ValidationError:
            pass
        return self._convert_currency_with_fixer(amount, from_currency, to_currency)

    def _convert_currency_with_freecurrencyapi(self, amount: Decimal, from_currency: str, to_currency: str) -> Decimal:
        api_key = getattr(settings, "EXCHANGERATE_API_KEY", None)
        if not api_key:
            raise ValidationError("Freecurrencyapi API key is not configured.")

        from_currency = (from_currency or "").upper()
        to_currency = (to_currency or "").upper()
        if not from_currency or not to_currency:
            raise ValidationError("Both source and destination currencies are required.")

        try:
            response = requests.get(
                "https://api.freecurrencyapi.com/v1/latest",
                params={
                    "apikey": api_key,
                    "base_currency": from_currency,
                    "currencies": to_currency,
                },
                timeout=20,
            )
            data = response.json()
        except requests.RequestException as exc:
            logger.error("Error calling freecurrencyapi: %s", exc, exc_info=True)
            raise ValidationError(f"Error getting exchange rate: {exc}") from exc
        except ValueError as exc:
            raise ValidationError("Received invalid response from freecurrencyapi.") from exc

        rate = (data.get("data") or {}).get(to_currency)
        if rate is None:
            raise ValidationError(f"Exchange rate not found for {to_currency}.")

        try:
            amount_decimal = Decimal(str(amount))
            converted_amount = (amount_decimal * Decimal(str(rate))).quantize(Decimal("0.01"))
        except Exception as exc:  # noqa: BLE001
            logger.error("Invalid conversion calculation from freecurrencyapi: %s", exc, exc_info=True)
            raise ValidationError("Invalid exchange rate received from freecurrencyapi.") from exc

        return converted_amount

    def _convert_currency_with_fixer(self, amount: Decimal, from_currency: str, to_currency: str) -> Decimal:
        api_key = getattr(settings, "FIXER_API_KEY", None)
        if not api_key:
            raise ValidationError("Fixer API key is not configured on the server.")

        from_currency = (from_currency or "").upper()
        to_currency = (to_currency or "").upper()
        if not from_currency or not to_currency:
            raise ValidationError("Both source and destination currencies are required.")

        try:
            response = requests.get(
                "https://data.fixer.io/api/latest",
                params={
                    "access_key": api_key,
                    "symbols": f"{from_currency},{to_currency}",
                },
                timeout=20,
            )
            data = response.json()
        except requests.RequestException as exc:
            logger.error("Error calling Fixer API: %s", exc, exc_info=True)
            raise ValidationError(f"Error getting exchange rate: {exc}") from exc
        except ValueError as exc:
            raise ValidationError("Received invalid response from Fixer API.") from exc

        if not data.get("success", True):
            error_info = data.get("error", {}).get("info") or "Fixer API error."
            raise ValidationError(error_info)

        rates = data.get("rates") or {}
        from_rate = rates.get(from_currency)
        to_rate = rates.get(to_currency)
        if from_rate is None or to_rate is None:
            raise ValidationError(f"Exchange rate not found for {to_currency}.")

        try:
            amount_decimal = Decimal(str(amount))
            converted_amount = (amount_decimal * (Decimal(str(to_rate)) / Decimal(str(from_rate)))).quantize(Decimal("0.01"))
        except Exception as exc:  # noqa: BLE001
            logger.error("Invalid conversion calculation from Fixer API: %s", exc, exc_info=True)
            raise ValidationError("Invalid exchange rate received from Fixer API.") from exc

        return converted_amount


class TokenPurchaseSettingsView(APIView):
    """Expose token purchase settings for the frontend."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        settings_obj, _ = TokenPurchaseSettings.objects.get_or_create()
        return Response(
            {
                'token_price_usd': str(settings_obj.token_price_usd),
                'is_active': settings_obj.is_active,
            }
        )


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




class TokenTransferView(APIView):
    def post(self, request):
        recipient = request.data.get('recipient')
        amount = request.data.get('amount')
        
        if not recipient or not amount:
            return Response(
                {"error": "Missing recipient or amount"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            recipient = Web3.to_checksum_address(recipient)
            
            service = KmsTokenTransfer()  
            result = service.transfer_tokens(  
                recipient=recipient,
                amount_tokens=float(Decimal(amount))  
            )
            
            return Response({
                "message": "Tokens transferred successfully",
                "transaction": {
                    "tx_hash": result['tx_hash'],
                    "explorer_url": result['explorer_url'],
                    "amount": result['amount'],
                    "recipient": result['recipient']
                }
            }, status=status.HTTP_200_OK)
            
        except ValueError as ve:
            return Response(
                {"error": str(ve)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Transfer failed: {str(e)}")
            return Response(
                {"error": "Internal error during transfer"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
