import logging

from django.template.response import TemplateResponse

from django.views.decorators.http import require_http_methods


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

from booking.models import Membership, UserMembership
from booking.forms import ChooseMembershipForm

from stripe_payments.utils import StripeConnector

logger = logging.getLogger(__name__)


def membership_create(request):
    form = ChooseMembershipForm()
    # TODO add when to start membership
    return TemplateResponse(request, "booking/membership_create.html", {"form": form})


@require_http_methods(['POST'])
def stripe_subscription_checkout(request):
    """
    Previous page: subscription setup form
    - selects Membership
    - checks box to confirm payment info can be stored
    
    This page:
    create stripe customer if User.userprofile doesn't already have stripe_customer_id
    look for an existing incomplete subscription for this price and customer 
    create subscription with payment_behavior=default_incomplete.
    Get payment intent info from subscription.latest_invoice.payment_intent
    reuse "stripe_payments/checkout.html"?
    """
    membership = get_object_or_404(Membership, id=request.POST.get("membership"))
    try:
        client = StripeConnector(request)
    except Seller.DoesNotExist:
        logger.error("No seller found on Stripe checkout attempt")
        return TemplateResponse(request, "stripe_payments/subscribe.html", {"preprocessing_error": True})

    customer_id = client.get_or_create_stripe_customer(request.user)
    # check for existing incomplete UserMembership
    user_membership = UserMembership.objects.filter(user=request.user, membership=membership, subscription_status="incomplete").first()
    subscription = None
    if user_membership is not None:
        # TODO get the subscription and ensure status is incomplete (not incomplete_expired)
        # AND and check/update the subcription to ensure the start date and price id are
        # correct (in case membership price has changed, or user has changed required start
        # date of membership)
        subscription = client.get_subscription(user_membership.subscription_id, status="incomplete")
    
    backdate = request.POST.get("backdate", True)
    if subscription is None:
        subscription = client.create_subscription(customer_id, membership.stripe_price_id, backdate=backdate)

    if backdate:
        client_secret = subscription.latest_invoice.payment_intent.client_secret
    else:
        client_secret = subscription.pending_setup_intent.client_secret

    # update/create the django model PaymentIntent - this isjust for records
    # StripePaymentIntent.update_or_create_payment_intent_instance(payment_intent, invoice, seller)
    context = {
        "membership": membership,
        "client_secret": client_secret,
        "stripe_account": client.connected_account_id,
        "stripe_api_key": settings.STRIPE_PUBLISHABLE_KEY,
        "stripe_return_url": request.build_absolute_uri(reverse("stripe_payments:stripe_payment_complete")),
        "backdate": backdate,
    }

    return TemplateResponse(request, "stripe_payments/subscribe.html", context)
