import logging
from django.conf import settings
from django.contrib.sites.models import Site
from django.urls import reverse
import stripe

from activitylog.models import ActivityLog
from booking.email_helpers import send_gift_voucher_email
from .emails import send_processed_payment_emails, send_invalid_request_email
from .exceptions import StripeProcessingError
from .models import Invoice, StripeRefund, StripePaymentIntent, Seller


logger = logging.getLogger(__name__)


def get_invoice_from_payment_intent(payment_intent, raise_immediately=False):
    # Don't raise the exception here so we don't expose it to the user; leave it for the webhook
    invoice_id = payment_intent.metadata.get("invoice_id")
    if not invoice_id:
        if raise_immediately:
            raise StripeProcessingError(f"Error processing stripe payment intent {payment_intent.id}; no invoice id")
        return None
    try:
        invoice = Invoice.objects.get(invoice_id=invoice_id)
        if not invoice.username:
            # if there's no username on the invoice, it's from a guest checkout
            # Add the username from the billing email
            billing_email = payment_intent.charges.data[0]["billing_details"]["email"]
            invoice.username = billing_email
            invoice.save()
        return invoice
    except Invoice.DoesNotExist:
        logger.error("Error processing stripe payment intent %s; could not find invoice", payment_intent.id)
        if raise_immediately:
            raise StripeProcessingError(f"Error processing stripe payment intent {payment_intent.id}; could not find invoice")
        return None


def check_stripe_data(payment_intent, invoice):
    signature = payment_intent.metadata.get("invoice_signature")
    if signature != invoice.signature():
        raise StripeProcessingError(
            f"Could not verify invoice signature: payment intent {payment_intent.id}; invoice id {invoice.invoice_id}")

    if payment_intent.amount != int(invoice.amount * 100):
        raise StripeProcessingError(
            f"Invoice amount is not correct: payment intent {payment_intent.id} ({payment_intent.amount/100}); "
            f"invoice id {invoice.invoice_id} ({invoice.amount})"
        )


# def process_invoice_items(invoice, payment_method, transaction_id=None, request=None):
#     for booking in invoice.bookings.all():
#         booking.paid = True
#         booking.save()
#     for membership in invoice.memberships.all():
#         membership.paid = True
#         membership.save()
#     for gift_voucher in invoice.gift_vouchers.all():
#         gift_voucher.paid = True
#         gift_voucher.save()
#         gift_voucher.activate()

#     invoice.paid = True
#     invoice.save()
#     # SEND EMAILS
#     send_processed_payment_emails(invoice)
#     for gift_voucher in invoice.gift_vouchers.all():
#         send_gift_voucher_email(gift_voucher, request=request)
#     ActivityLog.objects.create(
#         log=f"Invoice {invoice.invoice_id} (user {invoice.username}) paid by {payment_method}"
#     )


# def process_refund(request, booking):
#     # process refund
#     refunded = False
#     try:
#         try:
#             payment_intent = StripePaymentIntent.objects.get(
#                 payment_intent_id=booking.invoice.stripe_payment_intent_id
#             )
#         except StripePaymentIntent.DoesNotExist:
#             # send warning email to tech support
#             send_invalid_request_email(
#                 request, booking, "Payment intent not found"
#             )
#         else:
#             stripe.api_key = settings.STRIPE_SECRET_KEY
#             seller = Seller.objects.filter(site=Site.objects.get_current(request)).first()
            
#             # get the amount to refund from the metadata (in) pence)
#             amount = payment_intent.metadata.get(f"booking_{booking.id}_cost_in_p")
#             if amount is None:
#                 # send warning email to tech support
#                 send_invalid_request_email(
#                     request, booking, "Amount could not be parsed from PI metadata"
#                 )
#             else:
#                 try:
#                     refund = stripe.Refund.create(
#                         amount=int(amount),
#                         metadata={"booking_id": booking.id, "cancelled_by": request.user.email},
#                         payment_intent=payment_intent.payment_intent_id,
#                         reason="requested_by_customer",
#                         stripe_account=seller.stripe_user_id,
#                     )
#                     StripeRefund.create_from_refund_obj(refund, payment_intent, booking.id)
#                     refunded = True
#                     ActivityLog.objects.create(
#                         log=f"Refund for booking {booking.id} (user {booking.user.username}) processed"
#                     )
#                 except stripe.error.InvalidRequestError as error:
#                     # send warning email to tech support
#                     send_invalid_request_email(request, booking, str(error))
#     except Exception as error:
#         # catch anything else
#         send_invalid_request_email(request, booking, str(error))

#     return refunded
