from unittest.mock import patch, Mock

from django.core import mail

from model_bakery import baker
import pytest

from stripe.error import InvalidRequestError

from stripe_payments.models import StripePaymentIntent, Invoice, StripeRefund


from ..utils import process_refund


pytestmark = pytest.mark.django_db


@patch("stripe_payments.utils.stripe.Refund")
def test_process_refund(
    mock_refund, get_mock_refund, get_mock_payment_intent, configured_user, invoice, seller
):
    booking = baker.make_recipe(
        "booking.booking", event__cost=8, user=configured_user, paid=True, invoice=invoice
    )
    invoice.refresh_from_db()
    pi, _ = StripePaymentIntent.update_or_create_payment_intent_instance(
        get_mock_payment_intent(metadata=invoice.items_metadata()), invoice
    ) 

    mock_refund.create.return_value = get_mock_refund()
    refunded = process_refund(Mock(), booking)
    assert refunded

    refund_obj = StripeRefund.objects.first()
    assert refund_obj.payment_intent == pi
    assert refund_obj.invoice == invoice
    assert refund_obj.amount == 800


def test_process_refund_no_payment_intent(
    configured_user, invoice, seller
):
    booking = baker.make_recipe(
        "booking.booking", event__cost=8, user=configured_user, paid=True, invoice=invoice
    )
    refunded = process_refund(Mock(), booking)
    assert not refunded
    assert not StripeRefund.objects.exists()
    assert mail.outbox[0].subject == 'WARNING: Refund failed'
    assert "Payment intent not found" in mail.outbox[0].body


def test_process_refund_count_not_find_booking_cost(
    get_mock_payment_intent, configured_user, invoice, seller
):
    booking = baker.make_recipe(
        "booking.booking", event__cost=8, user=configured_user, paid=True, invoice=invoice
    )
    invoice.refresh_from_db()
    StripePaymentIntent.update_or_create_payment_intent_instance(
        get_mock_payment_intent(metadata={}), invoice
    ) 
    refunded = process_refund(Mock(), booking)
    assert not refunded
    assert not StripeRefund.objects.exists()
    assert mail.outbox[0].subject == 'WARNING: Refund failed'
    assert "Amount could not be parsed from PI metadata" in mail.outbox[0].body


@patch("stripe_payments.utils.stripe.Refund")
def test_process_refund_invalid_request_error(
    mock_refund, get_mock_payment_intent, configured_user, invoice, seller
):
    mock_refund.create.side_effect = InvalidRequestError("Invalid request", None)
    booking = baker.make_recipe(
        "booking.booking", event__cost=8, user=configured_user, paid=True, invoice=invoice
    )
    invoice.refresh_from_db()
    StripePaymentIntent.update_or_create_payment_intent_instance(
        get_mock_payment_intent(metadata=invoice.items_metadata()), invoice
    )
    refunded = process_refund(Mock(), booking)
    assert not refunded
    assert mail.outbox[0].subject == 'WARNING: Refund failed'
    assert "Invalid request" in mail.outbox[0].body


@patch("stripe_payments.utils.stripe.Refund")
def test_process_refund_unknown_error(
    mock_refund, get_mock_payment_intent, configured_user, invoice, seller
):
    mock_refund.create.side_effect = Exception("Unknown")
    booking = baker.make_recipe(
        "booking.booking", event__cost=8, user=configured_user, paid=True, invoice=invoice
    )
    invoice.refresh_from_db()
    StripePaymentIntent.update_or_create_payment_intent_instance(
        get_mock_payment_intent(metadata=invoice.items_metadata()), invoice
    )
    refunded = process_refund(Mock(), booking)
    assert not refunded
    assert mail.outbox[0].subject == 'WARNING: Refund failed'
    assert "Unknown" in mail.outbox[0].body
