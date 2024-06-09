from datetime import datetime
from datetime import timezone as datetime_tz
from decimal import Decimal
import json
import logging

import stripe

from django.conf import settings
from django.contrib.auth.models import User
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.shortcuts import render, HttpResponse, HttpResponseRedirect
from django.urls import reverse

from activitylog.models import ActivityLog
from booking.models import UserMembership, Membership
from .emails import (
    send_failed_payment_emails, 
    send_processed_refund_emails, 
    send_updated_membership_email_to_support,
    send_payment_expiring_email,
    send_subscription_past_due_email,
    send_subscription_renewal_upcoming_email,
    send_subscription_created_email
)
from .exceptions import StripeProcessingError
from .models import Seller, StripePaymentIntent, StripeSubscriptionInvoice
from .utils import (
    get_invoice_from_event_metadata, 
    check_stripe_data, 
    process_invoice_items, 
    StripeConnector, 
    get_first_of_next_month_from_timestamp,
    get_utcdate_from_timestamp
)


logger = logging.getLogger(__name__)


def stripe_portal(request, customer_id):
    client = StripeConnector()
    return HttpResponseRedirect(client.customer_portal_url(customer_id))


def _process_completed_stripe_payment(payment_intent, invoice, seller=None, request=None):
    if invoice is None:
        # no invoice == subscription payment (handled with subscription events) or oob payment (direct from stripe)
        # nothing to do
        return
    if not invoice.paid:
        logger.info("Updating items to paid for invoice %s", invoice.invoice_id)
        check_stripe_data(payment_intent, invoice)
        logger.info("Stripe check OK")
        process_invoice_items(invoice, payment_method="Stripe", request=request)
        # update/create the django model PaymentIntent - this is just for records
        StripePaymentIntent.update_or_create_payment_intent_instance(payment_intent, invoice, seller)
    else:
        logger.info(
            "Payment Intents signal received for invoice %s; already processed", invoice.invoice_id
        )


def stripe_payment_complete(request):
    payment_intent_id = request.GET.get("payment_intent", "unk")
    client = StripeConnector(request)
    try:
        payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id, stripe_account=client.connected_account_id)
    except stripe.error.InvalidRequestError as e:
        error = f"Error retrieving Stripe payment intent: {e}"
        logger.error(e)
        send_failed_payment_emails(
            payment_intent={"id": payment_intent_id, "status": "Not found"}, 
            error=error
        )
        return render(request, 'stripe_payments/non_valid_payment.html')
    
    failed = False
    if payment_intent.status == "succeeded":
        invoice = get_invoice_from_event_metadata(payment_intent, raise_immediately=False)
        if invoice is not None:
            try:
                _process_completed_stripe_payment(payment_intent, invoice, client.connected_account, request=request)
            except StripeProcessingError as e:
                error = f"Error processing Stripe payment: {str(e)}"
                logger.error(e)
                failed = True
        else:
            # No invoice retrieved, fail
            failed = True
            error = f"No invoice could be retrieved from succeeded payment intent {payment_intent.id}"
            logger.error(error)
    elif payment_intent.status == "processing":
        error = f"Payment intent {payment_intent.id} still processing."
        logger.error(error)
        send_failed_payment_emails(payment_intent=payment_intent, error=error)
        return render(request, 'stripe_payments/processing_payment.html')
    else:
        failed = True
        error = f"Payment intent id {payment_intent.id} status: {payment_intent.status}"
        logger.error(error)
    payment_intent.metadata.pop("invoice_id", None)
    payment_intent.metadata.pop("invoice_signature", None)
    if not failed:
        context = {
            "cart_items": invoice.items_dict().values(),
            "item_types": invoice.item_types(),
            "total_charged": invoice.amount,
        }
        return render(request, 'stripe_payments/valid_payment.html', context)
    else:
        send_failed_payment_emails(payment_intent=payment_intent, error=error)
        return render(request, 'stripe_payments/non_valid_payment.html')


