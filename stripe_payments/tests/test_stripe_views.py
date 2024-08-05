from unittest.mock import patch
import pytest

from django.conf import settings
from django.core import mail
from django.shortcuts import reverse

import stripe
from model_bakery import baker

from conftest import get_mock_payment_intent, get_mock_setup_intent
from booking.models import Block, Booking, TicketBooking, Ticket
from ..models import Invoice, StripePaymentIntent
from .mock_connector import MockConnector

pytestmark = pytest.mark.django_db


# StripePaymentCompleteView
complete_url = reverse("stripe_payments:stripe_payment_complete")


@patch("stripe_payments.views.views.StripeConnector", MockConnector)
@pytest.mark.usefixtures("seller", "send_all_studio_emails")
@patch("stripe_payments.views.views.stripe.PaymentIntent.retrieve")
def test_return_with_unknown_payment_intent(mock_payment_intent_retrieve, client):
    mock_payment_intent_retrieve.side_effect = stripe.error.InvalidRequestError(
        message="No payment intent found", param="payment_intent"
    )
    resp = client.get(complete_url)
    assert resp.status_code == 200
    assert "Error Processing Payment" in resp.content.decode("utf-8")

    # No invoice matching PI value, send failed emails
    assert len(mail.outbox) == 1
    assert mail.outbox[0].subject == "WARNING: Something went wrong processing a stripe event!"
    assert "No payment intent found" in mail.outbox[0].body


@patch("stripe_payments.views.views.StripeConnector", MockConnector)
@pytest.mark.usefixtures("seller", "send_all_studio_emails")
@patch("stripe_payments.views.views.stripe.PaymentIntent")
def test_return_with_no_matching_invoice(
    mock_payment_intent, client
):
    mock_payment_intent.retrieve.return_value = get_mock_payment_intent()
    resp = client.get(complete_url)
    assert resp.status_code == 200
    assert "Error Processing Payment" in resp.content.decode("utf-8")

    # No invoice matching PI value, send failed emails
    assert len(mail.outbox) == 1
    assert mail.outbox[0].subject == "WARNING: Something went wrong processing a stripe event!"
    assert "No invoice could be retrieved from succeeded payment intent mock-intent-id" in mail.outbox[0].body


