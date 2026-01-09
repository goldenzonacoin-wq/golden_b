from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.pagination import PageNumberPagination
from django.contrib.auth import login, logout
from django.db.models import Q
from django.utils import timezone
import logging
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from subapps.emails.send_email import send_html_email
from django.conf import settings
from .models import User, UserProfile, VerificationCode, UserActivity, Organisation
from .serializers import (
    AddressSerializer,
    CitySerializer,
    CountrySerializer,
    MyUserSerializer as UserSerializer,
    RegionSerializer,
    SubRegionSerializer,
    UserProfileSerializer, UserUpdateSerializer, 
     UserActivitySerializer,
    WalletConnectionSerializer, ReferralSerializer, OrganisationSerializer,
    KYCRewardRequestSerializer
)
from cities_light.models import Country, Region, SubRegion,City
from .models import Address
from rest_framework import generics
from decimal import Decimal
from mainapps.blockchain.kms_signer import KMSWeb3Signer

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

logger = logging.getLogger(__name__)


class UserViewSet(viewsets.ModelViewSet):
    """User management ViewSet"""
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination


    def get_serializer_class(self):
        if self.action in ['update', 'partial_update', ]:
            return UserUpdateSerializer
        return super().get_serializer_class()    
    @action(detail=False, methods=['get', ])
    def me(self, request):
        """Get or update user profile"""
        return Response(UserSerializer(request.user).data)
    
    @action(detail=False, methods=['post'])
    def connect_wallet(self, request):
        """Connect wallet to user account"""
        serializer = WalletConnectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        wallet_address = serializer.validated_data['wallet_address']
        
        # Check if wallet is already connected to another user
        if User.objects.filter(wallet_address=wallet_address).exclude(pk=request.user.pk).exists():
            return Response(
                {'error': 'Wallet address is already connected to another account'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # TODO: Verify signature
        
        # Update user wallet address
        request.user.wallet_address = wallet_address
        request.user.save()
        
        # Log activity
        UserActivity.objects.create(
            user=request.user,
            activity_type='wallet_connect',
            description='User connected wallet',
            ip_address=request.META.get('REMOTE_ADDR', ''),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            metadata={'wallet_address': wallet_address}
        )
        
        return Response({'message': 'Wallet connected successfully'})

    @action(detail=False, methods=['post'], url_path='kyc-reward')
    def kyc_reward(self, request):
        """Submit wallet address and send KYC reward"""
        user = request.user
        if not user.is_kyc_verified:
            return Response(
                {'error': 'KYC approval required before claiming reward'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if user.has_been_kyc_rewarded:
            return Response(
                {'error': 'KYC reward already claimed'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = KYCRewardRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        wallet_address = serializer.validated_data['wallet_address']

        if user.wallet_address and user.wallet_address.lower() != wallet_address.lower():
            return Response(
                {'error': 'Wallet address does not match your saved address'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if User.objects.filter(wallet_address=wallet_address).exclude(pk=user.pk).exists():
            return Response(
                {'error': 'Wallet address is already connected to another account'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            signer = KMSWeb3Signer()
            reward_amount = Decimal(str(settings.KYC_REWARD_AMOUNT))
            tx_hash = signer.send_token_transfer(wallet_address, reward_amount)
        except Exception as exc:
            logger.exception("Failed to send KYC reward for user %s", user.id)
            return Response(
                {'error': 'Failed to send KYC reward'},
                status=status.HTTP_502_BAD_GATEWAY
            )

        user.wallet_address = wallet_address
        user.has_been_kyc_rewarded = True
        user.save(update_fields=['wallet_address', 'has_been_kyc_rewarded'])

        UserActivity.objects.create(
            user=user,
            activity_type='kyc_reward',
            description='KYC reward sent',
            ip_address=request.META.get('REMOTE_ADDR', ''),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            metadata={'wallet_address': wallet_address, 'tx_hash': tx_hash}
        )

        return Response(
            {
                'success': True,
                'wallet_address': wallet_address,
                'tx_hash': tx_hash,
                'amount': str(settings.KYC_REWARD_AMOUNT),
            },
            status=status.HTTP_200_OK
        )
    
    @action(detail=False, methods=['post'])
    def apply_referral(self, request):
        """Apply referral code"""
        serializer = ReferralSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        referral_code = serializer.validated_data['referral_code']
        referrer_profile = UserProfile.objects.get(referral_code=referral_code)
        
        # Update user's referred_by field
        user_profile = request.user.profile
        if user_profile.referred_by:
            return Response(
                {'error': 'You have already used a referral code'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user_profile.referred_by = referrer_profile.user
        user_profile.save()
        
        # Award points to referrer
        referrer_profile.contribution_points += 100
        referrer_profile.save()
        
        return Response({'message': 'Referral code applied successfully'})
    
    @action(detail=False, methods=['get'])
    def search(self, request):
        """Search users"""
        query = request.query_params.get('q', '')
        if query:
            queryset = User.objects.filter(
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(email__icontains=query)
            ).filter(is_active=True)
            
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
        return Response([])


class UserProfileViewSet(viewsets.ModelViewSet):
    """User profile management ViewSet"""
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return UserProfile.objects.filter(user=self.request.user)
    
    def get_object(self):
        return self.request.user.profile


class UserActivityViewSet(viewsets.ReadOnlyModelViewSet):
    """User activity ViewSet (read-only)"""
    serializer_class = UserActivitySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        return UserActivity.objects.filter(user=self.request.user)


class VerificationAPI(APIView):
    throttle_classes = [AnonRateThrottle]
    def post(self, request):
        """Handle both sending verification code and verifying code submission (POST)"""
        action = request.data.get('action')

        if action == 'send_code':
            return self.send_verification_code(request)
        elif action == 'verify_code':
            return self.verify_code(request)
        else:
            return Response(
                {"error": "Invalid action. Use 'send_code' or 'verify_code'."},
                status=status.HTTP_400_BAD_REQUEST
            )

    def send_verification_code(self, request):
        """Send verification code via email"""
        email = request.data.get('email')

        if not email:
            return Response(
                {"error": "Email parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            user = User.objects.get(email=email)
            code, created = VerificationCode.objects.get_or_create(user=user)
            code.save()  # Ensure the code is saved or updated
            
            send_html_email(
                subject=f'Your Verification Code: {code.code}',
                message=f'Use this code to verify your login: {code.code}',
                to_email=[user.email],
                html_file='accounts/verify.html'
            )
            
            return Response(
                {"message": "Verification code sent successfully"},
                status=status.HTTP_200_OK
            )
            
        except User.DoesNotExist:
            return Response(
                {"error": "User  not found with this email"},
                status=status.HTTP_404_NOT_FOUND
            )

    def verify_code(self, request):
        """Verify code submission"""
        email = request.data.get('email')
        code_input = request.data.get('code')
        
        if not email or not code_input:
            return Response(
                {"error": "Both email and code are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(email=email)

            verification_code = VerificationCode.objects.get(user=user)
            if not verification_code.is_valid():
                return Response(
                    {"error": "Verification code has expired"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if str(verification_code.code) != code_input.strip():
                return Response(
                    {"error": "Invalid verification code"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            return Response(
                {
                    "message": "Verification successful",
                    "user_id": user.id,
                    "email": user.email
                },
                status=status.HTTP_200_OK
            )
            
        except User.DoesNotExist:
            return Response(
                {"error": "User  not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except VerificationCode.DoesNotExist:
            return Response(
                {"error": "No active verification code for this user"},
                status=status.HTTP_400_BAD_REQUEST
            )

class OrganisationViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing organisation instances.
    """
    serializer_class = OrganisationSerializer
    queryset = Organisation.objects.all()





class CountryListView(generics.ListAPIView):
    queryset = Country.objects.all()
    serializer_class = CountrySerializer

class RegionListView(generics.ListAPIView):
    serializer_class = RegionSerializer

    def get_queryset(self):
        country_id = self.request.query_params.get('country_id')
        return Region.objects.filter(country_id=country_id)

class SubRegionListView(generics.ListAPIView):
    serializer_class = SubRegionSerializer

    def get_queryset(self):
        region_id = self.request.query_params.get('region_id')
        return SubRegion.objects.filter(region_id=region_id)

class CityListView(generics.ListAPIView):
    serializer_class = CitySerializer

    def get_queryset(self):
        subregion_id = self.request.query_params.get('subregion_id')
        return City.objects.filter(subregion_id=subregion_id)
    

class AddressViewSet(viewsets.ModelViewSet):
    queryset = Address.objects.all()
    serializer_class = AddressSerializer
