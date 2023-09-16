from unittest.mock import patch, Mock
import json
import pytest

from django.conf import settings
from django.contrib.sites.models import Site
from django.core import mail
from django.shortcuts import reverse

import stripe
from model_bakery import baker

from booking.models import Block, Booking, TicketBooking, Ticket, GiftVoucherType
from ..models import Invoice, Seller, StripePaymentIntent


pytestmark = pytest.mark.django_db


# StripePaymentCompleteView
complete_url = reverse("stripe_payments:stripe_payment_complete")
status_url = reverse("stripe_payments:stripe_payment_status", args=("mock-intent-id",))


def test_payment_complete_view(client):
    resp = client.get(complete_url + "?payment_intent=mock-intent-id")
    assert resp.status_code == 302
    assert resp.url == status_url


def test_payment_complete_view_no_payment_intent(client):
    resp = client.get(complete_url)
    assert resp.status_code == 302
    # redirects with a bad payment intent id, to raise failure messages there
    assert resp.url == reverse("stripe_payments:stripe_payment_status", args=("unk",))


@pytest.mark.usefixtures("seller", "send_all_studio_emails")
@patch("stripe_payments.views.stripe.PaymentIntent.retrieve")
def test_return_with_unknown_payment_intent(mock_payment_intent_retrieve, client):
    mock_payment_intent_retrieve.side_effect = stripe.error.InvalidRequestError(
        message="No payment intent found", param="payment_intent"
    )
    resp = client.get(reverse("stripe_payments:stripe_payment_status", args=("unk",)))
    assert resp.status_code == 200
    assert "Error Processing Payment" in resp.content.decode("utf-8")

    # No invoice matching PI value, send failed emails
    assert len(mail.outbox) == 1
    assert mail.outbox[0].subject == "WARNING: Something went wrong with a payment!"
    assert "No payment intent found" in mail.outbox[0].body


@pytest.mark.usefixtures("seller", "send_all_studio_emails")
@patch("stripe_payments.views.stripe.PaymentIntent")
def test_return_with_no_matching_invoice(
    mock_payment_intent, get_mock_payment_intent, client
):
    mock_payment_intent.retrieve.return_value = get_mock_payment_intent()
    resp = client.get(status_url)
    assert resp.status_code == 200
    assert "Error Processing Payment" in resp.content.decode("utf-8")

    # No invoice matching PI value, send failed emails
    assert len(mail.outbox) == 1
    assert mail.outbox[0].subject == "WARNING: Something went wrong with a payment!"
    assert "No invoice could be retrieved from succeeded payment intent mock-intent-id" in mail.outbox[0].body


@pytest.mark.usefixtures("seller", "send_all_studio_emails")
@patch("stripe_payments.views.stripe.PaymentIntent")
def test_return_with_matching_invoice_and_block(
    mock_payment_intent, get_mock_payment_intent, client, configured_user
):
    assert StripePaymentIntent.objects.exists() is False
    invoice = baker.make(
        Invoice, invoice_id="foo", amount=10,
        username=configured_user.email, stripe_payment_intent_id="mock-intent-id"
    )
    block = baker.make(Block, paid=False, invoice=invoice, user=configured_user)
    metadata = {
        "invoice_id": "foo",
        "invoice_signature": invoice.signature(),
        **invoice.items_metadata(),
    }
    mock_payment_intent.retrieve.return_value = get_mock_payment_intent(metadata=metadata)

    resp = client.get(status_url)
    assert resp.status_code == 200
    assert "Payment Processed" in resp.content.decode("utf-8")
    block.refresh_from_db()
    invoice.refresh_from_db()

    assert block.paid is True
    payment_intent_obj = StripePaymentIntent.objects.latest("id")
    assert payment_intent_obj.invoice == invoice

    assert len(mail.outbox) == 2
    assert mail.outbox[0].to == [settings.DEFAULT_STUDIO_EMAIL]
    assert mail.outbox[1].to == [configured_user.email]
    assert "Your payment has been processed" in mail.outbox[1].subject

