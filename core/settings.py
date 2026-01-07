
import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


SECRET_KEY = os.getenv('SECRET_KEY' )

DEBUG=os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '').split(',')

DJ_DEFAULT_INSTALLED_APPS=[
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS=[
    'django_extensions',
     "rest_framework",
    "rest_framework.authtoken",
    'corsheaders',
    'whitenoise.runserver_nostatic',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'oauth2_provider',
    'drf_yasg',
    'djoser',
    'social_django',
    'cities_light',
]

CORE_APPS = [
    'mainapps.accounts',
    'mainapps.blockchain',
    'mainapps.kyc',
    'mainapps.wallet',
    'mainapps.smart_contract',
]

INSTALLED_APPS =DJ_DEFAULT_INSTALLED_APPS+THIRD_PARTY_APPS+CORE_APPS

ATC_TOKEN_CONTRACT_ADDRESS=os.getenv('ATC_TOKEN_CONTRACT_ADDRESS')
ETHEREUM_RPC_URL=os.getenv('ETHEREUM_RPC_URL')

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'corsheaders.middleware.CorsMiddleware',
]


ROOT_URLCONF = 'core.urls'
AUTH_USER_MODEL = 'accounts.User' 
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR/"templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

"""

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST'),
        'PORT': os.getenv('DB_PORT'),
    }
}
"""


DATABASES = {
    'default': dj_database_url.config(
        default=os.getenv('DATABASE_URL'),
    )
}
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

# S3 Configuration
AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME')
AWS_S3_REGION_NAME = os.getenv('AWS_S3_REGION_NAME')
AWS_S3_CUSTOM_DOMAIN = "%s.s3.amazonaws.com" % AWS_STORAGE_BUCKET_NAME
AWS_S3_CONNECT_TIMEOUT = 10  
AWS_S3_TIMEOUT = 60 
AWS_S3_FILE_OVERWRITE = True




STORAGES = {
        "default": {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"},
        "staticfiles": {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"},
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

STATIC_URL = '/static/'

STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')  

STATICFILES_DIRS=[os.path.join(BASE_DIR,'static')]

MEDIA_URL = '/media/'
MEDIAFILES_DIRS=[os.path.join(BASE_DIR,'media')]
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
EMAIL_BACKEND = 'django_smtp_ssl.SSLEmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST')
EMAIL_PORT = os.getenv('EMAIL_PORT')  
EMAIL_USE_TLS = False
EMAIL_USE_SSL = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD =os.getenv('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL =f"Goldenzona <{EMAIL_HOST_USER}>"

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

    




SITE_URL=os.getenv('SITE_URL')
SITE_NAME=os.getenv('SITE_NAME')
FRONTEND_DOMAIN=os.getenv('FRONTEND_DOMAIN')
FLUTTERWAVE_SECRET_KEY = os.getenv('FLUTTERWAVE_SECRET_KEY')
FLUTTERWAVE_PUBLIC_KEY = os.getenv('FLUTTERWAVE_PUBLIC_KEY')
FLUTTERWAVE_PUB_KEY = os.getenv('FLUTTERWAVE_PUB_KEY') or FLUTTERWAVE_PUBLIC_KEY
FLUTTERWAVE_WEBHOOK_HASH = os.getenv('FLUTTERWAVE_WEBHOOK_HASH') or os.getenv('FLUTTERWAVE_WEBHHOK_HASH')
FLUTTERWAVE_BASE_URL = os.getenv('FLUTTERWAVE_BASE_URL', 'https://api.flutterwave.com/v3')
FLUTTERWAVE_REDIRECT_URL = os.getenv('FLUTTERWAVE_REDIRECT_URL') or (
    f"{FRONTEND_DOMAIN.rstrip('/')}/kyc/payment/callback" if FRONTEND_DOMAIN else None
)
EXCHANGERATE_API_KEY = os.getenv('EXCHANGERATE_API_KEY')
FIXER_API_KEY = os.getenv('FIXER_API_KEY')
KYC_APPLICATION_FEE_AMOUNT = os.getenv('KYC_APPLICATION_FEE_AMOUNT', '10.00')
KYC_APPLICATION_FEE_CURRENCY = os.getenv('KYC_APPLICATION_FEE_CURRENCY', 'USD')
KYC_APPLICATION_FEE_DESCRIPTION = os.getenv('KYC_APPLICATION_FEE_DESCRIPTION', 'KYC verification payment')


AUTHENTICATION_BACKENDS = [
    'social_core.backends.google.GoogleOAuth2',
    'social_core.backends.facebook.FacebookOAuth2',
    "djoser.auth_backends.LoginFieldBackend",

    'django.contrib.auth.backends.ModelBackend',
]
import os
from datetime import timedelta

# DJOSER CONFIGURATION
DJOSER = {
        'SERIALIZERS': {
        'user': 'mainapps.accounts.serializers.UserCreateSerializer',
        },
    'PASSWORD_RESET_CONFIRM_URL': 'accounts/password_reset/{uid}/{token}',
    'USERNAME_RESET_CONFIRM_URL': 'username/reset/confirm/{uid}/{token}',
    'ACTIVATION_URL': 'activate/{uid}/{token}',
    'SEND_ACTIVATION_EMAIL': True,
    'USER_CREATE_PASSWORD_RETYPE': True,
    'PASSWORD_RESET_CONFIRM_RETYPE': True,
    'LOGOUT_ON_PASSWORD_CHANGE': True,
    'EMAIL_FRONTEND_DOMAIN':FRONTEND_DOMAIN,
    'EMAIL_FRONTEND_PROTOCOL':'https',
    'TOKEN_MODEL': 'rest_framework.authtoken.models.Token',  

    'SOCIAL_AUTH_ALLOWED_REDIRECT_URIS': os.getenv('SOCIAL_AUTH_ALLOWED_REDIRECT_URIS', '').split(','),
}
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=2),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=6),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'JWK_URL': None,
    'LEEWAY': 0,
    "TOKEN_OBTAIN_SERIALIZER": "mainapps.accounts.serializers.MyTokenObtainPairSerializer",

    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',

    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',

    'JTI_CLAIM': 'jti',

    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=5),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=1),
}


AUTH_COOKIE='access'
AUTH_COOKIE_ACCESS_MAX_AGE=60*10
AUTH_COOKIE_REFRESH_MAX_AGE=60*60*24
AUTH_COOKIE_SECURE=False 
AUTH_COOKIE_HTTP_ONLY=True
AUTH_COOKIE_PATH='/'
AUTH_COOKIE_SAMESITE='None'
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    )
}

CORS_ALLOW_ALL_ORIGINS=True
CORS_ORIGIN_ALLOW_ALL=True

CORS_ALLOW_CREDENTIALS=True
CORS_ALLOW_METHODS = (
    "DELETE",
    "GET",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
)
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'x-csrftoken',
    'x-requested-with',
]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    os.getenv('SITE_URL').rstrip('/'),
]


SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True

CSRF_COOKIE_SECURE = True
FILE_UPLOAD_TIMEOUT = 3600
DATA_UPLOAD_MAX_MEMORY_SIZE = 2147483648  # 2GB
FILE_UPLOAD_MAX_MEMORY_SIZE = 2147483648  # 2GB


USE_L10N = True
USE_THOUSAND_SEPARATOR = True

CITIES_LIGHT_TRANSLATION_LANGUAGES = [ 'en']
