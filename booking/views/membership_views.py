import calendar
from datetime import datetime
from datetime import timezone as datetime_tz
from dateutil.relativedelta import relativedelta
import json
import logging
from time import sleep

from braces.views import LoginRequiredMixin

from django.template.response import TemplateResponse

from django.views.decorators.http import require_http_methods
from django.views.generic import ListView

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.template.response import TemplateResponse
from django.shortcuts import get_object_or_404, HttpResponseRedirect
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone

from stripe_payments.models import Seller

from activitylog.models import ActivityLog
from booking.models import Membership, UserMembership
from booking.forms import ChooseMembershipForm, ChangeMembershipForm
from booking.views.views_utils import DataPolicyAgreementRequiredMixin
    
from stripe_payments.utils import StripeConnector, get_utcdate_from_timestamp, get_first_of_next_month_from_timestamp

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(['GET'])
def membership_create(request):
    has_ongoing_membership = request.user.memberships.filter(subscription_status__in=["active", "past_due"], end_date__isnull=True).exists()
    # Does user have an existing membership that ends after this month
    # User can buy membership if they have a current one that is due to end at the end of the month, but
    # should only have option to start from next month
    next_end_date = UserMembership.calculate_membership_end_date(datetime.now())
    has_cancelled_current_membership = request.user.memberships.filter(start_date__lt=datetime.now(), end_date=next_end_date).exists()
    
    form = ChooseMembershipForm(has_cancelled_current_membership=has_cancelled_current_membership)
    
    # TODO add discount voucher option
    return TemplateResponse(
        request, 
        "booking/membership_create.html", 
        {
            "form": form, 
            "has_ongoing_membership": has_ongoing_membership,
            "has_cancelled_current_membership": has_cancelled_current_membership,
            "memberships": Membership.objects.purchasable()
        }
    )


@login_required
def membership_change(request, subscription_id):
    user_membership = get_object_or_404(UserMembership, subscription_id=subscription_id)
    old_membership = user_membership.membership
    can_change = not bool(user_membership.end_date)

    # can only change IF the membership is active and not cancelling, i.e. it has no end date
    # changes will all start from the beginning of the next month
    # cancellations will start from the beginning of the next month
    # if it's the user's current (uncancelled) membership, this one will be cancelled from the end of the month and
    # a new one created from start of next month
    # if it's a future membership (starting at beginning of next month):
    # - if it's not billed yet, it'll be cancelled from the end of the month (25th) and a new one created that starts
    # from the start of next month - so this one should never be invoiced.

    if request.method == "POST":
        form = ChangeMembershipForm(request.POST, current_membership_id=user_membership.membership.id)
        if form.is_valid():
            membership = form.cleaned_data["membership"]
            client = StripeConnector(request)
            current_subscription = client.get_subscription(subscription_id)
            client.create_subscription(
                request.user.userprofile.stripe_customer_id, price_id=membership.stripe_price_id, backdate=False,
                default_payment_method=current_subscription.default_payment_method,
            )
            # If the current subscription (not membership) starts in the future, just cancel it from now
            # If the start date day is < 25, the user set up a subscription to start in the
            # future, so we need to take the billing anchor date as the start date (start of billing)
            if user_membership.subscription_start_date.day < 25:
                # Verify that the subscription_start_date was earlier in the same month as the billing cycle anchor
                # A user setting up a subscription on 25-end of the month is in the next months subscription, so is
                # automatically backdated for the current month to the 25th
                assert user_membership.subscription_start_date.month == user_membership.subscription_billing_cycle_anchor.month
                subscription_start = user_membership.subscription_billing_cycle_anchor
            else:
                subscription_start = user_membership.subscription_start_date
            client.cancel_subscription(subscription_id, cancel_immediately=subscription_start > timezone.now())

            ActivityLog.objects.create(
                log=f"User {request.user} requested to change membership plan from {old_membership.name} to {membership.name})"
            )
            
            # rearrange bookings for future memberships from the cancelled membership to the new one
            # Done in webhook when first membership is cancelled, and when second membership is created

            return HttpResponseRedirect(reverse("membership_list"))

    elif can_change:
        form = ChangeMembershipForm(current_membership_id=user_membership.membership.id)
    else:
        form = None
    return TemplateResponse(
        request, 
        "booking/membership_change.html", 
        {"form": form, "can_change": can_change})


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

        # get user's subscriptions and check for one with a matching price id and date that is either
        # incomplete or active with non-succeeded pending_setup_intent
        # Otherwise, create a new one
        subscription_kwargs = client.get_subscription_kwargs(customer_id, price_id, backdate=backdate)
        # status=None will fetch all non-cancelled subscriptions
        user_subscriptions = client.get_subscriptions_for_customer(customer_id, status=None)

        def _compare_subscription_kwargs(subsc):
            if subsc.status not in ["active", "incomplete"]:
                return False
            if subsc.status == "active":
                if subsc.pending_setup_intent is not None and subsc.pending_setup_intent.status == "succeeded":
                    return False
                elif subsc.latest_invoice is not None and subsc.latest_invoice.paid:
                    return False
            to_compare = {
                **subscription_kwargs,
                "customer": subsc.customer,
                "items": [
                    {"price": item.price.id, "quantity": item.quantity} for item in subsc['items'].data
                ],
                "billing_cycle_anchor": subsc.billing_cycle_anchor,
                "payment_settings": {'save_default_payment_method': subsc.payment_settings.save_default_payment_method},
            }
            return to_compare == subscription_kwargs
        subscription = next(
            (
                subs for subs in user_subscriptions.values() if _compare_subscription_kwargs(subs)
            ),
            None
        )
        if subscription is not None:
            if subscription.pending_setup_intent is not None:
                confirm_type = "setup"
                client_secret =  subscription.pending_setup_intent.client_secret
            else:
                confirm_type = "payment"
                payment_intent_id = subscription.latest_invoice.payment_intent
                payment_intent = client.get_payment_intent(payment_intent_id)
                client_secret = payment_intent.client_secret
        else:
            subscription = client.create_subscription(customer_id, price_id, backdate=backdate, subscription_kwargs=subscription_kwargs)
            if subscription.pending_setup_intent is not None:
                confirm_type = "setup"
                client_secret =  subscription.pending_setup_intent.client_secret
            else:
                confirm_type = "payment"
                client_secret =  subscription.latest_invoice.payment_intent.client_secret
        
        return JsonResponse({"clientSecret": client_secret, "type": confirm_type})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


