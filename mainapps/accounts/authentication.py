from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


class AccountJWTAuthentication(JWTAuthentication):
    MFA_EXEMPT_PATH_PREFIXES = (
        "/auth/login/",
        "/auth/refresh/",
        "/auth/verify/",
        "/auth/logout/",
        "/api/v1/accounts/mfa/setup/",
        "/api/v1/accounts/mfa/verify/",
        "/api/v1/accounts/mfa/toggle/",
        "/api/v1/accounts/verify/",
    )

    def _is_mfa_exempt_path(self, request):
        path = getattr(request, "path", "") or ""
        return any(path.startswith(prefix) for prefix in self.MFA_EXEMPT_PATH_PREFIXES)

    def authenticate(self, request):
        try:
            header = self.get_header(request)
            if header is None:
                raw_token = request.COOKIES.get(settings.AUTH_COOKIE)
            else:
                raw_token = self.get_raw_token(header)

            if raw_token is None:
                return None

            validated_token = self.get_validated_token(raw_token)
            user = self.get_user(validated_token)

            if user.requires_mfa and not self._is_mfa_exempt_path(request):
                if not bool(validated_token.get("mfa_verified", False)):
                    raise AuthenticationFailed("MFA verification required.")

            return user, validated_token
        except (InvalidToken, TokenError, AttributeError, TypeError, ValueError):
            return None
