from django.contrib import admin
from django.urls import path,include
from django.urls import re_path
from mainapps.kyc.views import FlutterwaveWebhookView
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from django.views.decorators.csrf import csrf_exempt
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from schema_graph.views import Schema

schema_view = get_schema_view(
   openapi.Info(
      title="Quick Campaign API",
      default_version='v1',
      description="Test description",
      terms_of_service="https://www.google.com/policies/terms/",
      contact=openapi.Contact(email="contact@snippets.local"),
      license=openapi.License(name="BSD License"),
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path('admin/', admin.site.urls),
    # djoser urls
    path('auth-api/', include('djoser.urls')),
    path('', include('djoser.urls.jwt')),

    #  api endpoints docs
    path('swagger<format>/', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path("schema/", Schema.as_view()),

    path('api/v1/accounts/', include('mainapps.accounts.urls')),
    path('blockchain_api/', include('mainapps.blockchain.urls')),
    path('kyc_api/', include('mainapps.kyc.urls')),
    path('wallet_api/', include('mainapps.wallet.urls')),
    path('smart_contract_api/', include('mainapps.smart_contract.urls')),
    path('flutter-webhook/',FlutterwaveWebhookView.as_view(), name='flutterwave-webhook'),

]