def subscription_cancel(request, subscription_id):
    user_membership = get_object_or_404(UserMembership, subscription_id=subscription_id)
    if request.method == "POST":
        client = StripeConnector()
        cancel_immediately = not user_membership.payment_has_started()
        # Cancel immediately if the first subscription payment is in the future
        client.cancel_subscription(subscription_id, cancel_immediately=cancel_immediately) 
        # unset bookings for dates after the subscription end date - done in webhook
        ActivityLog.objects.create(log=f"User {request.user} cancelled membership {user_membership.membership.name}")
        messages.success(
            request, "Your membership has been cancelled."
        )
        return HttpResponseRedirect(reverse("membership_list"))
    return TemplateResponse(request,  "booking/membership_cancel.html", {"user_membership": user_membership})


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
    try:
        client = StripeConnector(request)
    except Seller.DoesNotExist:
        logger.error("No seller found on Stripe checkout attempt")
        return TemplateResponse(request, "stripe_payments/subscribe.html", {"preprocessing_error": True})

    context = {
        "stripe_account": client.connected_account_id,
        "stripe_api_key": settings.STRIPE_PUBLISHABLE_KEY,
        "stripe_return_url": request.build_absolute_uri(reverse("stripe_payments:stripe_subscribe_complete")),
        "client_secret": "",
        "backdate": 0,
        "amount": "",
    }

    # Are we updating payment for an exisitng subscription?
    # This happens if a setup or payment failed; linked from the membership status page
    subscription_id = request.POST.get("subscription_id")
    if subscription_id:
        user_membership = get_object_or_404(UserMembership, subscription_id=subscription_id)
        # Updating payment for an existing subscription
        # Fetch subscription, expand latest_invoice.payment_intent or pending_setup_intent
        subscription = client.get_subscription(subscription_id)

        if user_membership.subscription_status == "setup_pending":
            setup_intent = client.get_setup_intent(user_membership.pending_setup_intent)
            if setup_intent.status == "succeeded":
                user_membership.subscription_status = "active"
                user_membership.pending_setup_intent = None
                user_membership.save()
                messages.info(request, "Subscription is active")
                return HttpResponseRedirect(reverse("membership_status", args=(subscription_id,)))
            
            client_secret = subscription.pending_setup_intent.client_secret
            confirm_type = "setup"
        elif subscription.status == "active":
            if user_membership.subscription_status != subscription.status:
                user_membership.subscription_status = "active"
                user_membership.save()
            messages.info(request, "Subscription is active")
            return HttpResponseRedirect(reverse("membership_status", args=(subscription_id,)))
        else:
            client_secret = subscription.latest_invoice.payment_intent.client_secret
            confirm_type = "payment"
        
        context.update({
            "membership": user_membership.membership,
            "customer_id": request.user.userprofile.stripe_customer_id,
            "client_secret": client_secret,
            "confirm_type": confirm_type
        })
    else:
        membership = get_object_or_404(Membership, id=request.POST.get("membership"))

        customer_id = client.get_or_create_stripe_customer(request.user)
        
        # backdate is a string, '0' or '1'; convert to int
        backdate = int(request.POST.get("backdate"))
        
        # if explicitly backdating or subscribing to next month after payment date (25th), we
        # charge the first month immediately
        if backdate or datetime.now().day >= 25:
            amount_to_charge_now = membership.price * 100
        else:
            amount_to_charge_now = 0

        context.update({
            "creating": True,
            "membership": membership,
            "customer_id": customer_id,
            "backdate": backdate,
            "amount": amount_to_charge_now,
        })

    return TemplateResponse(request, "stripe_payments/subscribe.html", context)