@pytest.mark.usefixtures("seller", "send_all_studio_emails")
@patch("stripe_payments.views.stripe.PaymentIntent")
def test_return_with_matching_invoice_and_booking(
    mock_payment_intent, get_mock_payment_intent, client, configured_user
):
    assert StripePaymentIntent.objects.exists() is False
    invoice = baker.make(
        Invoice, invoice_id="foo", amount=10,
        username=configured_user.email, stripe_payment_intent_id="mock-intent-id"
    )
    booking = baker.make(Booking, paid=False, invoice=invoice, user=configured_user)
    metadata = {
        "invoice_id": "foo",
        "invoice_signature": invoice.signature(),
        **invoice.items_metadata(),
    }
    mock_payment_intent.retrieve.return_value = get_mock_payment_intent(metadata=metadata)
    resp = client.get(status_url)
    assert resp.status_code == 200
    assert "Payment Processed" in resp.content.decode("utf-8")
    booking.refresh_from_db()
    invoice.refresh_from_db()

    assert booking.paid is True
    assert invoice.paid is True
    payment_intent_obj = StripePaymentIntent.objects.latest("id")
    assert payment_intent_obj.invoice == invoice

    assert len(mail.outbox) == 2
    assert mail.outbox[0].to == [settings.DEFAULT_STUDIO_EMAIL]
    assert mail.outbox[1].to == [configured_user.email]
    assert "Your payment has been processed" in mail.outbox[1].subject


@patch("stripe_payments.views.stripe.PaymentIntent")
def test_return_with_matching_invoice_and_ticket_booking(
    mock_payment_intent, get_mock_payment_intent, client, configured_user, seller
):
    assert StripePaymentIntent.objects.exists() is False
    invoice = baker.make(
        Invoice, invoice_id="foo", amount=10,
        username=configured_user.email, stripe_payment_intent_id="mock-intent-id"
    )
    ticket_booking = baker.make(
        TicketBooking, paid=False, invoice=invoice, user=configured_user,
    )
    baker.make(Ticket, ticket_booking=ticket_booking)
    metadata = {
        "invoice_id": "foo",
        "invoice_signature": invoice.signature(),
        **invoice.items_metadata(),
    }
    mock_payment_intent.retrieve.return_value = get_mock_payment_intent(metadata=metadata)
    resp = client.get(status_url)
    assert resp.status_code == 200
    assert "Payment Processed" in resp.content.decode("utf-8")
    ticket_booking.refresh_from_db()
    invoice.refresh_from_db()

    assert ticket_booking.paid is True
    assert invoice.paid is True
    payment_intent_obj = StripePaymentIntent.objects.latest("id")
    assert payment_intent_obj.invoice == invoice

    assert len(mail.outbox) == 2
    assert mail.outbox[0].to == [settings.DEFAULT_STUDIO_EMAIL]
    assert mail.outbox[1].to == [configured_user.email]
    assert "Your payment has been processed" in mail.outbox[1].subject


@pytest.mark.usefixtures("seller", "send_all_studio_emails")

@patch("stripe_payments.views.stripe.PaymentIntent")
def test_return_with_matching_invoice_and_gift_voucher(mock_payment_intent, get_mock_payment_intent, client, configured_user, block_gift_voucher):
    assert StripePaymentIntent.objects.exists() is False
    invoice = baker.make(
        Invoice, invoice_id="foo", amount=10,
        username=configured_user.email, stripe_payment_intent_id="mock-intent-id"
    )
    block_gift_voucher.invoice = invoice
    block_gift_voucher.purchaser_email = configured_user.email
    block_gift_voucher.save()

    metadata = {
        "invoice_id": "foo",
        "invoice_signature": invoice.signature(),
        **invoice.items_metadata(),
    }
    mock_payment_intent.retrieve.return_value = get_mock_payment_intent(metadata=metadata)

    resp = client.get(status_url)
    assert resp.status_code == 200
    assert "Payment Processed" in resp.content.decode("utf-8")
    block_gift_voucher.refresh_from_db()
    invoice.refresh_from_db()

    assert block_gift_voucher.activated is True

    payment_intent_obj = StripePaymentIntent.objects.latest("id")
    assert payment_intent_obj.invoice == invoice

    assert len(mail.outbox) == 3
    assert mail.outbox[0].to == [settings.DEFAULT_STUDIO_EMAIL]
    assert mail.outbox[1].to == [configured_user.email]
    assert "Your payment has been processed" in mail.outbox[1].subject
    assert mail.outbox[2].to == [configured_user.email]
    assert "Gift Voucher" in mail.outbox[2].subject


