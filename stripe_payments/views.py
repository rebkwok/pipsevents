from datetime import datetime, timedelta
from decimal import Decimal
import json
import logging

import stripe

from django.conf import settings
from django.contrib.auth.models import User
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.shortcuts import render, HttpResponse
from django.urls import reverse

from activitylog.models import ActivityLog
from booking.models import UserMembership, Membership
from .emails import send_failed_payment_emails, send_processed_refund_emails
from .exceptions import StripeProcessingError
from .models import Seller, StripePaymentIntent
from .utils import get_invoice_from_event_metadata, check_stripe_data, process_invoice_items, StripeConnector, get_first_of_next_month_from_timestamp

logger = logging.getLogger(__name__)


def _process_completed_stripe_payment(payment_intent, invoice, seller=None, request=None):
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
    # For setup intents, the webhook needs to handle sending a confirmation email to users
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
            # create Invoice and StripePaymentIntent?
            # _process_completed_stripe_subscription(intent, client.connected_account, subscribe_type=subscribe_type, request=request)
            return render(request, 'stripe_payments/valid_subscription_setup.html', {"payment": True})
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
        return render(request, 'stripe_payments/valid_subscription_setup.html', {"setup": True})
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

        # check event type
        # processing already:
        # - payment_intent.succeeded
        # - payment_intent.payment_failed (update to not email for every card error)
        # - payment_intent.processing
        # - account.application.authorized
        # - account.application.deauthorized
        # charge.refund.updated
        # charge.refunded

        # webhook also listens to:
        # customer.subscription.created - find User, create UserMembership, set status to subscription status
        # customer.subscription.deleted - canceled subscription, update UserMembership status
        # customer.subscription.updated 
        # - will be sent when subscription changes from incomplete to active
        # - confirm when subscription starts (
        #   check latest invoice? null for active subscriptions that don't start until next billing period
        #   sub start_date will be before billing_cycle_anchor if sub was backdated
        #   set start date on UserMmebership to future date
        # - also when subscription changes to past_due because an automatic payment failed
        # if past_due - send email to update payment method plus warning; allow 2 or 3 days past 1st of month and then
        # cancel subscription/membership. 

        # customer.source.expiring - if customer has a subscription, send email about expiring card and prompt payment method update

        # We need to handle unpaid invoices for subscriptions where payment methods fail, and send an email
        # with a link to update payment method
        # we don't need all of these
        # invoice.paid - check this to ensure subscription continues and create a new Invoice object
        # invoice.payment_failed - check attempt_count?
        # https://docs.stripe.com/billing/revenue-recovery/smart-retries#invoice-payment-failed-webhook
        # invoice.upcoming - Sent a few days prior to the renewal of the subscription; email user?
        
        # handled in payment_complete/subscribe_complete return_url, needs handling in webhook
        # payment_intent.processing

        # subscription_schedule
        # No events
        # we update schedules for membership price changes (by admin) and user cancel request
        # handle messages and updates when we do these

        # try to get the invoice from the event metadata; if we can get a valid invoice, it's an
        # event related to a payment for an immediate checkout (booking, block, ticket_booking) and not for a subscription
        # Handle the payment intent and refund events
        # This raises an error if there is an invoice id in the metadata but no associated local Invoice object in the db
        invoice = get_invoice_from_event_metadata(event_object, raise_immediately=True)
        if invoice is not None:
            error = None
            if event.type == "payment_intent.succeeded":
                _process_completed_stripe_payment(event_object, invoice, request=request)
            elif event.type == "payment_intent.processing":
                error = f"Payment intent {event_object.id} still processing."
            elif event.type in ["charge.refund.updated", "charge.refunded"]:
                # No automatic refunds from the system; if a payment is refunded, just send the
                # support emails for checking
                send_processed_refund_emails(invoice)
            elif event.type == "payment_intent.payment_failed":
                error = f"Failed payment intent id: {event_object.id}; invoice id {invoice.invoice_id}; " \
                        f"error {event_object.last_payment_error}"
            if error:
                logger.error(error)
                send_failed_payment_emails(error=error)
                return HttpResponse(error, status=200)
        else:
            if event.type == "customer.subscription.created":
                # calculate membership start from subscription start timestamp (should be 25th month, membership
                # start is 1st of the next month)
                membership_start = get_first_of_next_month_from_timestamp(event_object.start_date)
                user = User.objects.get(userprofile__stripe_customer_id=event_object.customer)
                UserMembership.objects.create(
                    user=user,
                    membership=Membership.objects.get(stripe_price_id=event_object["items"].data[0].price.id),
                    subscription_id=event_object.id,
                    subscription_status=event_object.status,
                    start_date=membership_start
                )
                ActivityLog.objects.create(
                    log=f"Membership {Membership.name} set up for {user} (stripe subscription id {event_object.id}, status {event_object.status})"
                )
            # handle all the other things related to subscriptions (including payment intents and refunds)
            ...
            # payment_intent and charge
            # fetch invoice using id from event_object.invoice (if not None), with expand=['subscription']
            # invoice.subscription will have subscription details, look up UserMembership
            #
            # customer.source.expiring 
            # send email to customer (find by User.userprofile.stripe_customer_id; cc email from event_object)
            #
            # customer.subscription.created/updated/deleted
            # update UserMembership with status, start and end dates if necessary
            #
            # invoice.paid/payment_failed/upcoming
            
    except Exception as e:  # log anything else
        logger.error(e)
        send_failed_payment_emails(error=e)
        return HttpResponse(str(e), status=200)
    return HttpResponse(status=200)
