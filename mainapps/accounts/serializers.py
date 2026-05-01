from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from django.core.exceptions import ValidationError
from .models import Organisation, User, UserProfile, VerificationCode, UserActivity
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.serializers import TokenRefreshSerializer as BaseTokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from djoser.serializers import UserCreateSerializer as BaseUserCreateSerializer
from cities_light.models import Country, Region, SubRegion,City
from .models import Address
from web3 import Web3


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Custom JWT token serializer for blockchain app with enhanced user data"""

    @classmethod
    def get_all_permissions(cls, user):
        """Get all permissions for user including blockchain-specific permissions"""
        user_perms = set()
        
        # Add user permissions
        user_perms.update(user.user_permissions.all().values_list('codename', flat=True))
        
        # Add group permissions
        for group in user.groups.all():
            user_perms.update(group.permissions.all().values_list('codename', flat=True))
        
        # Add role-based permissions if user has roles
        try:
            current_time = timezone.now()
            # Check if user has any role-based permissions (if implemented)
            if hasattr(user, 'roles'):
                for role in user.roles.all().iterator():
                    if hasattr(role, 'start_date') and hasattr(role, 'end_date'):
                        if role.end_date and role.end_date < current_time:
                            role.delete()
                        else:
                            if hasattr(role, 'permissions'):
                                perms = role.permissions.all().values_list('codename', flat=True)
                                user_perms.update(perms)
        except Exception as e:
            print(f"Role permissions error: {e}")
        
        # Add blockchain-specific permissions based on membership tier
        if user.membership_tier == 'WHALE':
            user_perms.update(['can_create_proposals', 'can_vote_governance', 'can_access_whale_features'])
        elif user.membership_tier == 'PREMIUM':
            user_perms.update(['can_vote_governance', 'can_access_premium_features'])
        elif user.membership_tier == 'BASIC':
            user_perms.update(['can_access_basic_features'])
        
        # Add KYC-based permissions
        if user.is_kyc_verified:
            user_perms.update(['can_trade_tokens', 'can_participate_ico', 'can_access_advanced_features'])
        
        return user_perms

    @classmethod
    def _build_user_payload(cls, user):
        profile = getattr(user, 'profile', None)

        data = {
            'id': user.id,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'full_name': user.get_full_name,
            'role': user.role,
            'membership_tier': user.membership_tier,
            'wallet_address': user.wallet_address,
            'is_whale': user.is_whale,
            'is_verified': user.is_verified,
            'is_active': user.is_active,
            'is_staff': bool(user.is_staff),
            'is_superuser': bool(getattr(user, 'is_superuser', False)),
            'is_kyc_verified': user.is_kyc_verified,
            'has_been_kyc_rewarded': user.has_been_kyc_rewarded,
            'phone_number': user.phone_number,
            'profile_id': profile.id if profile else None,
            'reputation_score': profile.reputation_score if profile else 0,
            'contribution_points': profile.contribution_points if profile else 0,
            'referral_code': profile.referral_code if profile else None,
            'mfa_enabled': bool(user.mfa_enabled),
            'has_setup_mfa': bool(user.has_setup_mfa),
        }

        try:
            from mainapps.kyc.models import KYCApplication
            kyc_app = KYCApplication.objects.filter(user=user).first()
            data.update(
                {
                'kyc_status': kyc_app.status if kyc_app else 'NOT_SUBMITTED',
                'kyc_level': kyc_app.verification_level if kyc_app else 'NONE',
                'kyc_submitted_at': kyc_app.submitted_at if kyc_app else None,
                }
            )
        except Exception:
            data.update(
                {
                'kyc_status': 'NOT_SUBMITTED',
                'kyc_level': 'NONE',
                'kyc_submitted_at': None,
                }
            )
        return data

    @classmethod
    def _session_mfa_verified(cls, user, mfa_verified=None):
        if mfa_verified is not None:
            return bool(mfa_verified)
        return not user.requires_mfa

    @classmethod
    def _apply_claims(cls, token, user):
        payload = cls._build_user_payload(user)
        token['permissions'] = list(cls.get_all_permissions(user))
        token['email'] = user.email
        token['user_id'] = user.id
        token['role'] = user.role
        token['membership_tier'] = user.membership_tier
        token['first_name'] = user.first_name or ''
        token['last_name'] = user.last_name or ''
        token['wallet_address'] = user.wallet_address
        token['is_verified'] = user.is_verified
        token['is_active'] = user.is_active
        token['is_staff'] = bool(user.is_staff)
        token['is_superuser'] = bool(getattr(user, 'is_superuser', False))
        token['is_kyc_verified'] = user.is_kyc_verified
        token['has_been_kyc_rewarded'] = user.has_been_kyc_rewarded
        token['profile_id'] = payload['profile_id']
        token['reputation_score'] = payload['reputation_score']
        token['contribution_points'] = payload['contribution_points']
        token['mfa_enabled'] = bool(user.mfa_enabled)
        token['has_setup_mfa'] = bool(user.has_setup_mfa)
        token['mfa_verified'] = bool(getattr(user, '_jwt_mfa_verified', False))
        token['kyc_status'] = payload['kyc_status']
        token['kyc_level'] = payload['kyc_level']

    @classmethod
    def issue_tokens_for_user(cls, user, mfa_verified=None):
        setattr(user, '_jwt_mfa_verified', cls._session_mfa_verified(user, mfa_verified))
        try:
            refresh = cls.get_token(user)
            access = refresh.access_token
            return refresh, access
        finally:
            if hasattr(user, '_jwt_mfa_verified'):
                delattr(user, '_jwt_mfa_verified')

    @classmethod
    def get_token(cls, user):
        """Generate token with blockchain-specific claims"""
        token = super().get_token(user)
        cls._apply_claims(token, user)
        return token

    def validate(self, attrs):
        """Validate and return enhanced user data"""
        email = attrs.get(self.username_field) or attrs.get("email")
        password = attrs.get("password")

        user = None
        if email:
            user = User.objects.filter(email__iexact=email).first()

        if not user:
            raise AuthenticationFailed("No account found with this email.", code="email_not_found")
        if not user.is_active:
            raise AuthenticationFailed("This account is inactive.", code="account_disabled")
        if password and not user.check_password(password):
            raise AuthenticationFailed("Incorrect password.", code="password_mismatch")

        data = super().validate(attrs)
        refresh, access = self.issue_tokens_for_user(self.user)
        data['refresh'] = str(refresh)
        data['access'] = str(access)
        data['mfa_verified'] = self._session_mfa_verified(self.user)
        data.update(self._build_user_payload(self.user))
        return data


class TokenRefreshSerializer(BaseTokenRefreshSerializer):
    """Attach custom claims to refreshed access tokens."""

    def validate(self, attrs):
        data = super().validate(attrs)
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        raw_refresh = data.get("refresh") or attrs.get("refresh")

        if (not user or not user.is_authenticated) and raw_refresh:
            try:
                refresh_token = RefreshToken(raw_refresh)
                user_id = refresh_token.get("user_id")
                if user_id:
                    user = User.objects.filter(id=user_id).first()
            except Exception:
                user = None

        if not user or not user.is_authenticated:
            return data

        mfa_verified = None
        if raw_refresh:
            try:
                refresh_payload = RefreshToken(raw_refresh)
                mfa_verified = bool(refresh_payload.get("mfa_verified"))
            except Exception:
                mfa_verified = None

        custom_refresh, custom_access = MyTokenObtainPairSerializer.issue_tokens_for_user(
            user,
            mfa_verified=MyTokenObtainPairSerializer._session_mfa_verified(user, mfa_verified),
        )
        data["access"] = str(custom_access)
        if "refresh" in data:
            data["refresh"] = str(custom_refresh)
        data["mfa_verified"] = MyTokenObtainPairSerializer._session_mfa_verified(user, mfa_verified)
        data.update(MyTokenObtainPairSerializer._build_user_payload(user))
        return data


class UserCreateSerializer(BaseUserCreateSerializer):
    class Meta(BaseUserCreateSerializer.Meta):
        model = User
        fields = ('id', 'email', 'first_name', 'last_name', 'password')
        
    def create(self, validated_data):
        
        first_name = validated_data.get('first_name', '')
        last_name = validated_data.get('last_name', '')
        
        # Create the user with explicit parameters
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=first_name,
            last_name=last_name
        )
        
        # Log the created user
        
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for user profile"""
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_full_name = serializers.CharField(source='user.get_full_name', read_only=True)
    user_role = serializers.CharField(source='user.role', read_only=True)
    user_membership_tier = serializers.CharField(source='user.membership_tier', read_only=True)
    
    class Meta:
        model = UserProfile
        fields = (
            'user_email', 'user_full_name', 'user_role', 'user_membership_tier',
            'bio', 'profile_image', 'cover_image', 'occupation', 'company', 
            'website', 'twitter_handle', 'linkedin_profile', 'github_profile',
            'discord_handle', 'telegram_handle',  'reputation_score',
            'contribution_points', 'referral_code', 'show_wallet_address',
            'show_token_balance', 'allow_direct_messages', 'created_at'
        )
        read_only_fields = (
            'user_email', 'user_full_name', 'user_role', 'user_membership_tier',
            'reputation_score', 'contribution_points', 'referral_code', 'created_at'
        )


