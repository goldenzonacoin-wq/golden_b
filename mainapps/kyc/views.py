import logging
from uuid import uuid4

import requests
from subapps.emails.send_email import send_html_email
from web3 import Web3
from rest_framework import viewsets, status, permissions, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.pagination import PageNumberPagination
from django.db.models import Count, Avg, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
from rest_framework.views import APIView
from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError
from mainapps.blockchain.uniswap_v4_price import get_live_uniswap_v4_price, UniswapV4PriceError
from .models import KYCApplication, KYCDocument, KYCPayment, KYCReviewNote, ComplianceCheck, KYCSettings
from .serializers import (
    KYCApplicationSerializer, KYCApplicationCreateSerializer,
    KYCDocumentUploadSerializer, KYCApplicationSubmitSerializer,
    KYCDocumentSerializer, KYCReviewNoteSerializer,
    ComplianceCheckSerializer, KYCApplicationReviewSerializer,
    KYCSettingsSerializer, KYCStatsSerializer, KYCPaymentSerializer,
    KYCPaymentInitiateSerializer, KYCPaymentVerifySerializer, DocumentNumberCheckSerializer
)
from mainapps.accounts.models import Address
from mainapps.accounts.serializers import AddressSerializer
from cities_light.models import Country, Region, SubRegion, City


logger = logging.getLogger(__name__)


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class IsAdminOrSuperUser(BasePermission):
    """Allow both staff users and superusers."""

    def has_permission(self, request, view):
        user = request.user
        user = get_user_model().objects.get(id=user.id)
        return bool(
            user
            and user.is_authenticated
            and (user.is_staff or getattr(user, "is_superuser", False))
        )