@pytest.mark.usefixtures("seller", "send_all_studio_emails")
@patch("stripe_payments.views.views.stripe.PaymentIntent")
def test_return_with_matching_invoice_and_block(
    mock_payment_intent, client, configured_user
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

    resp = client.get(complete_url)
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
@patch("stripe_payments.views.views.stripe.PaymentIntent")
def test_return_with_matching_invoice_and_booking(
    mock_payment_intent, client, configured_user
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
    resp = client.get(complete_url)
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


@patch("stripe_payments.views.views.stripe.PaymentIntent")
def test_return_with_matching_invoice_and_ticket_booking(
    mock_payment_intent, client, configured_user, seller
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
    resp = client.get(complete_url)
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
@patch("stripe_payments.views.views.stripe.PaymentIntent")
def test_return_with_matching_invoice_and_gift_voucher(mock_payment_intent, client, configured_user, block_gift_voucher):
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

    resp = client.get(complete_url)
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
@patch("stripe_payments.views.views.stripe.PaymentIntent")
def test_return_with_matching_invoice_and_gift_voucher_anon_user(
    mock_payment_intent, client, block_gift_voucher
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

    resp = client.get(complete_url)
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
@patch("stripe_payments.views.views.stripe.PaymentIntent")
def test_return_with_invalid_invoice(mock_payment_intent, client, configured_user):
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
    resp = client.get(complete_url)
    assert "Error Processing Payment" in resp.content.decode("utf-8")
    assert invoice.paid is False
    # send failed emails
    assert len(mail.outbox) == 1
    assert mail.outbox[0].subject == "WARNING: Something went wrong processing a stripe event!"
    assert "No invoice could be retrieved from succeeded payment intent mock-intent-id" in mail.outbox[0].body


@pytest.mark.usefixtures("seller", "send_all_studio_emails")
@patch("stripe_payments.views.views.stripe.PaymentIntent")
def test_return_with_matching_invoice_multiple_bookingss(mock_payment_intent, client, configured_user):
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
    resp = client.get(complete_url)
    assert resp.status_code == 200
    assert "Payment Processed" in resp.content.decode("utf-8")
    booking1.refresh_from_db()
    booking2.refresh_from_db()
    invoice.refresh_from_db()

    assert booking1.paid is True
    assert booking2.paid is True
    assert invoice.paid is True


@pytest.mark.usefixtures("seller", "send_all_studio_emails")
@patch("stripe_payments.views.views.stripe.PaymentIntent")
def test_return_with_matching_invoice_invalid_amount(mock_payment_intent, client, configured_user):
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
    resp = client.get(complete_url)
    assert invoice.paid is False
    assert "Error Processing Payment" in resp.content.decode("utf-8")


@pytest.mark.usefixtures("seller", "send_all_studio_emails")
@patch("stripe_payments.views.views.stripe.PaymentIntent")
def test_return_with_matching_invoice_invalid_signature(mock_payment_intent, client, configured_user):
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
    resp = client.get(complete_url)
    assert invoice.paid is False
    assert "Error Processing Payment" in resp.content.decode("utf-8")


@pytest.mark.usefixtures("seller", "send_all_studio_emails")
@patch("stripe_payments.views.views.stripe.PaymentIntent")
def test_return_with_matching_invoice_block_already_processed(mock_payment_intent, client, configured_user):
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
    resp = client.get(complete_url)

    assert resp.status_code == 200
    assert "Payment Processed" in resp.content.decode("utf-8")
    # already processed, no emails sent
    assert len(mail.outbox) == 0


@pytest.mark.usefixtures("seller", "send_all_studio_emails")
@patch("stripe_payments.views.views.stripe.PaymentIntent")
def test_return_with_failed_payment_intent(mock_payment_intent, client, configured_user):
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
    resp = client.get(complete_url)
    assert invoice.paid is False
    assert "Error Processing Payment" in resp.content.decode("utf-8")


@pytest.mark.usefixtures("seller", "send_all_studio_emails")
@patch("stripe_payments.views.views.stripe.PaymentIntent")
def test_return_with_processing_payment_intent(mock_payment_intent, client, configured_user):
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
    mock_payment_intent.retrieve.return_value = get_mock_payment_intent(metadata=metadata, status="processing")
    resp = client.get(complete_url)
    assert invoice.paid is False
    assert "Your payment is processing" in resp.content.decode("utf-8")
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [settings.SUPPORT_EMAIL]


# stripe portal
@pytest.mark.usefixtures("seller")
@patch("stripe_payments.views.views.StripeConnector", MockConnector)
def test_stripe_portal_view(client):
    resp = client.get(reverse("stripe_payments:stripe_portal", args=("customer-id-123",)))
    assert resp.status_code == 302
    assert resp.url == f"https://example.com/portal/customer-id-123/"


# stripe subscribe view (stripe return url for subscriptions)

subscribe_complete_url = reverse("stripe_payments:stripe_subscribe_complete")

@pytest.mark.parametrize(
    "payment_intent_status,updating,success,template_match",
    [
        ("succeeded", False, True, "Thank you for setting up your membership"),
        ("succeeded", True, True, "Thank you for updating your membership"),
        ("processing", True, False, "Your payment is processing"),
        ("unknown", False, False, "Error Processing Payment"),
    ]
)
@pytest.mark.usefixtures("seller")
@patch("stripe_payments.utils.stripe.PaymentIntent")
def test_stripe_subscribe_complete_with_payment_intent(mock_payment_intent, client, payment_intent_status, updating, success, template_match):
    mock_payment_intent.retrieve.return_value = get_mock_payment_intent(status=payment_intent_status)
    url = f"{subscribe_complete_url}?payment_intent=pi_123"
    if updating:
        url += "&updating=true"
    resp = client.get(url)
    assert resp.status_code == 200

    assert template_match in resp.content.decode()
    if success:
        assert resp.context["updating"] == updating
        assert resp.context["payment"]
        assert len(mail.outbox) == 0
    else:
        assert len(mail.outbox) == 1
        assert "Something went wrong processing a stripe event" in mail.outbox[0].subject
       

@pytest.mark.usefixtures("seller")
@patch("stripe_payments.utils.stripe.PaymentIntent")
def test_stripe_subscribe_complete_with_payment_intent_error(mock_payment_intent, client):
    mock_payment_intent.retrieve.side_effect = stripe.InvalidRequestError("err", None)
    url = f"{subscribe_complete_url}?payment_intent=pi_123"
    resp = client.get(url)
    assert resp.status_code == 200

    assert "Error Processing Payment" in resp.content.decode()
    assert len(mail.outbox) == 1
    assert "Something went wrong processing a stripe event" in mail.outbox[0].subject


@pytest.mark.parametrize(
    "setup_intent_status,updating,success,template_match",
    [
        ("succeeded", False, True, "Thank you for setting up your membership"),
        ("succeeded", True, True, "Thank you for updating your membership"),
        ("processing", True, False, "Your payment is processing"),
        ("unknown", False, False, "Error Processing Payment"),
    ]
)
@pytest.mark.usefixtures("seller")
@patch("stripe_payments.utils.stripe.SetupIntent")
def test_stripe_subscribe_complete_with_setup_intent(mock_setup_intent, client, setup_intent_status, updating, success, template_match):
    mock_setup_intent.retrieve.return_value = get_mock_setup_intent(status=setup_intent_status)
    url = f"{subscribe_complete_url}?setup_intent=su_123"
    if updating:
        url += "&updating=true"
    resp = client.get(url)
    assert resp.status_code == 200
    assert template_match in resp.content.decode()
    if success:
        assert resp.context["updating"] == updating
        assert resp.context["setup"]
        assert len(mail.outbox) == 0
    else:
        assert len(mail.outbox) == 1
        assert "Something went wrong processing a stripe event" in mail.outbox[0].subject
       

@pytest.mark.usefixtures("seller")
@patch("stripe_payments.utils.stripe.SetupIntent")
def test_stripe_subscribe_complete_with_setup_intent_error(mock_setup_intent, client):
    mock_setup_intent.retrieve.side_effect = stripe.InvalidRequestError("err", None)
    url = f"{subscribe_complete_url}?setup_intent=su_123"
    resp = client.get(url)
    assert resp.status_code == 200

    assert "Error Processing Payment" in resp.content.decode()
    assert len(mail.outbox) == 1
    assert "Something went wrong processing a stripe event" in mail.outbox[0].subject


@pytest.mark.usefixtures("seller")
def test_stripe_subscribe_complete_with_unknown_payment_type(client):
    resp = client.get(subscribe_complete_url)
    assert resp.status_code == 200

    assert "Error Processing Payment" in resp.content.decode()
    assert len(mail.outbox) == 1
    assert "Something went wrong processing a stripe event" in mail.outbox[0].subject