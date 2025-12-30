from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.pagination import PageNumberPagination
from django.db.models import Count, Avg, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from .models import KYCApplication, KYCDocument, KYCReviewNote, ComplianceCheck, KYCSettings
from .serializers import (
    KYCApplicationSerializer, KYCApplicationCreateSerializer,
    KYCDocumentUploadSerializer, KYCApplicationSubmitSerializer,
    KYCDocumentSerializer, KYCReviewNoteSerializer,
    ComplianceCheckSerializer, KYCApplicationReviewSerializer,
    KYCSettingsSerializer, KYCStatsSerializer
)
from mainapps.accounts.models import Address
from mainapps.accounts.serializers import AddressSerializer
from cities_light.models import Country, Region, SubRegion, City


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class IsAdminOrSuperUser(BasePermission):
    """Allow both staff users and superusers."""

    def has_permission(self, request, view):
        user = request.user
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
        if self.request.user.is_staff:
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
