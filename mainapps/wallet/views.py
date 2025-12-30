from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.conf import settings
from cryptography.fernet import Fernet
import secrets
import hashlib
import json
from mnemonic import Mnemonic
from eth_account import Account
from web3 import Web3
from decimal import Decimal

from .models import WalletSession, WalletCreationLog, WalletRecoveryAttempt
from .serializers import (
    WalletCreateSerializer, WalletRecoverySerializer, 
    WalletSessionSerializer, WalletInfoSerializer, TransactionSerializer
)

User = get_user_model()

def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def encrypt_private_key(private_key: str, password: str) -> str:
    """Encrypt private key with user password"""
    key = hashlib.pbkdf2_hmac('sha256', password.encode(), b'salt', 100000)
    # Fernet requires base64-encoded key
    import base64
    fernet_key = base64.urlsafe_b64encode(key)
    f = Fernet(fernet_key)
    return f.encrypt(private_key.encode()).decode()

def decrypt_private_key(encrypted_key: str, password: str) -> str:
    """Decrypt private key with user password"""
    key = hashlib.pbkdf2_hmac('sha256', password.encode(), b'salt', 100000)
    # Fernet requires base64-encoded key
    import base64
    fernet_key = base64.urlsafe_b64encode(key)
    f = Fernet(fernet_key)
    return f.decrypt(encrypted_key.encode()).decode()

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def create_wallet(request):
    """Create a new wallet for the user"""
    serializer = WalletCreateSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    
    user = request.user
    
    # Check if user already has a wallet
    if user.wallet_address:
        return Response({
            'error': 'User already has a wallet'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Generate mnemonic phrase
        mnemo = Mnemonic("english")
        mnemonic_phrase = mnemo.generate(strength=256)  # 24 words
        
        # Generate account from mnemonic
        Account.enable_unaudited_hdwallet_features()
        account = Account.from_mnemonic(mnemonic_phrase)
        
        # Update user with wallet address
        user.wallet_address = account.address
        user.save()
        
        # Create wallet creation log
        recovery_phrase_hash = hashlib.sha256(mnemonic_phrase.encode()).hexdigest()
        WalletCreationLog.objects.create(
            user=user,
            wallet_address=account.address,
            recovery_phrase_hash=recovery_phrase_hash,
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        return Response({
            'success': True,
            'wallet_address': account.address,
            'recovery_phrase': mnemonic_phrase,
            'message': 'Wallet created successfully. Please save your recovery phrase securely.'
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({
            'error': f'Failed to create wallet: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def recover_wallet(request):
    """Recover wallet using mnemonic phrase"""
    serializer = WalletRecoverySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    user = request.user
    recovery_phrase = serializer.validated_data['recovery_phrase']
    ip_address = get_client_ip(request)
    
    try:
        # Validate mnemonic
        mnemo = Mnemonic("english")
        if not mnemo.check(recovery_phrase):
            WalletRecoveryAttempt.objects.create(
                user=user,
                ip_address=ip_address,
                success=False,
                error_message="Invalid recovery phrase"
            )
            return Response({
                'error': 'Invalid recovery phrase'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Generate account from mnemonic
        Account.enable_unaudited_hdwallet_features()
        account = Account.from_mnemonic(recovery_phrase)
        
        # Update user's wallet address if they don't have one or if it's different
        if not user.wallet_address:
            user.wallet_address = account.address
            user.save()
        elif user.wallet_address.lower() != account.address.lower():
            # User is trying to connect a different wallet
            return Response({
                'error': 'This recovery phrase belongs to a different wallet than your current one'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create wallet session with encrypted private key
        session_password = secrets.token_urlsafe(32)
        encrypted_private_key = encrypt_private_key(account.key.hex(), session_password)
        
        # Deactivate old sessions
        WalletSession.objects.filter(user=user, is_active=True).update(is_active=False)
        
        # Create new session
        wallet_session = WalletSession.objects.create(
            user=user,
            encrypted_private_key=encrypted_private_key
        )
        
        # Log successful recovery
        WalletRecoveryAttempt.objects.create(
            user=user,
            ip_address=ip_address,
            success=True
        )
        
        return Response({
            'success': True,
            'session_token': wallet_session.session_token,
            'session_password': session_password,
            'wallet_address': account.address,
            'expires_at': wallet_session.expires_at,
            'message': 'Wallet recovered successfully'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        WalletRecoveryAttempt.objects.create(
            user=user,
            ip_address=ip_address,
            success=False,
            error_message=str(e)
        )
        return Response({
            'error': f'Failed to recover wallet: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def wallet_info(request):
    """Get user's wallet information"""
    user = request.user
    
    # Check for active session
    active_session = WalletSession.objects.filter(
        user=user,
        is_active=True
    ).first()
    
    session_active = active_session.is_valid() if active_session else False
    
    wallet_info = {
        'wallet_address': user.wallet_address,
        'has_wallet': bool(user.wallet_address),
        'atc_balance': user.atc_balance,
        'session_active': session_active
    }
    
    serializer = WalletInfoSerializer(wallet_info)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def create_transaction(request):
    """Create and sign a transaction"""
    serializer = TransactionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    user = request.user
    to_address = serializer.validated_data['to_address']
    amount = serializer.validated_data['amount']
    gas_price = serializer.validated_data.get('gas_price')
    
    # Check if user has an active wallet session
    active_session = WalletSession.objects.filter(
        user=user,
        is_active=True
    ).first()
    
    if not active_session or not active_session.is_valid():
        return Response({
            'error': 'No active wallet session. Please recover your wallet first.'
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    # Get session password from request headers
    session_password = request.META.get('HTTP_X_SESSION_PASSWORD')
    if not session_password:
        return Response({
            'error': 'Session password required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Decrypt private key
        private_key = decrypt_private_key(active_session.encrypted_private_key, session_password)
        account = Account.from_key(private_key)
        
        # Verify account matches user's wallet
        if account.address.lower() != user.wallet_address.lower():
            return Response({
                'error': 'Session account mismatch'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Check balance (simplified - in production, check on-chain)
        if user.atc_balance < amount:
            return Response({
                'error': 'Insufficient balance'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create transaction data (simplified)
        transaction_data = {
            'from': account.address,
            'to': to_address,
            'amount': str(amount),
            'gas_price': str(gas_price) if gas_price else None,
            'timestamp': timezone.now().isoformat()
        }
        
        # In production, this would:
        # 1. Connect to blockchain network
        # 2. Build actual transaction
        # 3. Sign with private key
        # 4. Broadcast to network
        # 5. Return transaction hash
        
        # For now, return mock transaction hash
        mock_tx_hash = f"0x{secrets.token_hex(32)}"
        
        # Update session last used
        active_session.last_used = timezone.now()
        active_session.save()
        
        return Response({
            'success': True,
            'transaction_hash': mock_tx_hash,
            'transaction_data': transaction_data,
            'message': 'Transaction created successfully'
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({
            'error': f'Failed to create transaction: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def end_wallet_session(request):
    """End active wallet session"""
    user = request.user
    
    # Deactivate all active sessions
    updated_count = WalletSession.objects.filter(
        user=user,
        is_active=True
    ).update(is_active=False)
    
    return Response({
        'success': True,
        'message': f'Ended {updated_count} wallet session(s)'
    })

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def wallet_sessions(request):
    """Get user's wallet sessions"""
    user = request.user
    sessions = WalletSession.objects.filter(user=user).order_by('-created_at')[:10]
    
    serializer = WalletSessionSerializer(sessions, many=True)
    return Response(serializer.data)
