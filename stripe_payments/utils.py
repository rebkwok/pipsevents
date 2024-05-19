import logging
from django.conf import settings
from django.contrib.sites.models import Site
from django.urls import reverse
import stripe

from activitylog.models import ActivityLog
from .emails import send_processed_payment_emails, send_gift_voucher_email
from .exceptions import StripeProcessingError
from .models import Invoice, Seller


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


def process_invoice_items(invoice, payment_method, request=None):
    for booking in invoice.bookings.all():
        booking.paid = True
        booking.payment_confirmed = True
        booking.process_voucher()
        booking.save()

    for ticket_booking in invoice.ticket_bookings.all():
        ticket_booking.paid = True
        ticket_booking.save()

    for block in invoice.blocks.all():
        block.paid = True
        block.process_voucher()
        block.save()

    for gift_voucher in invoice.gift_vouchers:
        gift_voucher.activated = True
        gift_voucher.save()

    invoice.paid = True
    invoice.save()

    # SEND EMAILS
    send_processed_payment_emails(invoice)
    for gift_voucher in invoice.gift_vouchers:
        send_gift_voucher_email(gift_voucher)
    ActivityLog.objects.create(
        log=f"Invoice {invoice.invoice_id} (user {invoice.username}) paid by {payment_method}"
    )


def get_connected_account_id(request=None):
    stripe.api_key = settings.STRIPE_SECRET_KEY
    seller = Seller.objects.filter(site=Site.objects.get_current(request=request)).first()
    return seller.stripe_user_id


def create_stripe_product(product_id, name, description, price, connected_account_id=None):
    connected_account_id = connected_account_id or get_connected_account_id()
    price_in_p = int(price * 100)
    product = stripe.Product.create(
        stripe_account=connected_account_id,
        id=product_id,
        name=name,
        description=description,
        default_price_data={
            "unit_amount": price_in_p,
            "currency": "gbp",
            "recurring": {"interval": "month"},
        },
    )
    return product


def update_stripe_product(product_id, name, description, active, price_id, connected_account_id=None):
    connected_account_id = connected_account_id or get_connected_account_id()
    product = stripe.Product.modify(
        product_id,
        stripe_account=connected_account_id,
        name=name,
        description=description,
        active=active,
        default_price=price_id,
    )
    return product


def get_or_create_stripe_price(product_id, price, connected_account_id=None):
    connected_account_id = connected_account_id or get_connected_account_id()
    price_in_p = int(price * 100)
    
    # get existing active Price for this product and amount if one exists
    matching_prices = stripe.Price.list(
        product=product_id, 
        stripe_account=connected_account_id, 
        unit_amount=price_in_p, 
        active=True,
        recurring={"interval": "month"}
    )
    if matching_prices.data:
        return matching_prices.data[0].id

    new_price = stripe.Price.create(
        product=product_id,
        stripe_account=connected_account_id,
        currency="gbp",
        unit_amount=price_in_p,
        recurring={"interval": "month"},
    )
    return new_price.id


def get_or_create_stripe_customer(user, connected_account_id=None, **kwargs):
    if user.user_profile.stripe_customer_id:
        return user.user_profile.stripe_customer_id
    
    connected_account_id = connected_account_id or get_connected_account_id()
    try:
        customer = stripe.Customer.create(
            name=f"{user.first_name} {user.last_name}",
            email=f"{user.email}",
            **kwargs
        )
    except Exception as e:
        import ipdb; ipdb.set_trace()
        ...
    return customer

