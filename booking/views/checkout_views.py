# -*- coding: utf-8 -*-
from decimal import Decimal
import logging

from django.conf import settings
from django.contrib.sites.models import Site
from django.contrib import messages
from django.template.response import TemplateResponse
from django.shortcuts import get_object_or_404, render, HttpResponseRedirect
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone

import stripe

from stripe_payments.models import Invoice, Seller, StripePaymentIntent


logger = logging.getLogger(__name__)


def get_unpaid_blocks_for_checkout(user):
    return [
        block for block in 
        user.blocks.filter(paid=False, paypal_pending=False, expiry_date__gte=timezone.now()) 
        if not block.full
    ]


def items_with_voucher_total(unpaid_items):
    return sum(item.cost_with_voucher for item in unpaid_items)


def _check_blocks_and_get_updated_invoice(request):
    total = Decimal(request.POST.get("cart_blocks_total"))

    checked = {
        "total": total,
        "invoice": None,
        "redirect": False,
        "redirect_url": None,
        "checkout_type": "blocks",
    }

    unpaid_blocks = get_unpaid_blocks_for_checkout(request.user)
    if not unpaid_blocks:
        messages.warning(request, "No blocks in cart")
        checked.update({"redirect": True, "redirect_url": reverse("booking:shopping_basket")})
        return checked

    # check the total against the total calculated by using the voucher-applied costs from the model
    # (this is what will be applied to the stripe payment and invoice, so it's what we care about)
    checked_total = items_with_voucher_total(unpaid_blocks)

    if total != checked_total:
        messages.error(request, "Some cart items changed; please refresh the page and try again")
        # reset any voucher codes that may have expired so user has to reapply them
        for block in unpaid_blocks:
            block.reset_voucher_code()
        checked.update({"redirect": True, "redirect_url": reverse("booking:shopping_basket")})
        return checked

    for unpaid_block in unpaid_blocks:
        # mark the time we've successfully proceeded to checkout for this booking
        # so we avoid cleaning it up during payment processing
        unpaid_block.mark_checked()

    unpaid_block_ids = {block.id for block in unpaid_blocks}

    def _get_matching_invoice(invoices):
        for invoice in invoices:
            if set(invoice.blocks.values_list("id", flat=True)) == unpaid_block_ids:
                return invoice

    # check for an existing unpaid invoice for this user
    invoices = Invoice.objects.filter(username=request.user.email, paid=False)
    # if any exist, check for one where the items are the same
    invoice = _get_matching_invoice(invoices)

    if invoice is None:
        invoice = Invoice.objects.create(
            invoice_id=Invoice.generate_invoice_id(), amount=Decimal(total), username=request.user.email,
        )
        for block in unpaid_blocks:
            block.invoice = invoice
            block.save()
    else:
        # If an invoice with the expected items is found, make sure its total is current and any total voucher
        # is updated
        invoice.amount = Decimal(total)
        invoice.save()

    checked.update({"invoice": invoice})

    if total == 0:
        # if the total in the cart is 0, then a voucher has been applied to all blocks/checkout total
        # and we can mark everything as paid now
        for block in unpaid_blocks:
            block.paid = True
            block.save()
        invoice.paid = True
        invoice.save()
        msg = []

        messages.success(request, f"Voucher applied successfully. {'; '.join(msg)}")
        checked.update({"redirect": True, "redirect_url": reverse("booking:lessons")})

    return checked


def get_unpaid_bookings_for_checkout(user):
    return user.bookings.filter(
        paid=False, status='OPEN', event__date__gte=timezone.now(), no_show=False, 
        paypal_pending=False, event__payment_open=True
    )


def _check_bookings_and_get_updated_invoice(request):
    total = Decimal(request.POST.get("cart_bookings_total"))

    checked = {
        "total": total,
        "invoice": None,
        "redirect": False,
        "redirect_url": None,
        "checkout_type": "bookings",
    }

    unpaid_bookings = get_unpaid_bookings_for_checkout(request.user)
    
    if not unpaid_bookings:
        messages.warning(request, "No bookings in cart")
        checked.update({"redirect": True, "redirect_url": reverse("booking:shopping_basket")})
        return checked

    # check the total against the total calculated by using the voucher-applied costs from the model
    # (this is what will be applied to the stripe payment and invoice, so it's what we care about)
    checked_total = items_with_voucher_total(unpaid_bookings)

    if total != checked_total:
        messages.error(request, "Some cart items changed; please refresh the page and try again")
        # reset any voucher codes that may have expired so user has to reapply them
        for booking in unpaid_bookings:
            booking.reset_voucher_code()
        checked.update({"redirect": True, "redirect_url": reverse("booking:shopping_basket")})
        return checked

    for unpaid_booking in unpaid_bookings:
        # mark the time we've successfully proceeded to checkout for this booking
        # so we avoid cleaning it up during payment processing
        unpaid_booking.mark_checked()

    unpaid_booking_ids = {booking.id for booking in unpaid_bookings}

    def _get_matching_invoice(invoices):
        for invoice in invoices:
            if {booking.id for booking in invoice.bookings.all()} == unpaid_booking_ids:
                return invoice

    # check for an existing unpaid invoice for this user
    invoices = Invoice.objects.filter(username=request.user.email, paid=False)
    # if any exist, check for one where the items are the same
    invoice = _get_matching_invoice(invoices)

    if invoice is None:
        invoice = Invoice.objects.create(
            invoice_id=Invoice.generate_invoice_id(), amount=Decimal(total), username=request.user.email,
        )
        for booking in unpaid_bookings:
            booking.invoice = invoice
            booking.save()
    else:
        # If an invoice with the expected items is found, make sure its total is current and any total voucher
        # is updated
        invoice.amount = Decimal(total)
        invoice.save()

    checked.update({"invoice": invoice})

    if total == 0:
        # if the total in the cart is 0, then a voucher has been applied to all blocks/checkout total
        # and we can mark everything as paid now
        for booking in unpaid_bookings:
            booking.paid = True
            booking.save()
        invoice.paid = True
        invoice.save()
        msg = []

        messages.success(request, f"Voucher applied successfully. {'; '.join(msg)}")
        checked.update({"redirect": True, "redirect_url": reverse("booking:lessons")})

    return checked


