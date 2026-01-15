import logging
from uuid import uuid4

import requests
from mainapps.kyc.models import KYCPayment
from mainapps.blockchain.models import TokenPurchase
from django.core.management import call_command
from rest_framework import status, permissions
from rest_framework.response import Response
from datetime import timedelta
from django.conf import settings
from rest_framework.views import APIView
from decimal import Decimal
from django.utils import timezone




class FlutterwaveWebhookView(APIView):
    """Receives payment events from Flutterwave."""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        expected_signature = (
            getattr(settings, 'FLUTTERWAVE_WEBHOOK_HASH', None)
            or getattr(settings, 'FLUTTERWAVE_WEBHHOK_HASH', None)
        )
        received_signature = request.headers.get('verif-hash')
        if expected_signature and received_signature != expected_signature:
            return Response({'detail': 'Invalid webhook signature.'}, status=status.HTTP_403_FORBIDDEN)

        payload = request.data
        event_data = payload.get('data') or {}
        tx_ref = event_data.get('tx_ref')
        if not tx_ref:
            return Response({'detail': 'Missing transaction reference.'}, status=status.HTTP_400_BAD_REQUEST)

        payment = None
        payment_type = None

        try:
            payment = KYCPayment.objects.get(tx_ref=tx_ref)
            payment_type = 'kyc'
        except KYCPayment.DoesNotExist:
            try:
                payment = TokenPurchase.objects.get(tx_ref=tx_ref)
                payment_type = 'token_purchase'
            except TokenPurchase.DoesNotExist:
                return Response({'detail': 'Payment not found, ignoring event.'}, status=status.HTTP_200_OK)

        payment.last_webhook_payload = payload
        event_status = event_data.get('status')

        if payment_type == 'kyc':
            if event_status == 'successful':
                charged_amount = event_data.get('charged_amount') or event_data.get('amount') or payment.amount
                try:
                    charged_amount = Decimal(str(charged_amount))
                except Exception:
                    charged_amount = Decimal('0')

                currency = event_data.get('currency')
                if charged_amount >= payment.amount and currency == payment.currency:
                    payment.status = KYCPayment.Status.SUCCESSFUL
                    payment.paid_at = timezone.now()
                else:
                    payment.status = KYCPayment.Status.FAILED
                payment.flw_ref = event_data.get('flw_ref') or event_data.get('id')
            elif event_status == 'failed':
                payment.status = KYCPayment.Status.FAILED
            elif event_status == 'cancelled':
                payment.status = KYCPayment.Status.CANCELLED
            else:
                payment.status = KYCPayment.Status.PENDING

            payment.save()
            return Response({'status': 'received'})

        if event_status == 'successful':
            charged_amount = event_data.get('charged_amount') or event_data.get('amount') or payment.charge_amount
            try:
                charged_amount = Decimal(str(charged_amount))
            except Exception:
                charged_amount = Decimal('0')

            currency = (event_data.get('currency') or '').upper()
            if charged_amount >= payment.charge_amount and currency == (payment.currency or '').upper():
                payment.status = TokenPurchase.Status.SUCCESSFUL
                payment.paid_at = timezone.now()
            else:
                payment.status = TokenPurchase.Status.FAILED
            payment.flw_ref = event_data.get('flw_ref') or event_data.get('id')
        elif event_status == 'failed':
            payment.status = TokenPurchase.Status.FAILED
        elif event_status == 'cancelled':
            payment.status = TokenPurchase.Status.CANCELLED
        else:
            payment.status = TokenPurchase.Status.PENDING

        payment.save()

        if payment.status == TokenPurchase.Status.SUCCESSFUL and payment.transfer_status != TokenPurchase.TransferStatus.SUCCESSFUL:
            if not payment.wallet_address:
                payment.transfer_status = TokenPurchase.TransferStatus.FAILED
                payment.transfer_error = "Missing wallet address for token transfer."
                payment.save(update_fields=['transfer_status', 'transfer_error', 'updated_at'])
                return Response({'status': 'received'})

            try:
                payment.transfer_status = TokenPurchase.TransferStatus.PROCESSING
                payment.save(update_fields=['transfer_status', 'updated_at'])

                call_command(
                    'send_direct_transfer',
                    recipient=payment.wallet_address,
                    amount=float(payment.token_amount),
                    purpose='token_purchase',
                )
                payment.transfer_status = TokenPurchase.TransferStatus.SUCCESSFUL
                payment.transfer_tx_hash = None
                payment.transfer_error = None
            except Exception as exc:
                payment.transfer_status = TokenPurchase.TransferStatus.FAILED
                payment.transfer_error = str(exc)

            payment.save(update_fields=['transfer_status', 'transfer_tx_hash', 'transfer_error', 'updated_at'])

        return Response({'status': 'received'})