@pytest.mark.usefixtures("seller", "send_all_studio_emails")
@patch("stripe_payments.views.stripe.PaymentIntent")
def test_return_with_matching_invoice_and_gift_voucher_anon_user(
    mock_payment_intent, get_mock_payment_intent, client, block_gift_voucher
):
    assert StripePaymentIntent.objects.exists() is False
    invoice = baker.make(
        Invoice, invoice_id="foo", amount=10,
        username="", stripe_payment_intent_id="mock-intent-id"
    )
    block_gift_voucher.purchaser_email = "anon@test.com"
    block_gift_voucher.invoice = invoice
    block_gift_voucher.save()
    metadata = {
        "invoice_id": "foo",
        "invoice_signature": invoice.signature(),
        **invoice.items_metadata(),
    }
    mock_payment_intent.retrieve.return_value = get_mock_payment_intent(metadata=metadata)

    resp = client.get(status_url)
    assert resp.status_code == 200
    assert "Payment Processed" in resp.content.decode("utf-8")
    block_gift_voucher.refresh_from_db()
    invoice.refresh_from_db()

    assert block_gift_voucher.activated is True

    # invoice username added from payment intent
    assert invoice.username == "stripe-payer@test.com"
    payment_intent_obj = StripePaymentIntent.objects.latest("id")
    assert payment_intent_obj.invoice == invoice

    assert len(mail.outbox) == 3
    assert mail.outbox[0].to == [settings.DEFAULT_STUDIO_EMAIL]
    # payment email goes to invoice email
    assert mail.outbox[1].to == ["stripe-payer@test.com"]
    assert "Your payment has been processed" in mail.outbox[1].subject
    # gift voucher goes to purchaser emailon voucher
    assert mail.outbox[2].to == ["anon@test.com"]
    assert "Gift Voucher" in mail.outbox[2].subject


@pytest.mark.usefixtures("seller", "send_all_studio_emails")
@patch("stripe_payments.views.stripe.PaymentIntent")
def test_return_with_invalid_invoice(mock_payment_intent, get_mock_payment_intent, client, configured_user):
    invoice = baker.make(
        Invoice, invoice_id="", amount=10,
        username=configured_user.email, stripe_payment_intent_id="mock-intent-id"
    )
    baker.make(Booking, paid=False, invoice=invoice, user=configured_user)
    metadata = {
        "invoice_id": "unk",
        "invoice_signature": invoice.signature(),
        **invoice.items_metadata(),
    }
    mock_payment_intent.retrieve.return_value = get_mock_payment_intent(metadata=metadata)
    resp = client.get(status_url)
    assert "Error Processing Payment" in resp.content.decode("utf-8")
    assert invoice.paid is False
    # send failed emails
    assert len(mail.outbox) == 1
    assert mail.outbox[0].subject == "WARNING: Something went wrong with a payment!"
    assert "No invoice could be retrieved from succeeded payment intent mock-intent-id" in mail.outbox[0].body


@pytest.mark.usefixtures("seller", "send_all_studio_emails")
@patch("stripe_payments.views.stripe.PaymentIntent")
def test_return_with_matching_invoice_multiple_bookingss(mock_payment_intent, get_mock_payment_intent, client, configured_user):
    invoice = baker.make(
        Invoice, invoice_id="foo", amount=10,
        username=configured_user.email, stripe_payment_intent_id="mock-intent-id"
    )
    booking1 = baker.make(Booking, paid=False, invoice=invoice, user=configured_user)
    booking2 = baker.make(Booking, paid=False, invoice=invoice, user=configured_user)

    metadata = {
        "invoice_id": "foo",
        "invoice_signature": invoice.signature(),
        **invoice.items_metadata(),
    }
    mock_payment_intent.retrieve.return_value = get_mock_payment_intent(metadata=metadata)
    resp = client.get(status_url)
    assert resp.status_code == 200
    assert "Payment Processed" in resp.content.decode("utf-8")
    booking1.refresh_from_db()
    booking2.refresh_from_db()
    invoice.refresh_from_db()

    assert booking1.paid is True
    assert booking2.paid is True
    assert invoice.paid is True


