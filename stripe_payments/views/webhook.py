from datetime import datetime
from datetime import timezone as datetime_tz
from decimal import Decimal
import json
import logging

import stripe

from django.conf import settings
from django.contrib.auth.models import User
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import HttpResponse

from activitylog.models import ActivityLog
from booking.models import UserMembership, Membership
from ..emails import (
    send_failed_payment_emails, 
    send_processed_refund_emails, 
    send_updated_membership_email_to_support,
    send_payment_expiring_email,
    send_subscription_past_due_email,
    send_subscription_renewal_upcoming_email,
    send_subscription_created_email
)
from ..exceptions import StripeProcessingError
from ..models import Seller, StripeSubscriptionInvoice
from ..utils import (
    get_invoice_from_event_metadata, 
    StripeConnector, 
    get_first_of_next_month_from_timestamp,
    get_utcdate_from_timestamp,
    process_completed_stripe_payment
)


logger = logging.getLogger(__name__)


@csrf_exempt
def stripe_webhook(request):
    stripe.api_key = settings.STRIPE_SECRET_KEY
    payload = request.body
    sig_header = request.META['HTTP_STRIPE_SIGNATURE']

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_ENDPOINT_SECRET)
    except ValueError as e:
        # Invalid payload
        logger.error(e)
        return HttpResponse(str(e), status=400)
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        logger.error(e)
        return HttpResponse(str(e), status=400)

    event_object = event.data.object
    logger.info("event type", event.type)

    if event.type == "account.application.authorized":
        connected_accounts = stripe.Account.list().data
        for connected_account in connected_accounts:
            seller = Seller.objects.filter(stripe_user_id=connected_account.id)
            if not seller.exists():
                logger.error(f"Stripe account has no associated seller on this site %s", connected_account.id)
                # return 200 so we don't keep trying. The error log will trigger an email to support.
                return HttpResponse("Stripe account has no associated seller on this site", status=200)
        return HttpResponse(status=200)

    elif event.type == "account.application.deauthorized":
        connected_accounts = stripe.Account.list().data
        connected_account_ids = [account.id for account in connected_accounts]
        for seller in Seller.objects.all():
            if seller.stripe_user_id not in connected_account_ids:
                seller.site = None
                seller.save()
                logger.info(f"Stripe account disconnected: %s", seller.stripe_user_id)
                ActivityLog.objects.create(log=f"Stripe account disconnected: {seller.stripe_user_id}")
        return HttpResponse(status=200)

    try:
        client = StripeConnector()
    except Seller.DoesNotExist:
        # No seller connected
        logger.error("No seller account set up, PI ignored")
        return HttpResponse("Ignored: No seller account set up for site", status=200)
    
    try:
        account = event.account
        if account != client.connected_account_id:
            # relates to a different seller, just return and let the next webhook manage it
            logger.info("Mismatched seller account %s", account)
            return HttpResponse("Ignored: Mismatched seller account", status=200)

        # try to get the invoice from the event metadata; if we can get a valid invoice, it's an
        # event related to a payment for an immediate checkout (booking, block, ticket_booking) and not for a subscription
        # Handle the payment intent and refund events
        # This raises an error if there is an invoice id in the metadata but no associated local Invoice object in the db
        try:    
            invoice = get_invoice_from_event_metadata(event_object, raise_immediately=True)
        except StripeProcessingError as e:
            # capture known errors, log and acknowledge. We only want to return 400s to stripe for unexpected
            # errors
            logger.error(str(e))
            send_failed_payment_emails(error=str(e))
            return HttpResponse(str(e), status=200)
        
        if event.type == "payment_intent.succeeded":
            try:
                process_completed_stripe_payment(event_object, invoice, request=request)
            except StripeProcessingError as e:
                # capture known errors, log and acknowledge. We only want to return 400s to stripe for unexpected
                # errors
                logger.error(str(e))
                send_failed_payment_emails(error=str(e))
                return HttpResponse(str(e), status=200)
        elif event.type in ["charge.refund.updated", "charge.refunded"]:
            # No automatic refunds from the system; if a payment is refunded, just send the
            # support emails for checking
            send_processed_refund_emails(invoice, event_object)
        elif event.type == "payment_intent.payment_failed":
            if invoice is not None:
                # payment failed for a one-off item; acknowledge but don't email
                # # no invoice == subscription payment (handled with subscription events) or oob payment (direct from stripe)
                # nothing to do
                logger.info(
                    f"Failed payment intent id: {event_object.id}; invoice id {invoice.invoice_id}; " \
                    f"error {event_object.last_payment_error}"
                )
        elif event.type == "customer.subscription.created":
            # calculate membership start from subscription start timestamp (should be 25th month, membership
            # start is 1st of the next month)
            membership_start = get_first_of_next_month_from_timestamp(event_object.start_date)
            user = User.objects.get(userprofile__stripe_customer_id=event_object.customer)
            # if it's a new subscription with a pending_setup_intent, create as setup_pending
            # default_payment_method is set when changing a plan, uses the payment method from the customer's
            # previous membership plan
            if (
                event_object.status == "active" 
                and not event_object.default_payment_method
                and event_object.pending_setup_intent is not None
            ):
                status = "setup_pending"
            else:
                status = event_object.status
            user_membership = UserMembership.objects.create(
                user=user,
                membership=Membership.objects.get(stripe_price_id=event_object["items"].data[0].price.id),
                start_date=membership_start,
                subscription_id=event_object.id,
                subscription_status=status,
                subscription_start_date=get_utcdate_from_timestamp(event_object.start_date),
                subscription_billing_cycle_anchor=get_utcdate_from_timestamp(event_object.billing_cycle_anchor),
                pending_setup_intent=event_object.pending_setup_intent,
            )
            ActivityLog.objects.create(
                log=f"Stripe webhook: Membership {user_membership.membership.name} set up for {user} (stripe subscription id {event_object.id}, status {status})"
            )
            # allocate bookings if necessary (does nothing is user_membership status is not active, will be called again when 
            # subscription is fully set up. This should only run when a plan has been changed)
            user_membership.reallocate_bookings()
            # Don't send emails until the invoice is paid or setup succeeds
    
        elif event.type == "customer.subscription.deleted":
            # Users can only cancel from end of month, which sends a subscription_update. 
            # Admin users might cancel a subscription immediately from stripe
            # This event is sent when the cancellation actually happens (i.e. not on user demand)
            # Set the subscription_status to cancelled
            try:
                user_membership = UserMembership.objects.get(subscription_id=event_object.id)
            except UserMembership.DoesNotExist:
                # It might not exist if we're cancelling an unpaid setup pending subscription
                ...
            else:
                # the end date for the membership is the stripe subscription end; cancelled at will be the 25th
                # the actual membership ends at the end of the month
                user_membership.subscription_status = event_object.status
                user_membership.subscription_end_date = get_utcdate_from_timestamp(event_object.canceled_at)
                user_membership.end_date = UserMembership.calculate_membership_end_date(user_membership.subscription_end_date)
                user_membership.save()
                user_membership.reallocate_bookings()
                ActivityLog.objects.create(
                    log=f"Stripe webhook: Membership {user_membership.membership.name} for {user_membership.user} (stripe subscription id {event_object.id}, cancelled on {user_membership.subscription_end_date})"
                )

        elif event.type == "customer.subscription.updated":
            user_membership = UserMembership.objects.get(subscription_id=event_object.id)
            old_status = user_membership.subscription_status
            status_changed = user_membership.subscription_status != event_object.status
            if status_changed:
                user_membership.subscription_status = event_object.status
                user_membership.save()
                ActivityLog.objects.create(
                    log=(
                        f"Stripe webhook: Membership {user_membership.membership.name} for user {user_membership.user} updated from {old_status} "
                        f"to {event_object.status}"
                    )
                )

            if event_object.status == "incomplete_expired":
                ActivityLog.objects.create(
                    log=(
                        f"Stripe webhook: Membership {user_membership.membership.name} for user {user_membership.user} expired "
                        f"and deleted (stripe id {event_object.id})"
                    )
                )
                user_membership.delete()

            elif event_object.status == "active":
                if old_status == "incomplete":
                    # A new subscription was just activated
                    send_subscription_created_email(user_membership)
                # has it been cancelled in future?               
                if event_object.cancel_at:
                    subscription_end_date = datetime.fromtimestamp(event_object.cancel_at).replace(tzinfo=datetime_tz.utc)

                    if user_membership.end_date != subscription_end_date:
                        membership_end_date = get_first_of_next_month_from_timestamp(event_object.cancel_at)
                        ActivityLog.objects.create(
                            log=f"Membership {user_membership.membership.name} for user {user_membership.user} will cancel at {subscription_end_date}"
                        )
                        user_membership.subscription_end_date = subscription_end_date
                        user_membership.end_date = membership_end_date
                        user_membership.save()
                else:
                    if user_membership.end_date is not None:
                        ActivityLog.objects.create(
                            log=f"Stripe webhook: Scheduled cancellation for membership for user {user_membership.user} has been unset"
                        )
                        user_membership.end_date = None
                        user_membership.subscription_end_date = None
                        user_membership.save()
                
                # Has the price changed?
                
                # If user changes their membership type, it should cancel this subscription from the end of the period and create
                # a new membership and subscription that starts on the next month. User changes to memberships do trigger
                # a stripe subscription.updated event, but only to add the schedule
                
                # If the price of a membership type is changed, it creates a subscription schedule and price changes from the next subscription
                # The membership instance should stay the same on the UserMembership, but in case it's changed from the
                # Stripe account, we update membership and send emails to support to check
                price_id = event_object["items"].data[0].price.id
                logger.error("Price ID %s", price_id)
                logger.error("User membership Price ID %s", user_membership.membership.stripe_price_id)

                if price_id != user_membership.membership.stripe_price_id:
                    old_membership_name = user_membership.membership.name
                    membership = Membership.objects.get(stripe_price_id=price_id)
                    old_price_id = user_membership.membership.stripe_price_id
                    user_membership.membership = membership
                    user_membership.save()
                    ActivityLog.objects.create(
                        log=f"Stripe webhook: Membership ({old_membership_name}) for user {user_membership.user} has been changed to {membership.name}"
                    )
                    send_updated_membership_email_to_support(user_membership, membership.stripe_price_id, old_price_id)
                
                # reallocate bookings now we're done with updating the membership
                user_membership.reallocate_bookings()

            elif event_object.status == "past_due":
                send_subscription_past_due_email(event_object)

        elif event.type == "setup_intent.succeeded":
            # Is there a subscription with this setup intent?
            user_membership = UserMembership.objects.filter(
                pending_setup_intent=event_object.id,
                subscription_status="setup_pending"
            ).first()
            if user_membership:
                user_membership.subscription_status = "active"
                user_membership.pending_setup_intent = None
                user_membership.save()
                send_subscription_created_email(user_membership)
                user_membership.reallocate_bookings()
                ActivityLog.objects.create(
                    log=f"Stripe webhook: Membership for user {user_membership.user} updated from setup_pending "
                    f"to active"
                )

        elif event.type == "customer.source.expiring":
            # send user emails to remind to update
            # send email to customer (find by User.userprofile.stripe_customer_id; cc email from event_object)
            # include link to Memberships page
            send_payment_expiring_email(event_object)

        elif event.type == "invoice.upcoming":
            # send warning email to user that subscription will recur soon
            send_subscription_renewal_upcoming_email(event_object)

        elif event.type in ["invoice.finalized", "invoice.paid"]:
            # create/update StripeSubscriptionInvoice
            StripeSubscriptionInvoice.from_stripe_event(event_object)
        
        elif event.type == "product.updated":
            # get membership matching product (if exists)
            # check for active and make corresponding membership inactive if necessary
            # store stripe active status on model
            membership = Membership.objects.filter(stripe_product_id=event_object.id).first()
            if membership is not None and (
                membership.active != event_object.active 
                or membership.name != event_object.name 
                or membership.description != event_object.description
            ):
                membership.active = event_object.active
                membership.name = event_object.name
                membership.description = event_object.description
                membership.save()
                ActivityLog.objects.create(
                    log=f"Stripe webhook: Membership {event_object.id} updated"
                )

    except Exception as e:  # log anything else; return 400 so stripe tries again
        logger.error(str(e))
        send_failed_payment_emails(error=str(e), event_type=event.type, event_object=event_object)
        return HttpResponse(str(e), status=400)
    return HttpResponse(status=200)
