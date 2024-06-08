from decimal import Decimal
from booking.models import Booking, Block, TicketBooking, Ticket, GiftVoucherType
import pytest

from django.contrib.admin import AdminSite
from django.urls import reverse

from model_bakery import baker

from stripe_payments.models import Invoice, StripePaymentIntent
from conftest import get_mock_payment_intent

from ..admin import StripePaymentIntentAdmin, InvoiceAdmin


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


def test_invoice_display_payment_intent():
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
    pi, _ = StripePaymentIntent.update_or_create_payment_intent_instance(
        get_mock_payment_intent(), invoice
    )
    booking = baker.make(Booking, event__name="test event", event__cost=10, invoice=invoice)
    invoice_admin = InvoiceAdmin(Invoice, AdminSite())
    assert invoice_admin.items(invoice) == f"<ul><li>{booking.event.str_no_location()}</li></ul>"


def test_payment_intent_admin_display(block_gift_voucher):
    invoice = baker.make(
        Invoice, invoice_id="foo123", username="test@test.com", amount=10
    )
    block_gift_voucher.invoice = invoice
    block_gift_voucher.save()
    booking = baker.make(Booking, event__name="test event", event__cost=10, invoice=invoice)
    block = baker.make(Block, invoice=invoice)
    ticket_booking = baker.make(TicketBooking, invoice=invoice)

    pi, _ = StripePaymentIntent.update_or_create_payment_intent_instance(
        get_mock_payment_intent(), invoice
    )
    payment_intent_admin = StripePaymentIntentAdmin(StripePaymentIntent, AdminSite())
    
    assert payment_intent_admin.username(pi) == "test@test.com"
    inv_admin_url = reverse("admin:stripe_payments_invoice_change", args=(invoice.pk,))
    assert payment_intent_admin.inv(pi) == f'<a href="{inv_admin_url}">foo123</a>'
    assert payment_intent_admin.items(pi) == (
        "<ul>"
        f"<li>{booking.event.str_no_location()}</li>"
        f"<li>{str(block.block_type)}</li>"
        f"<li>{block_gift_voucher.gift_voucher_type.name}</li>"
        f"<li>{str(ticket_booking.ticketed_event)}</li>"
        "</ul>"
    )

