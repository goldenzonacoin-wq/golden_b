import logging
from uuid import uuid4

import requests
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
from .models import KYCApplication, KYCDocument, KYCPayment, KYCReviewNote, ComplianceCheck, KYCSettings
from .serializers import (
    KYCApplicationSerializer, KYCApplicationCreateSerializer,
    KYCDocumentUploadSerializer, KYCApplicationSubmitSerializer,
    KYCDocumentSerializer, KYCReviewNoteSerializer,
    ComplianceCheckSerializer, KYCApplicationReviewSerializer,
    KYCSettingsSerializer, KYCStatsSerializer, KYCPaymentSerializer,
    KYCPaymentInitiateSerializer, DocumentNumberCheckSerializer
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
            raise 
        user = get_user_model().objects.get(id=user_id)
        serializer.save(user=user)
      
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """Submit KYC application for review"""
        application = self.get_object()
        
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
    
    @action(detail=True, methods=['post', ])
    def update_address(self, request, pk=None):
        """Add or update address for KYC application"""
        application = self.get_object()
        
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
    """Handle initialization and retrieval of KYC payment attempts."""
    serializer_class = KYCPaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return KYCPayment.objects.filter(user=self.request.user).order_by('-created_at')

    def create(self, request, *args, **kwargs):
        try:
            user = request.user
            user = get_user_model().objects.get(id=user.id)


            existing_payment = KYCPayment.objects.filter(user=user).order_by('-created_at').first()
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
            redirect_url = init_serializer.validated_data.get('redirect_url') or getattr(settings, 'FLUTTERWAVE_REDIRECT_URL', None)
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

            amount, currency = self._determine_charge_amount(requested_currency)
            if amount <= 0:
                return Response(
                    {'detail': 'Invalid KYC payment amount configured.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            tx_ref = f"kyc-{user.id}-{uuid4().hex[:10]}"

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
                    "kyc_payment": True,
                },
                "customizations": {
                    "title": getattr(settings, 'SITE_NAME', 'KYC Verification Fee'),
                    "description": getattr(settings, 'KYC_APPLICATION_FEE_DESCRIPTION', 'KYC verification payment'),
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
                logger.exception("Failed to initialize Flutterwave payment")
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

            if existing_payment:
                existing_payment.tx_ref = tx_ref
                existing_payment.flw_ref = flw_ref
                existing_payment.amount = amount
                existing_payment.currency = currency
                existing_payment.status = KYCPayment.Status.PENDING
                existing_payment.payment_link = payment_link
                existing_payment.init_payload = {"request": payload, "response": response_data}
                existing_payment.save()
                payment = existing_payment
            else:
                payment = KYCPayment.objects.create(
                    user=user,
                    tx_ref=tx_ref,
                    flw_ref=flw_ref,
                    amount=amount,
                    currency=currency,
                    status=KYCPayment.Status.PENDING,
                    payment_link=payment_link,
                    init_payload={"request": payload, "response": response_data},
                )

            return Response(
                {
                    'message': 'KYC payment initialized successfully.',
                    'payment': self.get_serializer(payment).data,
                    'flutterwave_payload': payload,
                },
                status=status.HTTP_201_CREATED
            )
        except ValidationError as exc:
            logger.error("KYC payment validation error: %s", exc, exc_info=True)
            print(f"[KYCPaymentViewSet.create] Validation error: {exc}")
            return Response(
                {'detail': exc.detail if hasattr(exc, 'detail') else str(exc)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as exc:
            logger.exception("Unexpected error initializing KYC payment")
            print(f"[KYCPaymentViewSet.create] Unexpected error: {exc}")
            return Response(
                {'detail': 'Unable to initialize payment at the moment.'},
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

    def _determine_charge_amount(self, requested_currency: str):
        """Return tuple of (amount_decimal, currency_code)."""
        base_currency = (getattr(settings, 'KYC_APPLICATION_FEE_CURRENCY', 'USD') or 'USD').upper()
        base_amount = getattr(settings, 'KYC_APPLICATION_FEE_AMOUNT', Decimal('0'))
        try:
            base_amount = Decimal(str(base_amount))
        except Exception:
            base_amount = Decimal('0')

        target_currency = (requested_currency or base_currency).upper()

        if target_currency == base_currency:
            return base_amount, base_currency

        converted_amount = self._convert_currency(
            amount=base_amount,
            from_currency=base_currency,
            to_currency=target_currency
        )
        return converted_amount, target_currency

    def _convert_currency(self, amount: Decimal, from_currency: str, to_currency: str) -> Decimal:
        """Convert amount using external FX providers (not Flutterwave)."""
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
