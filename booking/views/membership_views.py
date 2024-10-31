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
from django.shortcuts import get_object_or_404, HttpResponseRedirect, HttpResponse
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone

from stripe_payments.models import Seller

from activitylog.models import ActivityLog
from booking.models import Membership, UserMembership, StripeSubscriptionVoucher
from booking.forms import ChooseMembershipForm, ChangeMembershipForm
from booking.views.views_utils import DataPolicyAgreementRequiredMixin

from stripe_payments.models import StripeSubscriptionInvoice
from stripe_payments.utils import StripeConnector, get_utcdate_from_timestamp, get_first_of_next_month_from_timestamp

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(['GET'])
def membership_create(request):
    has_ongoing_membership = request.user.memberships.filter(subscription_status__in=["active", "past_due"], end_date__isnull=True).exists()

    # Does user have an existing membership that ends after this billing period?
    # User can buy membership if they have a current one that is due to end at the end of the month, but
    # should only have option to start from next month

    # If the current date is after the 25th, the next end date (the 1st of the next month plus 1, because the billing date for this
    # month has already passed)
    # A membership that ends on the next month plus 1 is considered an ongoing one

    # e.g.
    # It is the 26th April
    # No memberships --> option to purchase for current billing period only (started 25th April, for May membership)
    # User has M1 started 1st April, ends 1st May - has current cancelled membership (April), so can purchase a new one for May
    # User has M1 started 1st April, no end - has current ongoing membership, can't purchase
    # User has M1 starts 1st May, no end - has future ongoing membership (last billed 25th April), can't purchase
    # User has M1 starts 1st May, ends 1st June, no end - has future membership (last billed 25th April), considered ongoing, can't purchase
    next_end_date = UserMembership.calculate_membership_end_date(datetime.now())
    if datetime.now().day >= 25:
        next_end_date = next_end_date + relativedelta(months=1)
        if not has_ongoing_membership:
            has_ongoing_membership = request.user.memberships.filter(subscription_status="active", end_date=next_end_date).exists()
        
    has_cancelled_current_membership = request.user.memberships.filter(start_date__lt=datetime.now(), end_date=next_end_date).exists()

    if not has_ongoing_membership:
        form = ChooseMembershipForm(has_cancelled_current_membership=has_cancelled_current_membership)
    else:
        form = None

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

        # voucher code is only sent if it's valid, no need to check here
        discounts = None
        voucher = None
        if data.get("voucher_code"):
            try:
                voucher = StripeSubscriptionVoucher.objects.get(code=data["voucher_code"])
                discounts = [{"promotion_code": voucher.promo_code_id}]
            except StripeSubscriptionVoucher.DoesNotExist:
                ...

        # compare existing subscriptions WITHOUT discounts, so we can update an existing one with a 
        # different voucher code if necessary
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
            # update subscription changed discounts if necessary
            if voucher is None:
                # No voucher code; remove any previously applied discount
                if subscription.discount:
                    client.remove_discount_from_subscription(subscription.id)
            else:
                # Voucher code; remove any different previous discount and apply this new one
                if subscription.discount:
                    if subscription.discount.promotion_code != voucher.promo_code_id:
                        client.remove_discount_from_subscription(subscription.id)
                        client.add_discount_to_subscription(subscription.id, promo_code_id=voucher.promo_code_id)
                else:
                    # no existing discount, just add the new one
                    client.add_discount_to_subscription(subscription.id, promo_code_id=voucher.promo_code_id)

            if subscription.pending_setup_intent is not None:
                confirm_type = "setup"
                client_secret =  subscription.pending_setup_intent.client_secret
            else:
                confirm_type = "payment"
                payment_intent = subscription.latest_invoice.payment_intent
                client_secret = payment_intent.client_secret
        else:
            sub_kwargs_with_discounts = client.get_subscription_kwargs(customer_id, price_id, backdate=backdate, discounts=discounts)
            subscription = client.create_subscription(
                customer_id, price_id, backdate=backdate, subscription_kwargs=sub_kwargs_with_discounts
            )
            if subscription.pending_setup_intent is not None:
                confirm_type = "setup"
                client_secret =  subscription.pending_setup_intent.client_secret
            else:
                confirm_type = "payment"
                client_secret =  subscription.latest_invoice.payment_intent.client_secret
        
        return JsonResponse({"clientSecret": client_secret, "type": confirm_type})

    except Exception as e:
        logger.error("Unexpected Stripe error during subscription checkout: %s", str(e))
        if settings.DEBUG:
            error = str(e)
        else:
            error = "An unexpected error occurred."
        return JsonResponse({"error": {"message": str(error)}}, status=400)


