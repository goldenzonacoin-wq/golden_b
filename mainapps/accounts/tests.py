import pyotp
from rest_framework import status
from rest_framework.test import APITestCase

from .models import User


class MfaAuthFlowTests(APITestCase):
    def setUp(self):
        self.password = "StrongPassword123!"
        self.user = User.objects.create_user(
            email="mfa@example.com",
            password=self.password,
            first_name="Golden",
            last_name="Zona",
        )

    def test_login_returns_pending_mfa_state(self):
        response = self.client.post(
            "/auth/login/",
            {"email": self.user.email, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["mfa_verified"])
        self.assertFalse(response.data["mfa_enabled"])
        self.assertFalse(response.data["has_setup_mfa"])

    def test_unverified_mfa_token_cannot_access_protected_endpoint(self):
        login_response = self.client.post(
            "/auth/login/",
            {"email": self.user.email, "password": self.password},
            format="json",
        )

        access = login_response.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        response = self.client.get("/api/v1/accounts/users/me/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["detail"], "MFA verification required.")

    def test_mfa_setup_and_verify_unlocks_protected_endpoint(self):
        login_response = self.client.post(
            "/auth/login/",
            {"email": self.user.email, "password": self.password},
            format="json",
        )
        access = login_response.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        setup_response = self.client.post("/api/v1/accounts/mfa/setup/", {}, format="json")
        self.assertEqual(setup_response.status_code, status.HTTP_200_OK)
        self.assertIn("mfa_secret", setup_response.data)

        totp = pyotp.TOTP(setup_response.data["mfa_secret"])
        verify_response = self.client.post(
            "/api/v1/accounts/mfa/verify/",
            {"code": totp.now()},
            format="json",
        )
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.assertTrue(verify_response.data["mfa_verified"])
        self.assertTrue(verify_response.data["mfa_enabled"])

        verified_access = verify_response.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {verified_access}")
        me_response = self.client.get("/api/v1/accounts/users/me/")

        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        self.assertTrue(me_response.data["mfa_enabled"])
        self.assertTrue(me_response.data["has_setup_mfa"])
