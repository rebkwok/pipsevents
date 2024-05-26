from datetime import datetime
import json
import logging

from django.template.response import TemplateResponse

from django.views.decorators.http import require_http_methods


from django.conf import settings
from django.contrib.auth.decorators import login_required
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

from booking.models import Membership, UserMembership
from booking.forms import ChooseMembershipForm

from stripe_payments.utils import StripeConnector

logger = logging.getLogger(__name__)


@login_required
def membership_create(request):
    form = ChooseMembershipForm()
    # TODO add discount voucher option
    return TemplateResponse(request, "booking/membership_create.html", {"form": form})


@require_http_methods(['POST'])
def subscription_create(request):
    """Called by frontend after payment details have been taken"""
    data = json.loads(request.body)
    try:
        customer_id = data["customer_id"]
        price_id = data["price_id"]
        # backdate is a string, '0' or '1'; convert to int and bool
        backdate = bool(int(data["backdate"]))

        client = StripeConnector(request)
        subscription = client.create_subscription(customer_id, price_id, backdate=backdate)
        if subscription.pending_setup_intent is not None:
            return JsonResponse({"clientSecret": subscription.pending_setup_intent.client_secret, "type": "setup"})
        else:
            return JsonResponse({"clientSecret": subscription.latest_invoice.payment_intent.client_secret, "type": "payment"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_http_methods(['POST'])
def stripe_subscription_checkout(request):
    """
    Previous page: subscription setup form
    - selects Membership
    - checks box to confirm payment info can be stored
    
    This page:
    create stripe customer if User.userprofile doesn't already have stripe_customer_id
    Identify amount that's due now
    Pass relevant date to frontend
    JS handles collecting payment first, then calls subscription_create to create the
    subscription. 
    """
    membership = get_object_or_404(Membership, id=request.POST.get("membership"))
    try:
        client = StripeConnector(request)
    except Seller.DoesNotExist:
        logger.error("No seller found on Stripe checkout attempt")
        return TemplateResponse(request, "stripe_payments/subscribe.html", {"preprocessing_error": True})

    customer_id = client.get_or_create_stripe_customer(request.user)
    
    # backdate is a string, '0' or '1'; convert to int
    backdate = int(request.POST.get("backdate"))
    
    # if explicitly backdating or subscribing to next month after payment date (25th), we
    # charge the first month immediately
    if backdate or datetime.now().day >= 25:
        amount_to_charge_now = membership.price * 100
    else:
        amount_to_charge_now = 0

    # update/create the django model PaymentIntent - this isjust for records
    # StripePaymentIntent.update_or_create_payment_intent_instance(payment_intent, invoice, seller)
    context = {
        "membership": membership,
        "customer_id": customer_id,
        "stripe_account": client.connected_account_id,
        "stripe_api_key": settings.STRIPE_PUBLISHABLE_KEY,
        "stripe_return_url": request.build_absolute_uri(reverse("stripe_payments:stripe_subscribe_complete")),
        "backdate": backdate,
        "amount": amount_to_charge_now,
    }

    return TemplateResponse(request, "stripe_payments/subscribe.html", context)