def ensure_subscription_up_to_date(user_membership, subscription, subscription_id=None):
    if subscription is None:
        client = StripeConnector()
        subscription = client.get_subscription(subscription_id)
        if subscription is None:
            return

    if subscription.canceled_at:
        sub_end = get_utcdate_from_timestamp(subscription.canceled_at)
    elif subscription.cancel_at:
        sub_end = get_utcdate_from_timestamp(subscription.cancel_at)
    else:
        sub_end = None

    status = subscription.status
    if user_membership.subscription_status == "setup_pending":
        # prevent status being updated to active (the stripe subscription status) if
        # the setup intent has not yet succeeded and there's no default_payment_method
        if not subscription.default_payment_method and subscription.pending_setup_intent.status != "succeeded":
            status = "setup_pending"

    subscription_data = {
        "subscription_start_date": get_utcdate_from_timestamp(subscription.start_date),
        "subscription_end_date": sub_end,
        "start_date": get_first_of_next_month_from_timestamp(subscription.start_date),
        "end_date": user_membership.calculate_membership_end_date(sub_end),
        "subscription_status": status,
        "subscription_billing_cycle_anchor": get_utcdate_from_timestamp(subscription.billing_cycle_anchor),
    }
    needs_update = False
    for attribute, value in subscription_data.items():
        if getattr(user_membership, attribute) != value:
            needs_update = True
            setattr(user_membership, attribute, value)
    
    if needs_update:
        user_membership.save()


@login_required
@require_http_methods(['GET'])
def membership_status(request, subscription_id):
    user_membership = get_object_or_404(UserMembership, user=request.user, subscription_id=subscription_id)
    this_month = datetime.now().month
    next_month = (this_month + 1 - 12) % 12
    
    client = StripeConnector()
    subscription = client.get_subscription(subscription_id)
    # Don't show next due date for already cancelled subscriptions, or subscriptions that are
    # cancelling in the future
    if user_membership.subscription_status != 'canceled' and not subscription.cancel_at:
        next_due = get_utcdate_from_timestamp(subscription.current_period_end)
    else:
        next_due = None
    last_invoice = get_utcdate_from_timestamp(subscription.latest_invoice.effective_at) if subscription.latest_invoice else None

    return TemplateResponse(
        request, 
        "booking/membership_status.html", 
        {
            "user_membership": user_membership,
            "this_month": calendar.month_name[this_month],
            "next_month": calendar.month_name[next_month],
            "next_due": next_due,
            "last_invoice": last_invoice,
            "cancelling": bool(user_membership.end_date)
        }
    )


class MembershipListView(DataPolicyAgreementRequiredMixin, LoginRequiredMixin, ListView):

    model = UserMembership
    context_object_name = 'memberships'
    template_name = 'booking/memberships.html'
    paginate_by = 20

    def get_queryset(self):
        return self.request.user.memberships.all()
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            queryset = self.get_queryset()
            customer_id = self.request.user.userprofile.stripe_customer_id
            if customer_id:
                client = StripeConnector()
                # check non-cancelled memberships
                subscriptions = client.get_subscriptions_for_customer(customer_id, status=None)
                for user_membership in queryset.exclude(subscription_status="canceled"):
                    ensure_subscription_up_to_date(user_membership, subscriptions.get(user_membership.subscription_id), user_membership.subscription_id)

        return super().dispatch(request, *args, **kwargs)
