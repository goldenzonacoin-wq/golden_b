from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import Organisation, User, UserProfile, VerificationCode, UserActivity
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
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
    def get_token(cls, user):
        """Generate token with blockchain-specific claims"""
        token = super().get_token(user)
        # Get user permissions
        perms = cls.get_all_permissions(user)
        token['permissions'] = list(perms)
        # Basic user info
        token['email'] = user.email
        token['user_id'] = user.id
        token['role'] = user.role
        token['membership_tier'] = user.membership_tier
        # Profile information
        profile = getattr(user, 'profile', None)
        token['profile_id'] = profile.id if profile else None
        token['reputation_score'] = profile.reputation_score if profile else 0
        token['contribution_points'] = profile.contribution_points if profile else 0
        
        # Blockchain-specific data
        token['wallet_address'] = user.wallet_address
        token['is_whale'] = user.is_whale
        token['is_verified'] = user.is_verified
        token['is_kyc_verified'] = user.is_kyc_verified
        token['has_been_kyc_rewarded'] = user.has_been_kyc_rewarded
        
        # KYC status
        try:
            from mainapps.kyc.models import KYCApplication
            kyc_app = KYCApplication.objects.filter(user=user).first()
            token['kyc_status'] = kyc_app.status if kyc_app else 'NOT_SUBMITTED'
            token['kyc_level'] = kyc_app.verification_level if kyc_app else 'NONE'
        except Exception:
            token['kyc_status'] = 'NOT_SUBMITTED'
            token['kyc_level'] = 'NONE'
        return token

    def validate(self, attrs):
        """Validate and return enhanced user data"""
        data = super().validate(attrs)
        user = self.user
        profile = getattr(user, 'profile', None)
        
        # Enhanced user data for frontend
        data.update({
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
            'is_kyc_verified': user.is_kyc_verified,
            'has_been_kyc_rewarded': user.has_been_kyc_rewarded,
            'phone_number': user.phone_number,
            'profile_id': profile.id if profile else None,
            'reputation_score': profile.reputation_score if profile else 0,
            'contribution_points': profile.contribution_points if profile else 0,
            'referral_code': profile.referral_code if profile else None,
        })
        # Add KYC status information
        try:
            from mainapps.kyc.models import KYCApplication
            kyc_app = KYCApplication.objects.filter(user=user).first()
            data.update({
                'kyc_status': kyc_app.status if kyc_app else 'NOT_SUBMITTED',
                'kyc_level': kyc_app.verification_level if kyc_app else 'NONE',
                'kyc_submitted_at': kyc_app.submitted_at if kyc_app else None,
            })
        except Exception:
            data.update({
                'kyc_status': 'NOT_SUBMITTED',
                'kyc_level': 'NONE',
                'kyc_submitted_at': None,
            })
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
             'is_whale', 'is_verified', 'is_kyc_verified',
            'has_been_kyc_rewarded', 'phone_number', 'date_of_birth', 'created_at', 'profile'
        )
        read_only_fields = (
            'id', 'get_full_name', 'is_whale', 
            'is_verified', 'is_kyc_verified', 'has_been_kyc_rewarded', 'created_at'
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