def subscription_cancel(request, subscription_id):
    user_membership = get_object_or_404(UserMembership, subscription_id=subscription_id)
    if request.method == "POST":
        client = StripeConnector()
        cancel_immediately = not user_membership.payment_has_started()
        # Cancel immediately if the first subscription payment is in the future
        try:
            client.cancel_subscription(subscription_id, cancel_immediately=cancel_immediately)
        except Exception as err:
            logger.error(err)
            messages.error(request, "Something went wrong")
        else:
            # unset bookings for dates after the subscription end date - done in webhook
            ActivityLog.objects.create(log=f"User {request.user} cancelled membership {user_membership.membership.name}")
            messages.success(
                request, "Your membership has been cancelled."
            )
        return HttpResponseRedirect(reverse("membership_list"))
    return TemplateResponse(request,  "booking/membership_cancel.html", {"user_membership": user_membership})


def validate_voucher_code(voucher_code, membership, existing_subscription_id=False):
    voucher = None
    voucher_message = None
    voucher_valid = False
    if voucher_code:
        # check the basic things we can check first before asking stripe
        try:
            voucher = StripeSubscriptionVoucher.objects.get(code=voucher_code)
        except StripeSubscriptionVoucher.DoesNotExist:
            voucher_message = f"{voucher_code} is not a valid code"

        if voucher:
            if not voucher.active or (voucher.redeem_by and voucher.redeem_by < timezone.now()):
                voucher_message = f"{voucher_code} is not a valid code"
            elif not voucher.memberships.filter(id=membership.id):
                voucher_message = f"{voucher_code} is not valid for the selected membership"
            elif existing_subscription_id:
                if voucher.new_memberships_only:
                    voucher_message = f"{voucher_code} is only valid for new memberships"
                else:
                    # check if it's already been used
                    if StripeSubscriptionInvoice.objects.filter(subscription_id=existing_subscription_id, promo_code_id=voucher.promo_code_id).exists():
                        voucher_message = f"{voucher_code} has already been applied to this membership"

            if not voucher_message:
                client = StripeConnector()
                promo_code = client.get_promo_code(voucher.promo_code_id)
                if promo_code.active:       
                    voucher_message = f"Voucher valid: {voucher.description}"
                    voucher_valid = True
                else:
                    voucher_message = f"{voucher_code} is not a valid code"

    return voucher, voucher_valid, voucher_message


@login_required
@require_http_methods(['POST'])
def membership_voucher_validate(request):
    client = StripeConnector()
    membership = get_object_or_404(Membership, id=request.POST.get("membership_id"))
    context = {
        "htmx": True,
        "membership": membership,
        "stripe_account": client.connected_account_id,
        "stripe_api_key": settings.STRIPE_PUBLISHABLE_KEY,
        "stripe_return_url": request.build_absolute_uri(reverse("stripe_payments:stripe_subscribe_complete")),
        "customer_id": request.user.userprofile.stripe_customer_id,
        "creating": request.POST.get("creating"),
        "client_secret": request.POST.get("client_secret", ""),
        "backdate": request.POST.get("backdate"),
        "amount": request.POST.get("amount"),
        "regular_amount": membership.price,
        "confirm_type": request.POST.get("confirm_type"),
    }

    # posts to this endpoint are to validate a voucher code and update the form
    voucher_code = request.POST.get("voucher_code").lower()
    voucher, voucher_valid, voucher_message = validate_voucher_code(voucher_code, membership)

    amount_in_p = int(membership.price * 100)
    if voucher_valid:
        if voucher.percent_off:
            next_amount_in_p = amount_in_p - (amount_in_p * (voucher.percent_off / 100))
        else:
            next_amount_in_p = amount_in_p - (voucher.amount_off * 100)
    else:
        next_amount_in_p = amount_in_p
    
    context.update(
        {
            "voucher_message": voucher_message,
            "voucher_valid": voucher_valid,
            "voucher_code": voucher_code,
            "next_amount": next_amount_in_p / 100,
        }
    )

    return TemplateResponse(request, "stripe_payments/includes/membership_voucher_form.html", context)


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
            "confirm_type": confirm_type,
        })
    else:
        membership = get_object_or_404(Membership, id=request.POST.get("membership"))

        customer_id = client.get_or_create_stripe_customer(request.user)
        
        # backdate is a string, '0' or '1'; convert to int
        backdate = int(request.POST.get("backdate"))

        # if explicitly backdating or subscribing to next month after payment date (25th), we
        # charge the first month immediately
        regular_amount = membership.price
        if backdate or datetime.now().day >= 25:
            amount_to_charge_now = int(regular_amount * 100)
        else:
            amount_to_charge_now = 0

        context.update({
            "creating": True,
            "membership": membership,
            "customer_id": customer_id,
            "backdate": backdate,
            # the amount passed to Stripe to change now (in p)
            "amount": amount_to_charge_now,
            # amounts to display (in £)
            "regular_amount": regular_amount,
            "next_amount": regular_amount,
        })
    return TemplateResponse(request, "stripe_payments/subscribe.html", context)