def stripe_subscribe_complete(request):
    subscribe_type = None
    intent_id = request.GET.get("payment_intent")
    updating = request.GET.get("updating", False)
    if intent_id:
        subscribe_type = "payment"
    else:
        intent_id = request.GET.get("setup_intent")
        subscribe_type = "setup"

    if subscribe_type is None:
        error = f"Could not identify payment or setup intent for subscription"
        logger.error(error)
        return render(request, 'stripe_payments/non_valid_payment.html')

    client = StripeConnector(request)
    
    # PaymentIntents can retrieve the subscription (via invoice), SetupIntents can't
    # All confirmation emails are handled in the webhook
    if subscribe_type == "payment":
        try:
            intent = stripe.PaymentIntent.retrieve(intent_id, stripe_account=client.connected_account_id)
        except stripe.error.InvalidRequestError as e:
            error = f"Error retrieving Stripe payment intent: {e}"
            logger.error(e)
            send_failed_payment_emails(
                payment_intent={"id": intent_id, "status": "Not found"}, 
                error=error
            )
            return render(request, 'stripe_payments/non_valid_payment.html')
    else:
        assert subscribe_type == "setup"
        try:
            intent = stripe.SetupIntent.retrieve(intent_id, stripe_account=client.connected_account_id)
        except stripe.error.InvalidRequestError as e:
            error = f"Error retrieving Stripe setup intent: {e}"
            logger.error(e)
            send_failed_payment_emails(
                payment_intent={"id": intent_id, "status": "Not found"}, 
                error=error
            )
            return render(request, 'stripe_payments/non_valid_payment.html')
    
    if subscribe_type == "payment":
        if intent.status == "succeeded":
            return render(request, 'stripe_payments/valid_subscription_setup.html', {"payment": True, "updating": updating})
        elif intent.status == "processing":
            error = f"Payment intent {intent.id} still processing."
            logger.error(error)
            send_failed_payment_emails(payment_intent=intent, error=error)
            return render(request, 'stripe_payments/processing_payment.html')
        else:
            error = f"Payment intent id {intent.id} status: {intent.status}"
            logger.error(error)
            send_failed_payment_emails(payment_intent=intent, error=error)
            return render(request, 'stripe_payments/non_valid_payment.html')
    
    assert subscribe_type == "setup"
    if intent.status == "succeeded":
        # _process_completed_stripe_subscription(intent, client.connected_account, subscribe_type=subscribe_type, request=request)
        return render(request, 'stripe_payments/valid_subscription_setup.html', {"setup": True, "updating": updating})
    elif intent.status == "processing":
        error = f"Setup intent {intent.id} still processing."
        logger.error(error)
        send_failed_payment_emails(payment_intent=intent, error=error)
        return render(request, 'stripe_payments/processing_payment.html')
    else:
        error = f"Setup intent id {intent.id} status: {intent.status}"
        logger.error(error)
        send_failed_payment_emails(payment_intent=intent, error=error)
        return render(request, 'stripe_payments/non_valid_payment.html')


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
                _process_completed_stripe_payment(event_object, invoice, request=request)
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
            user_membership = UserMembership.objects.create(
                user=user,
                membership=Membership.objects.get(stripe_price_id=event_object["items"].data[0].price.id),
                start_date=membership_start,
                subscription_id=event_object.id,
                subscription_status=event_object.status,
                subscription_start_date=get_utcdate_from_timestamp(event_object.start_date),
                subscription_billing_cycle_anchor=get_utcdate_from_timestamp(event_object.billing_cycle_anchor),
            )
            ActivityLog.objects.create(
                log=f"Stripe webhook: Membership {user_membership.membership.name} set up for {user} (stripe subscription id {event_object.id}, status {event_object.status})"
            )
            send_subscription_created_email(user_membership)
    
        elif event.type == "customer.subscription.deleted":
            # Users can only cancel from end of month, which sends a subscription_update. 
            # Admin users might cancel a subscription immediately from stripe
            # This event is sent when the cancellation actually happens (i.e. not on user demand)
            # Set the subscription_status to cancelled
            user_membership = UserMembership.objects.get(subscription_id=event_object.id)
            # the end date for the membership is the stripe subscription end; cancelled at will be the 25th
            # the actual membership ends at the end of the month
            user_membership.subscription_status = event_object.status
            user_membership.subscription_end_date = get_utcdate_from_timestamp(event_object.canceled_at)
            user_membership.end_date = user_membership.calculate_membership_end_date()
            user_membership.save()
            ActivityLog.objects.create(
                log=f"Stripe webhook: Membership {user_membership.membership.name} for {user_membership.user} (stripe subscription id {event_object.id}, cancelled on {user_membership.subscription_end_date})"
            )
        elif event.type == "customer.subscription.updated":
            user_membership = UserMembership.objects.get(subscription_id=event_object.id)
            status_changed = user_membership.subscription_status != event_object.status
            if status_changed:
                user_membership.subscription_status = event_object.status
                ActivityLog.objects.create(
                    log=f"Stripe webhook: Membership for user {user_membership.user} updated from {user_membership.subscription_status} "
                    f"to {event_object.status}"
                )
            if event_object.status == "active":
                # has it been cancelled in future?               
                if event_object.cancel_at:
                    end_date = datetime.fromtimestamp(event_object.cancel_at)
                    if user_membership.end_date != end_date:
                        ActivityLog.objects.create(
                            log=f"Membership for user {user_membership.user} will cancel at {end_date}"
                        )
                        user_membership.end_date = end_date
                else:
                    if user_membership.end_date is not None:
                        ActivityLog.objects.create(
                            log=f"Stripe webhook: Scheduled cancellation for membership for user {user_membership.user} has been unset"
                        )
                        user_membership.end_date = None
                
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
                    membership = Membership.objects.get(stripe_price_id=price_id)
                    old_price_id = user_membership.membership.stripe_price_id
                    ActivityLog.objects.create(
                        log=f"Stripe webhook: Membership ({user_membership.membership.name}) for user {user_membership.user} has been changed to {membership.name}"
                    )
                    send_updated_membership_email_to_support(user_membership, membership.stripe_price_id, old_price_id)
            user_membership.save()
            if event_object.status == "past_due":
                # TODO email user with link to subscription status page for updating payment
                send_subscription_past_due_email(event_object)

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
        
    except Exception as e:  # log anything else; return 400 so stripe tries again
        logger.error(e)
        send_failed_payment_emails(error=e, event_type=event.type, event_object=event_object)
        return HttpResponse(str(e), status=400)
    return HttpResponse(status=200)
