import logging

import stripe

from django.shortcuts import render, HttpResponseRedirect

from ..emails import send_failed_payment_emails
from ..exceptions import StripeProcessingError
from ..utils import (
    get_invoice_from_event_metadata, 
    StripeConnector, 
    process_completed_stripe_payment
)


logger = logging.getLogger(__name__)


def stripe_portal(request, customer_id):
    client = StripeConnector()
    return HttpResponseRedirect(client.customer_portal_url(customer_id))


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
                process_completed_stripe_payment(payment_intent, invoice, client.connected_account, request=request)
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
    updating = "updating" in request.GET
    
    if "payment_intent" in request.GET:
        intent_id = request.GET.get("payment_intent")
        subscribe_type = "payment"
    elif "setup_intent" in request.GET:
        intent_id = request.GET.get("setup_intent")
        subscribe_type = "setup"

    if subscribe_type is None:
        error = f"Could not identify payment or setup intent for subscription"
        logger.error(error)
        send_failed_payment_emails(
            payment_intent=None, 
            error=error
        )
        return render(request, 'stripe_payments/non_valid_payment.html')

    client = StripeConnector(request)
    
    # PaymentIntents can retrieve the subscription (via invoice), SetupIntents can't
    # All confirmation emails are handled in the webhook
    if subscribe_type == "payment":
        try:
            intent = client.get_payment_intent(intent_id)
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
            intent = client.get_setup_intent(intent_id)
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