def _check_items_and_get_updated_invoice(request):

    # what sort of checkout is it? block/bookings
    if "cart_bookings_total" in request.POST:
        return _check_bookings_and_get_updated_invoice(request)
    elif "cart_blocks_total" in request.POST:
        return _check_blocks_and_get_updated_invoice(request)
    else:
        # no expected total, redirect to shopping basket
        return {"redirect": True, "redirect_url": reverse("booking:shopping_basket")}


@require_http_methods(['POST'])
def stripe_checkout(request):
    """
    Called when clicking on checkout from the shopping basket page
    Re-check the voucher codes and the total
    """
    checked_dict = _check_items_and_get_updated_invoice(request)
    if checked_dict["redirect"]:
        return HttpResponseRedirect(checked_dict["redirect_url"])
    total = checked_dict["total"]
    invoice = checked_dict["invoice"]
    checkout_type = checked_dict["checkout_type"]
    logger.info("Stripe checkout for invoice id %s", invoice.invoice_id)
    # Create the Stripe PaymentIntent
    stripe.api_key = settings.STRIPE_SECRET_KEY
    seller = Seller.objects.filter(site=Site.objects.get_current(request)).first()

    context = {}
    if seller is None:
        logger.error("No seller found on Stripe checkout attempt")
        context.update({"preprocessing_error": True})
    else:
        stripe_account = seller.stripe_user_id
        # Stripe requires the amount as an integer, in pence
        total_as_int = int(total * 100)

        payment_intent_data = {
            "payment_method_types": ['card'],
            "amount": total_as_int,
            "currency": 'gbp',
            "stripe_account": stripe_account,
            "description": f"{''.join([request.user.first_name, request.user.last_name]) if request.user.is_authenticated else ''}-invoice#{invoice.invoice_id}",
            "metadata": {
                "invoice_id": invoice.invoice_id, "invoice_signature": invoice.signature(), **invoice.items_metadata()},
        }

        if not invoice.stripe_payment_intent_id:
            payment_intent = stripe.PaymentIntent.create(**payment_intent_data)
            invoice.stripe_payment_intent_id = payment_intent.id
            invoice.save()
        else:
            try:
                payment_intent_obj = StripePaymentIntent.objects.get(
                    payment_intent_id=invoice.stripe_payment_intent_id
                )
            except StripePaymentIntent.DoesNotExist:
                logger.info("Payment intent obj %s not found, retrieving from stripe", invoice.stripe_payment_intent_id)
                payment_intent_obj = stripe.PaymentIntent.retrieve(
                    invoice.stripe_payment_intent_id, stripe_account=stripe_account
                )
            
            try:
                if payment_intent_obj.metadata != payment_intent_data["metadata"]:
                    logger.info("Resetting metadata")
                    # unset all metadata so we can reset it to the new values
                    # otherwise deleted items will not be removed
                    unset_metadata = {k: "" for k in payment_intent_obj.metadata}
                    stripe.PaymentIntent.modify(
                        invoice.stripe_payment_intent_id, metadata=unset_metadata, stripe_account=stripe_account
                    )
                logger.info("Updating payment intent")
                payment_intent = stripe.PaymentIntent.modify(
                    invoice.stripe_payment_intent_id, **payment_intent_data,
                )
            except stripe.error.InvalidRequestError as error:
                payment_intent = stripe.PaymentIntent.retrieve(
                    invoice.stripe_payment_intent_id, stripe_account=stripe_account
                )
                if payment_intent.status == "succeeded":
                    context.update({"preprocessing_error": True})
                    context.update({"already_paid": True})
                else:
                    context.update({"preprocessing_error": True})
                logger.error(
                    "Error processing checkout for invoice: %s, payment intent: %s (%s)", invoice.invoice_id, payment_intent.id, str(error)
                )
        # update/create the django model PaymentIntent - this isjust for records
        StripePaymentIntent.update_or_create_payment_intent_instance(payment_intent, invoice, seller)

        context.update({
            "client_secret": payment_intent.client_secret,
            "stripe_account": stripe_account,
            "stripe_api_key": settings.STRIPE_PUBLISHABLE_KEY,
            "cart_items": invoice.items_dict(),
            "cart_total": total,
            "checkout_type": checkout_type,
         })
    return TemplateResponse(request, "stripe_payments/checkout.html", context)


def check_total(request):
    checkout_type = request.GET.get("checkout_type")
    total = None
    if request.user.is_authenticated:
        if checkout_type == "bookings":
            unpaid_items = get_unpaid_bookings_for_checkout(request.user)
        elif checkout_type == "blocks":
            unpaid_items = get_unpaid_blocks_for_checkout(request.user)
        total = items_with_voucher_total(unpaid_items)
    else:
        # TODO gift vouchers/ ticket bookings
        ...

    return JsonResponse({"total": total})