@pytest.mark.usefixtures("seller", "send_all_studio_emails")
@patch("stripe_payments.views.stripe.PaymentIntent")
def test_return_with_matching_invoice_invalid_amount(mock_payment_intent, get_mock_payment_intent, client, configured_user):
    invoice = baker.make(
        Invoice, invoice_id="foo", username=configured_user.email, amount=50,
        stripe_payment_intent_id="mock-intent-id"
    )
    baker.make(Booking, paid=False, invoice=invoice, user=configured_user)
    metadata = {
        "invoice_id": "foo",
        "invoice_signature": invoice.signature(),
        **invoice.items_metadata(),
    }
    mock_payment_intent.retrieve.return_value = get_mock_payment_intent(metadata=metadata)
    resp = client.get(status_url)
    assert invoice.paid is False
    assert "Error Processing Payment" in resp.content.decode("utf-8")


@pytest.mark.usefixtures("seller", "send_all_studio_emails")
@patch("stripe_payments.views.stripe.PaymentIntent")
def test_return_with_matching_invoice_invalid_signature(mock_payment_intent, get_mock_payment_intent, client, configured_user):
    invoice = baker.make(
        Invoice, invoice_id="foo", username=configured_user.email, amount=50,
        stripe_payment_intent_id="mock-intent-id"
    )
    baker.make(Booking, paid=False, invoice=invoice, user=configured_user)
    metadata = {
        "invoice_id": "foo",
        "invoice_signature": "foo",
        **invoice.items_metadata(),
    }
    mock_payment_intent.retrieve.return_value = get_mock_payment_intent(metadata=metadata)
    resp = client.get(status_url)
    assert invoice.paid is False
    assert "Error Processing Payment" in resp.content.decode("utf-8")


@pytest.mark.usefixtures("seller", "send_all_studio_emails")
@patch("stripe_payments.views.stripe.PaymentIntent")
def test_return_with_matching_invoice_block_already_processed(mock_payment_intent, get_mock_payment_intent, client, configured_user):
    invoice = baker.make(
        Invoice, invoice_id="foo", amount=10,
        username=configured_user.email, stripe_payment_intent_id="mock-intent-id",
        paid=True
    )
    baker.make(Booking, invoice=invoice, user=configured_user, paid=True)
    metadata = {
        "invoice_id": "foo",
        "invoice_signature": "foo",
        **invoice.items_metadata(),
    }
    mock_payment_intent.retrieve.return_value = get_mock_payment_intent(metadata=metadata)
    resp = client.get(status_url)

    assert resp.status_code == 200
    assert "Payment Processed" in resp.content.decode("utf-8")
    # already processed, no emails sent
    assert len(mail.outbox) == 0


@pytest.mark.usefixtures("seller", "send_all_studio_emails")
@patch("stripe_payments.views.stripe.PaymentIntent")
def test_return_with_failed_payment_intent(mock_payment_intent, get_mock_payment_intent, client, configured_user):
    invoice = baker.make(
        Invoice, invoice_id="foo", username=configured_user.email, amount=50,
        stripe_payment_intent_id="mock-intent-id"
    )
    baker.make(Booking, paid=False, invoice=invoice, user=configured_user)
    metadata = {
        "invoice_id": "foo",
        "invoice_signature": invoice.signature(),
        **invoice.items_metadata(),
    }
    mock_payment_intent.retrieve.return_value = get_mock_payment_intent(metadata=metadata, status="failed")
    resp = client.get(status_url)
    assert invoice.paid is False
    assert "Error Processing Payment" in resp.content.decode("utf-8")


# stripe_webhook view
webhook_url = reverse("stripe_payments:stripe_webhook")