class KYCApplicationViewSet(viewsets.ModelViewSet):
    """KYC Application management ViewSet"""
    serializer_class = KYCApplicationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        user = self.request.user
        user = get_user_model().objects.get(id=user.id)
        
        if user.is_staff:
            return KYCApplication.objects.all()
        return KYCApplication.objects.filter(user_id=self.request.user.id)
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return KYCApplicationCreateSerializer
        elif self.action in ['update', 'partial_update'] and self.request.user.is_staff:
            return KYCApplicationReviewSerializer
        elif self.action == 'submit':
            return KYCApplicationSubmitSerializer
        elif self.action == 'upload_documents':
            return KYCDocumentUploadSerializer
        
        return KYCApplicationSerializer
    
    def get_permissions(self):
        """Set permissions based on action"""
        if self.action in ['admin_list', 'statistics', 'review',]:
            permission_classes = [IsAdminOrSuperUser]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def perform_create(self, serializer):
        """Set user as the owner of the KYC application"""
        user_id = self.request.user.id
        if KYCApplication.objects.filter(user_id=user_id).exists():
            raise ValidationError({'detail': 'You already have a KYC application.'})
        user = get_user_model().objects.get(id=user_id)
        self._ensure_payment_completed(user)
        serializer.save(user=user)

    def perform_update(self, serializer):
        application = self.get_object()
        request_user = get_user_model().objects.get(id=self.request.user.id)
        if not request_user.is_staff:
            self._ensure_payment_completed(request_user)
        serializer.save()

    def _ensure_payment_completed(self, user):
        latest_payment = (
            KYCPayment.objects.filter(user=user)
            .order_by('-created_at')
            .first()
        )
        if not latest_payment or latest_payment.status != KYCPayment.Status.SUCCESSFUL:
            raise ValidationError(
                {'detail': 'Complete the on-chain KYC payment before continuing your application.'}
            )
      
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """Submit KYC application for review"""
        application = self.get_object()
        self._ensure_payment_completed(application.user)
        
        if application.status != 'draft':
            return Response(
                {'error': 'KYC application cannot be submitted'},
                status=status.HTTP_400_BAD_REQUEST
            )
        # serializer = KYCApplicationSubmitSerializer(data=request.data)
        # serializer.is_valid(raise_exception=True)
        
        # Validate required documents
        if not application.document_front:
            return Response(
                {'error': 'Document front image is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not application.selfie_image:
            return Response(
                {'error': 'Selfie image is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Submit application
        application.status = 'submitted'
        application.submitted_at = timezone.now()
        application.save()
        
        # Log activity
        from accounts.models import UserActivity
        UserActivity.objects.create(
            user=request.user,
            activity_type='kyc_submission',
            description='KYC application submitted',
            ip_address=request.META.get('REMOTE_ADDR', ''),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            metadata={'application_id': application.application_id}
        )
        
        return Response({
            'message': 'KYC application submitted successfully',
            'application': KYCApplicationSerializer(application).data
        })
    
    @action(detail=True, methods=['post'])
    def upload_documents(self, request, pk=None):
        """Upload KYC documents"""
        application = self.get_object()
        self._ensure_payment_completed(application.user)
        
        if application.status not in ['draft', 'submitted']:
            return Response(
                {'error': 'Cannot upload documents for this application'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = KYCDocumentUploadSerializer(application, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response({
            'message': 'Documents uploaded successfully',
            'application': KYCApplicationSerializer(application).data
        })
    
    @action(detail=False, methods=['get'])
    def me(self,request):
        user = request.user
        if not user or not user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            application = user.kyc_application
        except KYCApplication.DoesNotExist:
            return Response({'detail': 'No KYC application found for this user.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = KYCApplicationSerializer(application)
        return Response(serializer.data)
    

    @action(detail=False, methods=['post'], permission_classes=[IsAdminOrSuperUser], url_path="unsubmit-by-email")
    def unsubmit_application_by_email(self, request):
        """
        Move a user's application back to draft using their email instead of application ID.
        """
        email = (request.data.get("email") or "").strip()
        if not email:
            return Response({'detail': 'Email is required to unsubmit an application.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = get_user_model().objects.get(email__iexact=email)
        except get_user_model().DoesNotExist:
            return Response({'detail': 'No user found with that email.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            application = KYCApplication.objects.get(user=user)
        except KYCApplication.DoesNotExist:
            return Response({'detail': 'No KYC application found for that user.'}, status=status.HTTP_404_NOT_FOUND)

        reviewer = self._resolve_request_user() or request.user
        return self._perform_unsubmit(application, reviewer, request.data.get("reason"))

    @action(detail=True, methods=['post', ])
    def update_address(self, request, pk=None):
        """Add or update address for KYC application"""
        application = self.get_object()
        self._ensure_payment_completed(application.user)
        
        if application.status not in ['draft', 'submitted']:
            return Response(
                {'error': 'Cannot update address for this application'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # If application already has an address, update it
        if application.address:
            serializer = AddressSerializer(application.address, data=request.data, partial=True)
        else:
            # Create new address
            serializer = AddressSerializer(data=request.data)
        
        serializer.is_valid(raise_exception=True)
        address = serializer.save()
        
        # Link address to application
        application.address = address
        application.save()
        
        return Response({
            'message': 'Address updated successfully',
            'address': AddressSerializer(address).data,
            'application': KYCApplicationSerializer(application).data
        })

    @action(detail=True, methods=['post'])
    def update_origin_details(self, request, pk=None):
        """Add or update origin details for KYC application"""
        application = self.get_object()
        self._ensure_payment_completed(application.user)

        if application.status not in ['draft', 'submitted']:
            return Response(
                {'error': 'Cannot update origin details for this application'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if application.origin_details:
            serializer = AddressSerializer(application.origin_details, data=request.data, partial=True)
        else:
            serializer = AddressSerializer(data=request.data)

        serializer.is_valid(raise_exception=True)
        address = serializer.save()

        application.origin_details = address
        application.save()

        return Response({
            'message': 'Origin details updated successfully',
            'address': AddressSerializer(address).data,
            'application': KYCApplicationSerializer(application).data
        })

    @action(detail=False, methods=['post'])
    def check_document_number(self, request):
        """Frontend helper: check if a document number is already in use before submitting the form."""
        serializer = DocumentNumberCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data["is_unique"]:
            return Response(
                {
                    "is_unique": True,
                    "message": "Document number looks good and is not in use.",
                    "duplicate_ids": [],
                }
            )

        return Response(
            {
                "is_unique": False,
                "message": "This document number is already linked to another KYC. Please double check or use a different document.",
                "duplicate_ids": data["duplicate_ids"],
            },
            status=status.HTTP_200_OK,
        )
    
    @action(detail=False, methods=['get'])
    def get_countries(self, request):
        """Get list of countries for KYC forms"""
        countries = Country.objects.all().values('id', 'name', 'code2', 'code3')
        return Response(list(countries))
    
    @action(detail=False, methods=['get'])
    def get_regions(self, request):
        """Get regions for a specific country"""
        country_id = request.query_params.get('country_id')
        if not country_id:
            return Response({'error': 'country_id parameter is required'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        regions = Region.objects.filter(country_id=country_id).values('id', 'name', 'name_ascii')
        return Response(list(regions))
    
    @action(detail=False, methods=['get'])
    def get_subregions(self, request):
        """Get subregions for a specific region"""
        region_id = request.query_params.get('region_id')
        if not region_id:
            return Response({'error': 'region_id parameter is required'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        subregions = SubRegion.objects.filter(region_id=region_id).values('id', 'name', 'name_ascii')
        return Response(list(subregions))
    
    @action(detail=False, methods=['get'])
    def get_cities(self, request):
        """Get cities for a specific subregion"""
        subregion_id = request.query_params.get('subregion_id')
        if not subregion_id:
            return Response({'error': 'subregion_id parameter is required'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        cities = City.objects.filter(subregion_id=subregion_id).values('id', 'name', 'name_ascii')
        return Response(list(cities))
    
    @action(detail=False, methods=['get'], permission_classes=[IsAdminOrSuperUser])
    def admin_list(self, request):
        """Admin view to list all KYC applications with filters"""
        queryset = KYCApplication.objects.all()
        
        # Filter by status
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by risk level
        risk_filter = request.query_params.get('risk_level')
        if risk_filter:
            queryset = queryset.filter(risk_level=risk_filter)
        
        # Filter by date range
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        if date_from:
            queryset = queryset.filter(created_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__lte=date_to)
        
        queryset = queryset.order_by('-created_at')
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAdminOrSuperUser])
    def statistics(self, request):
        """Get KYC statistics"""
        # Basic counts
        total_applications = KYCApplication.objects.count()
        pending_applications = KYCApplication.objects.filter(
            status__in=['submitted', 'under_review']
        ).count()
        approved_applications = KYCApplication.objects.filter(status='approved').count()
        rejected_applications = KYCApplication.objects.filter(status='rejected').count()
        flagged_applications = KYCApplication.objects.filter(status='flagged').count()
        
        # Approval rate
        total_reviewed = approved_applications + rejected_applications
        approval_rate = (approved_applications / total_reviewed * 100) if total_reviewed > 0 else 0
        
        # Average review time
        reviewed_apps = KYCApplication.objects.filter(
            reviewed_at__isnull=False,
            submitted_at__isnull=False
        )
        
        avg_review_time = 0
        if reviewed_apps.exists():
            total_hours = sum([
                (app.reviewed_at - app.submitted_at).total_seconds() / 3600
                for app in reviewed_apps
            ])
            avg_review_time = total_hours / reviewed_apps.count()
        
        # Applications by country
        applications_by_country = dict(
            KYCApplication.objects.values('nationality')
            .annotate(count=Count('id'))
            .values_list('nationality', 'count')
        )
        
        # Applications by month (last 12 months)
        applications_by_month_qs = (
            KYCApplication.objects.filter(
                created_at__gte=timezone.now() - timedelta(days=365)
            )
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(count=Count('id'))
            .order_by('month')
        )
        applications_by_month = {
            entry['month'].strftime('%Y-%m'): entry['count']
            for entry in applications_by_month_qs
            if entry['month']
        }
        
        stats = {
            'total_applications': total_applications,
            'pending_applications': pending_applications,
            'approved_applications': approved_applications,
            'rejected_applications': rejected_applications,
            'flagged_applications': flagged_applications,
            'approval_rate': round(approval_rate, 2),
            'average_review_time_hours': round(avg_review_time, 2),
            'applications_by_country': applications_by_country,
            'applications_by_month': applications_by_month,
        }
        
        serializer = KYCStatsSerializer(stats)
        return Response(serializer.data)

    
    def _perform_unsubmit(self, application: KYCApplication, reviewer, reason: str):
        """
        Common unsubmit logic shared across endpoints.
        """
        clean_reason = (reason or "").strip()
        if not clean_reason:
            return Response({'detail': 'Reason is required to unsubmit an application.'}, status=status.HTTP_400_BAD_REQUEST)

        if application.status == KYCApplication.Status.DRAFT:
            return Response({'detail': 'Application is already in draft state.'}, status=status.HTTP_400_BAD_REQUEST)

        application.status = KYCApplication.Status.DRAFT
        application.reviewed_by = None
        application.reviewed_at = None
        application.rejection_reason = clean_reason
        application.review_notes = None
        application.save()

        KYCReviewNote.objects.create(
            kyc_application=application,
            reviewer=reviewer,
            note=f"Unsubmitted for user corrections: {clean_reason}",
            is_internal=False,
        )

        try:
            subject = "KYC requires updates"
            message = f"Your KYC application was sent back for edits. Reason: {clean_reason}"
            send_html_email(
                subject=subject,
                message=message,
                to_email=[application.user.email],
                html_file="kyc/unsubmitted.html",
                extra_context={"reason": clean_reason, "application": application},
            )
        except Exception:
            logger.exception("Failed to send unsubmit notice to %s", application.user.email)

        return Response(
            {
                'message': 'Application moved back to draft for user corrections.',
                'application': KYCApplicationSerializer(application).data,
            }
        )


    def _resolve_request_user(self):
        user = getattr(self.request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return None
        user_id = getattr(user, "id", None)
        if not user_id:
            return user
        try:
            return get_user_model().objects.get(id=user_id)
        except get_user_model().DoesNotExist:
            return user


class KYCDocumentViewSet(viewsets.ModelViewSet):
    """KYC Document management ViewSet"""
    serializer_class = KYCDocumentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        application_pk = self.kwargs.get('application_pk')
        if application_pk:
            try:
                application = KYCApplication.objects.get(
                    pk=application_pk,
                    user=self.request.user
                )
                return application.additional_documents.all()
            except KYCApplication.DoesNotExist:
                return KYCDocument.objects.none()
        return KYCDocument.objects.none()
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        application_pk = self.kwargs.get('application_pk')
        if application_pk:
            try:
                application = KYCApplication.objects.get(
                    pk=application_pk,
                    user=self.request.user
                )
                context['kyc_application'] = application
            except KYCApplication.DoesNotExist:
                pass
        return context


class KYCReviewNoteViewSet(viewsets.ModelViewSet):
    """KYC Review Note management ViewSet"""
    serializer_class = KYCReviewNoteSerializer
    
    def get_permissions(self):
        """Set permissions based on action"""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsAdminOrSuperUser]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def get_queryset(self):
        application_pk = self.kwargs.get('application_pk')
        if application_pk:
            try:
                application = KYCApplication.objects.get(pk=application_pk)
                
                # Users can only see non-internal notes for their own applications
                if self.request.user == application.user:
                    return application.review_notes.filter(is_internal=False)
                
                # Admins can see all notes
                if self.request.user.is_staff:
                    return application.review_notes.all()
                
                return KYCReviewNote.objects.none()
            except KYCApplication.DoesNotExist:
                return KYCReviewNote.objects.none()
        return KYCReviewNote.objects.none()
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        application_pk = self.kwargs.get('application_pk')
        if application_pk:
            try:
                application = KYCApplication.objects.get(pk=application_pk)
                context['kyc_application'] = application
            except KYCApplication.DoesNotExist:
                pass
        return context


class ComplianceCheckViewSet(viewsets.ReadOnlyModelViewSet):
    """Compliance Check ViewSet (read-only)"""
    serializer_class = ComplianceCheckSerializer
    permission_classes = [IsAdminOrSuperUser]
    
    def get_queryset(self):
        application_pk = self.kwargs.get('application_pk')
        if application_pk:
            try:
                application = KYCApplication.objects.get(pk=application_pk)
                return application.compliance_checks.all()
            except KYCApplication.DoesNotExist:
                return ComplianceCheck.objects.none()
        return ComplianceCheck.objects.none()


class KYCSettingsViewSet(viewsets.ModelViewSet):
    """KYC Settings management ViewSet"""
    serializer_class = KYCSettingsSerializer
    permission_classes = [IsAdminOrSuperUser]
    
    def get_queryset(self):
        return KYCSettings.objects.all()
    
    def get_object(self):
        settings, created = KYCSettings.objects.get_or_create()
        return settings


class KYCPaymentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet
):
    """Handle initialization and verification of on-chain KYC payments."""
    serializer_class = KYCPaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return KYCPayment.objects.filter(user=self.request.user).order_by('-created_at')

    def create(self, request, *args, **kwargs):
        try:
            user = get_user_model().objects.get(id=request.user.id)
            existing_payment = self.get_queryset().first()
            if existing_payment and existing_payment.status == KYCPayment.Status.SUCCESSFUL:
                return Response(
                    {
                        'message': 'KYC payment already completed.',
                        'payment': self.get_serializer(existing_payment).data,
                    },
                    status=status.HTTP_200_OK
                )

            init_serializer = KYCPaymentInitiateSerializer(data=request.data)
            init_serializer.is_valid(raise_exception=True)
            wallet_address = init_serializer.validated_data['wallet_address']
            self._sync_user_wallet(user=user, wallet_address=wallet_address)
            config = self._get_payment_configuration()
            amount = config['fee_usd']
            token_price = config['token_price_usd']
            required_token_amount = (amount / token_price).quantize(Decimal('0.000000000000000001'))
            tx_ref = f"kyc-onchain-{user.id}-{uuid4().hex[:10]}"
            init_payload = {
                'swap_url': config['swap_url'],
                'network_name': config['network_name'],
            }

            if existing_payment:
                existing_payment.tx_ref = tx_ref
                existing_payment.amount = amount
                existing_payment.currency = 'USD'
                existing_payment.payer_wallet_address = wallet_address
                existing_payment.collection_wallet_address = config['collection_wallet_address']
                existing_payment.required_token_amount = required_token_amount
                existing_payment.token_price_usd = token_price
                existing_payment.token_symbol = config['token_symbol']
                existing_payment.token_address = config['token_address']
                existing_payment.token_decimals = config['token_decimals']
                existing_payment.chain_id = config['chain_id']
                existing_payment.status = KYCPayment.Status.PENDING
                existing_payment.payment_link = None
                existing_payment.flw_ref = None
                existing_payment.init_payload = init_payload
                existing_payment.last_webhook_payload = {}
                existing_payment.payment_confirmed = False
                existing_payment.payment_rejection_reason = None
                existing_payment.payment_tx_hash = None
                existing_payment.verification_details = {}
                existing_payment.paid_at = None
                existing_payment.verified_at = None
                existing_payment.save()
                payment = existing_payment
            else:
                payment = KYCPayment.objects.create(
                    user=user,
                    tx_ref=tx_ref,
                    amount=amount,
                    currency='USD',
                    payer_wallet_address=wallet_address,
                    collection_wallet_address=config['collection_wallet_address'],
                    required_token_amount=required_token_amount,
                    token_price_usd=token_price,
                    token_symbol=config['token_symbol'],
                    token_address=config['token_address'],
                    token_decimals=config['token_decimals'],
                    chain_id=config['chain_id'],
                    status=KYCPayment.Status.PENDING,
                    init_payload=init_payload,
                )

            return Response(
                {
                    'message': 'KYC payment requirement prepared successfully.',
                    'payment': self.get_serializer(payment).data,
                },
                status=status.HTTP_201_CREATED
            )
        except ValidationError as exc:
            logger.error("KYC payment validation error: %s", exc, exc_info=True)
            return Response(
                {'detail': exc.detail if hasattr(exc, 'detail') else str(exc)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as exc:
            logger.exception("Unexpected error initializing on-chain KYC payment")
            return Response(
                {'detail': 'Unable to prepare the KYC payment right now.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def latest(self, request):
        payment = self.get_queryset().first()
        if not payment:
            return Response(
                {'detail': 'No KYC payments found for this user.'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(self.get_serializer(payment).data)

    @action(detail=False, methods=['post'], url_path='verify-transfer')
    def verify_transfer(self, request):
        serializer = KYCPaymentVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payment = self.get_queryset().first()
        if not payment:
            return Response(
                {'detail': 'No KYC payment session found for this user.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        tx_hash = serializer.validated_data['tx_hash']
        if payment.status == KYCPayment.Status.SUCCESSFUL and payment.payment_tx_hash == tx_hash:
            return Response(
                {
                    'message': 'KYC payment already verified.',
                    'payment': self.get_serializer(payment).data,
                },
                status=status.HTTP_200_OK,
            )

        if KYCPayment.objects.filter(payment_tx_hash__iexact=tx_hash).exclude(pk=payment.pk).exists():
            raise ValidationError({'detail': 'This transaction hash has already been used for another payment.'})

        receipt, tx = self._load_transaction(tx_hash)
        self._validate_transfer_against_payment(payment=payment, tx=tx, receipt=receipt)

        payment.status = KYCPayment.Status.SUCCESSFUL
        payment.payment_confirmed = True
        payment.payment_rejection_reason = None
        payment.payment_tx_hash = tx_hash
        payment.paid_at = timezone.now()
        payment.verified_at = timezone.now()
        payment.verification_details = {
            'block_number': receipt['blockNumber'],
            'transaction_from': tx['from'],
            'transaction_to': tx.get('to'),
            'transaction_index': receipt.get('transactionIndex'),
        }
        payment.save(
            update_fields=[
                'status',
                'payment_confirmed',
                'payment_rejection_reason',
                'payment_tx_hash',
                'paid_at',
                'verified_at',
                'verification_details',
                'updated_at',
            ]
        )

        return Response(
            {
                'message': 'KYC payment verified successfully.',
                'payment': self.get_serializer(payment).data,
            },
            status=status.HTTP_200_OK,
        )

    def _get_payment_configuration(self):
        fee_usd = Decimal(str(getattr(settings, 'KYC_APPLICATION_FEE_AMOUNT', '0')))
        if fee_usd <= 0:
            raise ValidationError('KYC fee amount is not configured.')

        try:
            live_price = get_live_uniswap_v4_price()
            token_price_usd = live_price.token_price_usd
        except UniswapV4PriceError as exc:
            raise ValidationError(f'Live Uniswap price is unavailable: {exc}') from exc
        if token_price_usd <= 0:
            raise ValidationError('The live Uniswap price is invalid.')

        collection_wallet_address = getattr(settings, 'KYC_PAYMENT_COLLECTION_WALLET', None)
        if not collection_wallet_address or not Web3.is_address(collection_wallet_address):
            raise ValidationError('KYC collection wallet is not configured correctly.')

        chain_id = int(getattr(settings, 'KYC_PAYMENT_CHAIN_ID', '137'))
        configured_token_address = getattr(settings, 'KYC_PAYMENT_TOKEN_ADDRESS', None)
        token_address = configured_token_address

        try:
            reward_chain_id = int(getattr(settings, 'KYC_REWARD_CHAIN_ID', '0'))
        except (TypeError, ValueError):
            reward_chain_id = 0

        # Only fall back to the legacy token address when the KYC payment flow is on the
        # same chain as the existing reward/token configuration. This avoids pointing a
        # Polygon mainnet fee flow at an Amoy deployment by mistake.
        if not token_address and chain_id == reward_chain_id:
            token_address = getattr(settings, 'TOKEN_CONTRACT_ADDRESS', None)

        if not token_address or not Web3.is_address(token_address):
            raise ValidationError('KYC payment token address is not configured correctly.')

        return {
            'fee_usd': fee_usd.quantize(Decimal('0.01')),
            'token_price_usd': token_price_usd,
            'collection_wallet_address': Web3.to_checksum_address(collection_wallet_address),
            'token_address': Web3.to_checksum_address(token_address),
            'token_symbol': getattr(settings, 'KYC_PAYMENT_TOKEN_SYMBOL', 'GZC'),
            'token_decimals': int(getattr(settings, 'KYC_PAYMENT_TOKEN_DECIMALS', '18')),
            'chain_id': chain_id,
            'swap_url': self._build_swap_url(token_address),
            'network_name': getattr(settings, 'KYC_PAYMENT_NETWORK_NAME', 'Polygon'),
        }

    def _build_swap_url(self, token_address: str):
        configured_url = getattr(settings, 'KYC_PAYMENT_SWAP_URL', None)
        if configured_url:
            return configured_url.replace('{token_address}', token_address)
        if int(getattr(settings, 'KYC_PAYMENT_CHAIN_ID', '137')) == 137:
            return f"https://app.uniswap.org/swap?chain=polygon&outputCurrency={token_address}"
        return None

    def _sync_user_wallet(self, user, wallet_address: str):
        wallet_address = Web3.to_checksum_address(wallet_address)
        existing_user = (
            get_user_model()
            .objects
            .filter(wallet_address__iexact=wallet_address)
            .exclude(pk=user.pk)
            .exists()
        )
        if existing_user:
            raise ValidationError('Wallet address is already connected to another account.')

        if user.wallet_address != wallet_address:
            user.wallet_address = wallet_address
            user.save(update_fields=['wallet_address'])

    def _get_web3(self):
        rpc_url = getattr(settings, 'KYC_PAYMENT_RPC_URL', None) or getattr(settings, 'ETHEREUM_RPC_URL', None)
        if not rpc_url:
            raise ValidationError('Polygon RPC URL is not configured.')
        provider = Web3.HTTPProvider(rpc_url)
        web3 = Web3(provider)
        if not web3.is_connected():
            raise ValidationError('Unable to connect to the configured blockchain RPC endpoint.')
        return web3

    def _load_transaction(self, tx_hash: str):
        web3 = self._get_web3()
        try:
            receipt = web3.eth.get_transaction_receipt(tx_hash)
        except Exception as exc:  # noqa: BLE001
            raise ValidationError({'detail': 'Transaction receipt is not available yet. Wait for confirmation and try again.'}) from exc
        if not receipt or receipt.get('status') != 1:
            raise ValidationError({'detail': 'The transaction was not successful on-chain.'})

        try:
            tx = web3.eth.get_transaction(tx_hash)
        except Exception as exc:  # noqa: BLE001
            raise ValidationError({'detail': 'Unable to load the transaction from the blockchain.'}) from exc

        return receipt, tx

    def _validate_transfer_against_payment(self, payment, tx, receipt):
        expected_sender = (payment.payer_wallet_address or '').lower()
        tx_sender = (tx.get('from') or '').lower()
        if expected_sender != tx_sender:
            payment.status = KYCPayment.Status.FAILED
            payment.payment_rejection_reason = 'Transaction sender does not match the wallet used for KYC payment.'
            payment.save(update_fields=['status', 'payment_rejection_reason', 'updated_at'])
            raise ValidationError({'detail': payment.payment_rejection_reason})

        transfer_topic = Web3.keccak(text='Transfer(address,address,uint256)').hex().lower()
        expected_token = (payment.token_address or '').lower()
        expected_receiver = (payment.collection_wallet_address or '').lower()
        required_amount_wei = int(
            Decimal(str(payment.required_token_amount)) * (Decimal(10) ** int(payment.token_decimals))
        )

        matched_amount = 0
        for log in receipt['logs']:
            log_address = getattr(log, 'address', None) or log.get('address')
            if not log_address or log_address.lower() != expected_token:
                continue

            topics = getattr(log, 'topics', None) or log.get('topics') or []
            if len(topics) < 3:
                continue
            topic0 = topics[0].hex().lower() if hasattr(topics[0], 'hex') else str(topics[0]).lower()
            if topic0 != transfer_topic:
                continue

            from_address = f"0x{(topics[1].hex() if hasattr(topics[1], 'hex') else str(topics[1]))[-40:]}".lower()
            to_address = f"0x{(topics[2].hex() if hasattr(topics[2], 'hex') else str(topics[2]))[-40:]}".lower()
            if from_address != expected_sender or to_address != expected_receiver:
                continue

            raw_data = getattr(log, 'data', None) or log.get('data')
            if isinstance(raw_data, bytes):
                value = int.from_bytes(raw_data, byteorder='big')
            else:
                value = int(str(raw_data), 16)
            matched_amount += value

        if matched_amount < required_amount_wei:
            payment.status = KYCPayment.Status.FAILED
            payment.payment_rejection_reason = 'The transaction did not transfer enough GZC to the KYC collection wallet.'
            payment.save(update_fields=['status', 'payment_rejection_reason', 'updated_at'])
            raise ValidationError({'detail': payment.payment_rejection_reason})



# class FlutterwaveWebhookView(APIView):
#     """Receives payment events from Flutterwave."""
#     authentication_classes = []
#     permission_classes = [permissions.AllowAny]

#     def post(self, request, *args, **kwargs):
#         expected_signature = (
#             getattr(settings, 'FLUTTERWAVE_WEBHOOK_HASH', None)
#             or getattr(settings, 'FLUTTERWAVE_WEBHHOK_HASH', None)
#         )
#         received_signature = request.headers.get('verif-hash')
#         if expected_signature and received_signature != expected_signature:
#             return Response({'detail': 'Invalid webhook signature.'}, status=status.HTTP_403_FORBIDDEN)

#         payload = request.data
#         event_data = payload.get('data') or {}
#         tx_ref = event_data.get('tx_ref')
#         if not tx_ref:
#             return Response({'detail': 'Missing transaction reference.'}, status=status.HTTP_400_BAD_REQUEST)

#         try:
#             payment = KYCPayment.objects.get(tx_ref=tx_ref)
#         except KYCPayment.DoesNotExist:
#             return Response({'detail': 'Payment not found, ignoring event.'}, status=status.HTTP_200_OK)

#         payment.last_webhook_payload = payload
#         event_status = event_data.get('status')

#         if event_status == 'successful':
#             charged_amount = event_data.get('charged_amount') or event_data.get('amount') or payment.amount
#             try:
#                 charged_amount = Decimal(str(charged_amount))
#             except Exception:
#                 charged_amount = Decimal('0')

#             currency = event_data.get('currency')
#             if charged_amount >= payment.amount and currency == payment.currency:
#                 payment.status = KYCPayment.Status.SUCCESSFUL
#                 payment.paid_at = timezone.now()
#             else:
#                 payment.status = KYCPayment.Status.FAILED
#             payment.flw_ref = event_data.get('flw_ref') or event_data.get('id')
#         elif event_status == 'failed':
#             payment.status = KYCPayment.Status.FAILED
#         elif event_status == 'cancelled':
#             payment.status = KYCPayment.Status.CANCELLED
#         else:
#             payment.status = KYCPayment.Status.PENDING

#         payment.save()
#         return Response({'status': 'received'})
