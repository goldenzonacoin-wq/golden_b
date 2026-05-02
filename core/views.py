import logging
from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail
from django.core.management import call_command
from django.utils import timezone
from mainapps.blockchain.models import TokenPurchase
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView


class ContactMessageSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    email = serializers.EmailField()
    message = serializers.CharField(max_length=5000)


class ContactMessageView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = ContactMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        first_name = serializer.validated_data["first_name"].strip()
        last_name = serializer.validated_data.get("last_name", "").strip()
        email = serializer.validated_data["email"].strip()
        message = serializer.validated_data["message"].strip()
        full_name = " ".join(part for part in [first_name, last_name] if part).strip()

        subject = f"GoldenZona contact form message from {full_name or email}"
        body = (
            "A new message was submitted from the GoldenZona contact form.\n\n"
            f"Name: {full_name or 'Not provided'}\n"
            f"Email: {email}\n\n"
            "Message:\n"
            f"{message}\n"
        )

        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.SUPPORT_CONTACT_EMAIL],
                fail_silently=False,
                reply_to=[email],
            )
        except Exception:
            logging.exception("Failed to send GoldenZona contact form email")
            return Response(
                {"detail": "We could not send your message right now. Please try again shortly."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {"detail": "Your message has been sent successfully."},
            status=status.HTTP_200_OK,
        )


class FlutterwaveWebhookView(APIView):
    """Receives payment events from Flutterwave."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        expected_signature = (
            getattr(settings, "FLUTTERWAVE_WEBHOOK_HASH", None)
            or getattr(settings, "FLUTTERWAVE_WEBHHOK_HASH", None)
        )
        received_signature = request.headers.get("verif-hash")
        if expected_signature and received_signature != expected_signature:
            return Response({"detail": "Invalid webhook signature."}, status=status.HTTP_403_FORBIDDEN)

        payload = request.data
        event_data = payload.get("data") or {}
        tx_ref = event_data.get("tx_ref")
        if not tx_ref:
            return Response({"detail": "Missing transaction reference."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payment = TokenPurchase.objects.get(tx_ref=tx_ref)
        except TokenPurchase.DoesNotExist:
            return Response({"detail": "Payment not found, ignoring event."}, status=status.HTTP_200_OK)

        payment.last_webhook_payload = payload
        event_status = event_data.get("status")

        if event_status == "successful":
            charged_amount = event_data.get("charged_amount") or event_data.get("amount") or payment.charge_amount
            try:
                charged_amount = Decimal(str(charged_amount))
            except Exception:
                charged_amount = Decimal("0")

            currency = (event_data.get("currency") or "").upper()
            if charged_amount >= payment.charge_amount and currency == (payment.currency or "").upper():
                payment.status = TokenPurchase.Status.SUCCESSFUL
                payment.paid_at = timezone.now()
            else:
                payment.status = TokenPurchase.Status.FAILED
            payment.flw_ref = event_data.get("flw_ref") or event_data.get("id")
        elif event_status == "failed":
            payment.status = TokenPurchase.Status.FAILED
        elif event_status == "cancelled":
            payment.status = TokenPurchase.Status.CANCELLED
        else:
            payment.status = TokenPurchase.Status.PENDING

        payment.save()

        if (
            payment.status == TokenPurchase.Status.SUCCESSFUL
            and payment.transfer_status != TokenPurchase.TransferStatus.SUCCESSFUL
        ):
            if not payment.wallet_address:
                payment.transfer_status = TokenPurchase.TransferStatus.FAILED
                payment.transfer_error = "Missing wallet address for token transfer."
                payment.save(update_fields=["transfer_status", "transfer_error", "updated_at"])
                return Response({"status": "received"})

            try:
                payment.transfer_status = TokenPurchase.TransferStatus.PROCESSING
                payment.save(update_fields=["transfer_status", "updated_at"])

                call_command(
                    "send_direct_transfer",
                    recipient=payment.wallet_address,
                    amount=float(payment.token_amount),
                    purpose="token_purchase",
                )
                payment.transfer_status = TokenPurchase.TransferStatus.SUCCESSFUL
                payment.transfer_tx_hash = None
                payment.transfer_error = None
            except Exception as exc:
                payment.transfer_status = TokenPurchase.TransferStatus.FAILED
                payment.transfer_error = str(exc)

            payment.save(
                update_fields=["transfer_status", "transfer_tx_hash", "transfer_error", "updated_at"]
            )

        return Response({"status": "received"})