class MyUserSerializer(serializers.ModelSerializer):
    """Serializer for user details"""
    profile = UserProfileSerializer(read_only=True)
    wallet_address_short = serializers.SerializerMethodField()
    is_whale = serializers.ReadOnlyField()
    
    class Meta:
        model = User
        fields = (
            'id', 'email', 'first_name', 'last_name', 'get_full_name',
            'role', 'membership_tier', 'wallet_address', 'wallet_address_short',
             'is_whale', 'is_verified', 'is_active', 'is_staff', 'is_superuser', 'is_kyc_verified',
            'has_been_kyc_rewarded', 'phone_number', 'date_of_birth',
            'mfa_enabled', 'has_setup_mfa', 'created_at', 'profile'
        )
        read_only_fields = (
            'id', 'get_full_name', 'is_whale', 
            'is_verified', 'is_active', 'is_staff', 'is_superuser', 'is_kyc_verified', 'has_been_kyc_rewarded',
            'mfa_enabled', 'has_setup_mfa', 'created_at'
        )
    
    def get_wallet_address_short(self, obj):
        if obj.wallet_address:
            return f"{obj.wallet_address[:6]}...{obj.wallet_address[-4:]}"
        return None


class UserUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating user information"""
    
    class Meta:
        model = User
        fields = (
            'first_name', 'last_name', 'phone_number', 
            'date_of_birth', 'wallet_address'
        )
    
    def validate_wallet_address(self, value):
        if value and User.objects.filter(wallet_address=value).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError("This wallet address is already registered")
        return value


class UserActivitySerializer(serializers.ModelSerializer):
    """Serializer for user activities"""
    
    class Meta:
        model = UserActivity
        fields = (
            'activity_type', 'description', 'ip_address', 
            'user_agent', 'metadata', 'created_at'
        )
        read_only_fields = ('created_at',)


class WalletConnectionSerializer(serializers.Serializer):
    """Serializer for wallet connection"""
    wallet_address = serializers.CharField(max_length=42)
    signature = serializers.CharField()


class KYCRewardRequestSerializer(serializers.Serializer):
    wallet_address = serializers.CharField(max_length=42)

    def validate_wallet_address(self, value):
        if not Web3.is_address(value):
            raise serializers.ValidationError("Invalid wallet address format")
        return Web3.to_checksum_address(value)
    message = serializers.CharField()
    
    def validate_wallet_address(self, value):
        from .models import validate_wallet_address
        try:
            validate_wallet_address(value)
        except ValidationError as e:
            raise serializers.ValidationError(str(e))
        return value


class ReferralSerializer(serializers.Serializer):
    """Serializer for referral information"""
    referral_code = serializers.CharField(max_length=10)
    
    def validate_referral_code(self, value):
        try:
            profile = UserProfile.objects.get(referral_code=value)
            if profile.user == self.context['request'].user:
                raise serializers.ValidationError("Cannot use your own referral code")
        except UserProfile.DoesNotExist:
            raise serializers.ValidationError("Invalid referral code")
        return value


class OrganisationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organisation
        fields = '__all__'





class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ['id', 'name']

class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = ['id', 'name', 'country']

class SubRegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubRegion
        fields = ['id', 'name', 'region']

class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ['id', 'name', 'subregion']






class AddressSerializer(serializers.ModelSerializer):
    

    class Meta:
        model = Address
        fields = '__all__'

    def create(self, validated_data):
        # Create instance but don't save yet
        instance = Address(**validated_data)
        try:
            instance.full_clean()  # Validate model fields
        except ValidationError as e:
            raise serializers.ValidationError(e.message_dict)
        instance.save()
        return instance

    def update(self, instance, validated_data):
        # Update instance attributes
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        try:
            instance.full_clean()  # Validate updated instance
        except ValidationError as e:
            raise serializers.ValidationError(e.message_dict)
        instance.save()
        return instance