@patch("stripe_payments.views.stripe.Webhook")
def test_webhook_with_matching_invoice_and_block(
    mock_webhook, get_mock_webhook_event, client, invoice, configured_user
):
    assert StripePaymentIntent.objects.exists() is False
    block = baker.make(Block, paid=True, block_type__cost=10, invoice=invoice)
    metadata = {
        "invoice_id": "foo",
        "invoice_signature": invoice.signature(),
        **invoice.items_metadata(),
    }
    mock_webhook.construct_event.return_value = get_mock_webhook_event(metadata=metadata)

    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200
    block.refresh_from_db()
    invoice.refresh_from_db()

    assert block.paid is True
    assert invoice.paid is True
    payment_intent_obj = StripePaymentIntent.objects.latest("id")
    assert payment_intent_obj.invoice == invoice

    assert len(mail.outbox) == 2
    assert mail.outbox[0].to == [settings.DEFAULT_STUDIO_EMAIL]
    assert mail.outbox[1].to == [configured_user.email]
    assert "Your payment has been processed" in mail.outbox[1].subject


@patch("stripe_payments.views.stripe.Webhook")
def test_webhook_with_refunded_invoice_and_block(
    mock_webhook, get_mock_webhook_event, client, invoice, configured_user
):
    assert StripePaymentIntent.objects.exists() is False
    invoice.paid = True
    invoice.save()
    block = baker.make(Block, paid=True, block_type__cost=10, invoice=invoice)
    metadata = {
        "invoice_id": "foo",
        "invoice_signature": invoice.signature(),
        **invoice.items_metadata(),
    }
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="payment_intent.refunded",
        metadata=metadata
    )

    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200
    block.refresh_from_db()
    invoice.refresh_from_db()

    # still paid, we don't do any updates to refunded items
    assert block.paid is True
    assert invoice.paid is True

    # email to support only
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [settings.SUPPORT_EMAIL]
    assert "WARNING: Payment refund processed" in mail.outbox[0].subject


@patch("stripe_payments.views.stripe.Webhook")
def test_webhook_already_processed(
    mock_webhook, get_mock_webhook_event, client, invoice
):
    baker.make(Block, paid=True, block_type__cost=10, invoice=invoice)
    invoice.paid = True
    invoice.save()
    metadata = {
        "invoice_id": "foo",
        "invoice_signature": invoice.signature(),
        **invoice.items_metadata(),
    }
    mock_webhook.construct_event.return_value = get_mock_webhook_event(metadata=metadata)
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")

    assert resp.status_code == 200
    # already processed, no emails sent
    assert len(mail.outbox) == 0


@patch("stripe_payments.views.stripe.Webhook")
def test_webhook_exceptions(mock_webhook, client):
    mock_webhook.construct_event.side_effect = stripe.error.SignatureVerificationError("", "foo")
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    # stripe verification error returns 400 so stripe will try again
    assert resp.status_code == 400

    mock_webhook.construct_event.side_effect = ValueError
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    # value error means payload is invalid; returns 400 so stripe will try again
    assert resp.status_code == 400


@patch("stripe_payments.views.stripe.Webhook")
def test_webhook_exception_invalid_invoice_signature(
    mock_webhook, get_mock_webhook_event, client, invoice
):
    block = baker.make(Block, paid=False, block_type__cost=10, invoice=invoice)
    # invalid invoice signature
    metadata = {
        "invoice_id": "bar",
        **invoice.items_metadata(),
    }
    mock_webhook.construct_event.return_value = get_mock_webhook_event(metadata=metadata)
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200

    # invoice and block is still unpaid
    assert block.paid is False
    assert invoice.paid is False

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [settings.SUPPORT_EMAIL]
    assert "WARNING: Something went wrong with a payment!" in mail.outbox[0].subject
    assert "Error: Error processing stripe payment intent mock-intent-id; could not find invoice" \
            in mail.outbox[0].body