def ensure_subscription_up_to_date(user_membership, subscription, subscription_id=None):
    if subscription is None:
        client = StripeConnector()
        subscription = client.get_subscription(subscription_id)
        if subscription is None:
            return

    # Check cancel_at FIRST; if a subscription was canceled in the future, it
    # will have both a cancel_at and canceled_at attribute, where canceled_at is the date
    # the cancellation was requested, and cancel_at is the date it will actually cancel
    if subscription.cancel_at:
        sub_end = get_utcdate_from_timestamp(subscription.cancel_at)
    elif subscription.canceled_at:
        sub_end = get_utcdate_from_timestamp(subscription.canceled_at)
    else:
        sub_end = None

    status = subscription.status
    if user_membership.subscription_status == "setup_pending":
        # prevent status being updated to active (the stripe subscription status) if
        # the setup intent has not yet succeeded and there's no default_payment_method
        if (
            not subscription.default_payment_method 
            and subscription.pending_setup_intent 
            and subscription.pending_setup_intent.status != "succeeded"
        ):
            status = "setup_pending"

    if status == "active" and user_membership.subscription_status == "incomplete":
        payment_intent_status = subscription.latest_invoice.payment_intent.status
        if payment_intent_status != "succeeded":
            status = "incomplete"

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
    
    return user_membership


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
        next_invoice = client.get_upcoming_invoice(subscription_id)
        if next_invoice.discount:
            voucher_code = StripeSubscriptionVoucher.objects.get(promo_code_id=next_invoice.discount.promotion_code).code
        else:
            voucher_code = None
        upcoming_invoice = {
            "date": get_utcdate_from_timestamp(next_invoice.period_end),
            "amount": next_invoice.total / 100,
            "voucher_code": voucher_code
        }
    else:
        upcoming_invoice = None

    if subscription.latest_invoice:
        if subscription.latest_invoice.discount:
            voucher_code = StripeSubscriptionVoucher.objects.get(promo_code_id=subscription.latest_invoice.discount.promotion_code).code
        else:
            voucher_code = None
        last_invoice = {
            "date": get_utcdate_from_timestamp(subscription.latest_invoice.effective_at),
            "amount": subscription.latest_invoice.total / 100,
            "voucher_code": voucher_code
        }
    else:
        last_invoice = None

    return TemplateResponse(
        request, 
        "booking/membership_status.html", 
        {
            "user_membership": user_membership,
            "this_month": calendar.month_name[this_month],
            "next_month": calendar.month_name[next_month],
            "upcoming_invoice": upcoming_invoice,
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


@login_required
@require_http_methods(['POST'])
def membership_voucher_apply_validate(request):
    voucher_code = request.POST.get("voucher_code")
    user_membership = get_object_or_404(UserMembership, id=request.POST.get("user_membership_id"))

    voucher, voucher_valid, voucher_message = validate_voucher_code(voucher_code, user_membership.membership, existing_subscription_id=user_membership.subscription_id)

    if voucher_valid and "apply" in request.POST:
        messages.success(request, "code applied")
        client = StripeConnector()
        client.add_discount_to_subscription(user_membership.subscription_id, voucher.promo_code_id)
        return HttpResponseRedirect(reverse("membership_status", args=(user_membership.subscription_id,)))
    else:
        context = {
            "user_membership": user_membership, 
            "voucher_message": voucher_message,
            "voucher_valid": voucher_valid,
            "voucher_code": voucher_code
        }

    return TemplateResponse(request, "booking/includes/membership_voucher_apply_form.html", context)
