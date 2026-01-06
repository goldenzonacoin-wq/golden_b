from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'applications', views.KYCApplicationViewSet, basename='kycapplication')
router.register(r'settings', views.KYCSettingsViewSet, basename='kycsettings')
router.register(r'payments', views.KYCPaymentViewSet, basename='kycpayment')

router.register(r'documents', views.KYCDocumentViewSet, basename='application-documents')
router.register(r'review-notes', views.KYCReviewNoteViewSet, basename='application-reviewnotes')
router.register(r'compliance-checks', views.ComplianceCheckViewSet, basename='application-compliancechecks')

urlpatterns = [
    path('', include(router.urls)),
]
