from decimal import Decimal
from booking.models import Booking, GiftVoucher, Membership
import pytest

from django.contrib.admin import AdminSite
from django.urls import reverse

from model_bakery import baker

from stripe_payments.models import Invoice, StripePaymentIntent, StripeRefund

from ..admin import StripePaymentIntentAdmin, StripeRefundAdmin, InvoiceAdmin


pytestmark = pytest.mark.django_db


def test_invoice_display_no_payment_intent_or_items():
    invoice = baker.make(
        Invoice, invoice_id="foo123", username="test@test.com", amount=10
    )

    invoice_admin = InvoiceAdmin(Invoice, AdminSite())
    
    assert invoice_admin.get_username(invoice) == "test@test.com"
    assert invoice_admin.display_amount(invoice) == "£10"
    assert invoice_admin.items(invoice) == ""
    assert invoice_admin.pi(invoice) == ""


def test_invoice_display_payment_intent(get_mock_payment_intent):
    invoice = baker.make(
        Invoice, invoice_id="foo123", username="test@test.com", amount=10
    )
    pi, _ = StripePaymentIntent.update_or_create_payment_intent_instance(
        get_mock_payment_intent(), invoice
    )
    invoice_admin = InvoiceAdmin(Invoice, AdminSite())
    pi_admin_url = reverse("admin:stripe_payments_stripepaymentintent_change", args=(pi.pk,))
    assert invoice_admin.pi(invoice) == f'<a href="{pi_admin_url}">mock-intent-id</a>'


def test_invoice_display_items():
    invoice = baker.make(
        Invoice, invoice_id="foo123", username="test@test.com", amount=10
    )
    booking = baker.make(Booking, event__name="test event", event__cost=10, invoice=invoice)
    invoice_admin = InvoiceAdmin(Invoice, AdminSite())
    assert invoice_admin.items(invoice) == f"<ul><li>{str(booking.event)}</li></ul>"


def test_payment_intent_admin_display(get_mock_payment_intent):
    invoice = baker.make(
        Invoice, invoice_id="foo123", username="test@test.com", amount=10
    )
    membership = baker.make(Membership, membership_type__cost=10, membership_type__name="test membership", invoice=invoice)
    booking = baker.make(Booking, event__name="test event", event__cost=10, invoice=invoice)
    gift_voucher = baker.make(
        GiftVoucher, gift_voucher_type__event_type="private", 
        gift_voucher_type__override_cost=Decimal(10), invoice=invoice
    )

    pi, _ = StripePaymentIntent.update_or_create_payment_intent_instance(
        get_mock_payment_intent(), invoice
    )
    payment_intent_admin = StripePaymentIntentAdmin(StripePaymentIntent, AdminSite())
    
    assert payment_intent_admin.username(pi) == "test@test.com"
    inv_admin_url = reverse("admin:stripe_payments_invoice_change", args=(invoice.pk,))
    assert payment_intent_admin.inv(pi) == f'<a href="{inv_admin_url}">foo123</a>'
    assert payment_intent_admin.items(pi) == (
        "<ul>"
        f"<li>{str(booking.event)}</li>"
        f"<li>{str(membership)}</li>"
        f"<li>{str(gift_voucher)}</li>"
        "</ul>"
    )


def test_refund_admin_display(get_mock_payment_intent, get_mock_refund):
    invoice = baker.make(
        Invoice, invoice_id="foo123", username="test@test.com", amount=10
    )
    membership = baker.make(Membership, membership_type__cost=10, membership_type__name="test membership", invoice=invoice)
    booking = baker.make(Booking, event__name="test event", event__cost=10, invoice=invoice)
    booking_id = booking.id
    gift_voucher = baker.make(
        GiftVoucher, gift_voucher_type__event_type="private", 
        gift_voucher_type__override_cost=Decimal(10), invoice=invoice
    )

    pi, _ = StripePaymentIntent.update_or_create_payment_intent_instance(
        get_mock_payment_intent(), invoice
    )
    
    refund_from_stripe = get_mock_refund()
    refund = StripeRefund.create_from_refund_obj(
        refund=refund_from_stripe, payment_intent_model_instance=pi, booking_id=booking.id
    )
    refund_admin = StripeRefundAdmin(StripeRefund, AdminSite())

    assert refund_admin.username(refund) == "test@test.com"
    inv_admin_url = reverse("admin:stripe_payments_invoice_change", args=(invoice.pk,))
    assert refund_admin.inv(refund) == f'<a href="{inv_admin_url}">foo123</a>'
    pi_admin_url = reverse("admin:stripe_payments_stripepaymentintent_change", args=(pi.pk,))
    assert refund_admin.pi(refund) == f'<a href="{pi_admin_url}">mock-intent-id</a>'
    booking_admin_url = reverse("admin:booking_booking_change", args=(booking.id,))
    assert refund_admin.booking(refund) == f'<a href="{booking_admin_url}">{booking.event}</a>'

    booking.delete()
    assert refund_admin.booking(refund) == f"{booking_id} (deleted)"
