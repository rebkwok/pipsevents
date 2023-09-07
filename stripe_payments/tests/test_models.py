from decimal import Decimal
import os
from unittest.mock import patch
from hashlib import sha512

import pytest

from model_bakery import baker

from booking.models import Booking, Block, TicketBooking
from ..models import Invoice, Seller, StripePaymentIntent

pytestmark = pytest.mark.django_db


def test_invoice_str():
    invoice = baker.make(Invoice, username="test@test.com", invoice_id="foo123", amount="10")
    assert str(invoice) == "foo123 - test@test.com - £10"
    assert invoice.date_paid is None
    invoice.paid = True
    invoice.save()
    assert str(invoice) == "foo123 - test@test.com - £10 (paid)"
    assert invoice.date_paid is not None


@patch("stripe_payments.models.ShortUUID.random")
def test_generate_invoice_id(short_uuid_random):
    short_uuid_random.side_effect = ["foo123", "foo234", "foo567"]
    # inv id generated from random shortuuid
    assert Invoice.generate_invoice_id() == "foo123"

    # if an invoice already exists with that id, try again until we get a unique one
    baker.make(Invoice, invoice_id="foo234")
    assert Invoice.generate_invoice_id() == "foo567"

@pytest.mark.usefixtures("invoice_keyenv")
def test_signature():
    invoice = baker.make(Invoice, invoice_id="foo123")
    assert invoice.signature() == sha512("foo123test".encode("utf-8")).hexdigest()

@pytest.mark.usefixtures("invoice_keyenv")
def test_invoice_item_count():
    invoice = baker.make(
        Invoice, invoice_id="foo123",
        memberships=baker.make(Membership, _quantity=2),
        bookings=baker.make(Booking, _quantity=1),
        gift_vouchers=baker.make(GiftVoucher, gift_voucher_type__discount_amount=10, _quantity=1),
    )
    assert invoice.item_count() == 4

@pytest.mark.usefixtures("invoice_keyenv")
def test_invoice_items_metadata():
    invoice = baker.make(Invoice, invoice_id="foo123")
    membership = baker.make(Membership, membership_type__cost=10, membership_type__name="test membership", invoice=invoice)
    booking = baker.make(Booking, event__name="test event", event__cost=10, invoice=invoice)
    gift_voucher = baker.make(GiftVoucher, gift_voucher_type__discount_amount=10, invoice=invoice)
    
    assert invoice.items_metadata() == {
        f'booking_{booking.id}_cost_in_p': '1000',
        f'booking_{booking.id}_item': str(booking.event),
        f'gift_voucher_{gift_voucher.id}_cost_in_p': '1000',
        f'gift_voucher_{gift_voucher.id}_item': 'Gift Voucher: £10.00',
        f'membership_{membership.id}_cost_in_p': '1000',
        f'membership_{membership.id}_item': f'test membership - {membership.month_str} {membership.year}'}


@pytest.mark.usefixtures("invoice_keyenv")
def test_invoice_items_summary():
    invoice = baker.make(Invoice, invoice_id="foo123")
    membership = baker.make(Membership, membership_type__cost=10, membership_type__name="test membership", invoice=invoice)
    booking = baker.make(Booking, event__name="test event", event__cost=10, invoice=invoice)
    gift_voucher = baker.make(
        GiftVoucher, gift_voucher_type__event_type="private", 
        gift_voucher_type__override_cost=Decimal(10), invoice=invoice
    )

    assert invoice.items_summary() == {
        "bookings": [str(booking.event)],
        "memberships": [str(membership)],
        "gift_vouchers": [str(gift_voucher)]
    }


@pytest.mark.usefixtures("invoice_keyenv")
def test_invoice_item_types():
    invoice = baker.make(Invoice, invoice_id="foo123")
    baker.make(Membership, membership_type__cost=10, membership_type__name="test membership", invoice=invoice)
    baker.make(Booking, event__name="test event", event__cost=10, invoice=invoice)
    baker.make(GiftVoucher, gift_voucher_type__discount_amount=10, invoice=invoice)

    assert invoice.item_types() == ["memberships", "bookings", "gift_vouchers"]


def test_seller_str():
    seller = baker.make(Seller, user__email="testuser@test.com")
    assert str(seller) == "testuser@test.com"


def test_create_stripe_payment_intent_instance_from_pi(get_mock_payment_intent):
    payment_intent = get_mock_payment_intent()
    invoice = baker.make(Invoice, invoice_id="foo123")
    assert not StripePaymentIntent.objects.exists()
    pi, created = StripePaymentIntent.update_or_create_payment_intent_instance(payment_intent, invoice)
    assert created
    assert StripePaymentIntent.objects.count() == 1
    assert pi.invoice == invoice
    assert pi.seller is None

    # update with seller
    seller = baker.make(Seller, user__email="testuser@test.com")
    pi, created = StripePaymentIntent.update_or_create_payment_intent_instance(payment_intent, invoice, seller=seller)
    assert not created
    assert StripePaymentIntent.objects.count() == 1
    assert pi.seller == seller


def test_stripe_payment_intent_str(get_mock_payment_intent):
    payment_intent = get_mock_payment_intent()
    invoice = baker.make(Invoice, invoice_id="foo123", username="user@test.com")
    pi, _ = StripePaymentIntent.update_or_create_payment_intent_instance(payment_intent, invoice)
    assert str(pi) == "mock-intent-id - invoice foo123 - user@test.com"


def test_create_stripe_refund_instance_from_refund_obj_and_pi_instance(get_mock_payment_intent, get_mock_refund):
    payment_intent_from_stripe = get_mock_payment_intent()
    refund_from_stripe = get_mock_refund()
    invoice = baker.make(Invoice, invoice_id="foo123")
    seller = baker.make(Seller, user__email="testuser@test.com")
    pi, _ = StripePaymentIntent.update_or_create_payment_intent_instance(
        payment_intent_from_stripe, invoice, seller=seller
    )
    
    refund = StripeRefund.create_from_refund_obj(
        refund=refund_from_stripe, payment_intent_model_instance=pi, booking_id=1
    )
    assert refund.booking_id == 1
    assert refund.refund_id == "mock-refund-id"
    assert refund.amount == 800
    assert refund.invoice == invoice
    assert refund.seller == seller