@patch("stripe_payments.views.stripe.Webhook")
def test_webhook_exception_retrieving_invoice(
    mock_webhook, get_mock_webhook_event, client, invoice
):
    block = baker.make(Block, paid=False, block_type__cost=10, invoice=invoice)

    # invalid invoice signature
    metadata = {
        "invoice_id": "foo",
        "invoice_signature": "foo",
        **invoice.items_metadata(),
    }
    mock_webhook.construct_event.return_value = get_mock_webhook_event(metadata=metadata)
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200

    # invoice and block is still unpaid
    assert block.paid is False
    assert invoice.paid is False

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [settings.SUPPORT_EMAIL]
    assert "WARNING: Something went wrong with a payment!" in mail.outbox[0].subject
    assert "Error: Could not verify invoice signature: payment intent mock-intent-id; invoice id foo" \
            in mail.outbox[0].body


@patch("stripe_payments.views.stripe.Webhook")
def test_webhook_exception_no_invoice(
    mock_webhook, get_mock_webhook_event, client, invoice
):
    block = baker.make(Block, paid=False, block_type__cost=10, invoice=invoice)

    # invalid invoice signature
    metadata = invoice.items_metadata()
    mock_webhook.construct_event.return_value = get_mock_webhook_event(metadata=metadata)
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200

    # invoice and block is still unpaid
    assert block.paid is False
    assert invoice.paid is False

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [settings.SUPPORT_EMAIL]
    assert "WARNING: Something went wrong with a payment!" in mail.outbox[0].subject
    assert "Error: Error processing stripe payment intent mock-intent-id; no invoice id" \
            in mail.outbox[0].body


@patch("stripe_payments.views.stripe.Webhook")
def test_webhook_payment_failed(
    mock_webhook, get_mock_webhook_event, client, invoice
):
    block = baker.make(Block, paid=False, block_type__cost=10, invoice=invoice)
    metadata = {
        "invoice_id": "foo",
        "invoice_signature": invoice.signature(),
        **invoice.items_metadata(),
    }
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="payment_intent.payment_failed", metadata=metadata
    )
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200
    block.refresh_from_db()
    invoice.refresh_from_db()
    # invoice and block is still unpaid
    assert block.paid is False
    assert invoice.paid is False

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [settings.SUPPORT_EMAIL]
    assert "WARNING: Something went wrong with a payment!" in mail.outbox[0].subject
    assert "Failed payment intent id: mock-intent-id; invoice id foo" in mail.outbox[0].body


@patch("stripe_payments.views.stripe.Webhook")
@patch("stripe_payments.views.stripe.Account")
def test_webhook_authorized_account(
    mock_account, mock_webhook, get_mock_webhook_event, client
):
    # mock the seller that should have been created in the StripeAuthorizeCallbackView
    baker.make(Seller, stripe_user_id="stripe-account-1")
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="account.application.authorized"
    )
    mock_account.list.return_value = Mock(data=[Mock(id="stripe-account-1")])

    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200


@patch("stripe_payments.views.stripe.Webhook")
@patch("stripe_payments.views.stripe.Account")
def test_webhook_authorized_account_no_seller(
    mock_account, mock_webhook, get_mock_webhook_event, client
):
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="account.application.authorized"
    )
    mock_account.list.return_value = Mock(data=[Mock(id="stripe-account-1")])

    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 400


@patch("stripe_payments.views.stripe.Webhook")
@patch("stripe_payments.views.stripe.Account")
def test_webhook_authorized_account_mismatched_seller(
    mock_account, mock_webhook, get_mock_webhook_event, client, invoice
):     
    baker.make(Block, paid=True, block_type__cost=10, invoice=invoice)
    metadata = {
        "invoice_id": "foo",
        "invoice_signature": invoice.signature(),
        **invoice.items_metadata(),
    }
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        metadata=metadata, seller_id="other-seller-id"
    )

    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200
    assert resp.content.decode() == "Ignored: Mismatched seller account"


@patch("stripe_payments.views.stripe.Webhook")
@patch("stripe_payments.views.stripe.Account")
def test_webhook_deauthorized_account(
    mock_account, mock_webhook, get_mock_webhook_event, seller, client
):
    assert seller.site == Site.objects.get_current()
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="account.application.deauthorized"
    )
    mock_account.list.return_value = Mock(data=[])

    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200
    seller.refresh_from_db()
    assert seller.site is None
