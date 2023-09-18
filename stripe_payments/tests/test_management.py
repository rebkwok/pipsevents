from model_bakery import baker
import pytest

from django.core import management

from booking.models import Block, TicketBooking, Booking, GiftVoucherType
from ..models import Invoice, StripePaymentIntent
from activitylog.models import ActivityLog


pytestmark = pytest.mark.django_db


@pytest.fixture
def setup_invoices(block_gift_voucher):
    # unpaid invoice with block
    invoice1 = baker.make(
        Invoice, blocks=baker.make(Block, paid=False, _quantity=1), paid=False
    )
    # unpaid invoice with booking
    invoice2 = baker.make(Invoice, bookings=baker.make(Booking, paid=False, _quantity=1), paid=False)
    # unpaid invoice with gift vouchers
    invoice3 = baker.make(Invoice, paid=False)
    block_gift_voucher.invoice = invoice3
    block_gift_voucher.save()
    # unpaid invoice with ticket booking
    invoice4 = baker.make(
        Invoice, ticket_bookings=baker.make(TicketBooking, paid=False, _quantity=1), paid=False)
   
    # paid invoice, no booking, block. ticket_booking or gift vouchers
    invoice5 = baker.make(Invoice, paid=True)
    baker.make(StripePaymentIntent, invoice=invoice1)
    baker.make(StripePaymentIntent, invoice=invoice2)
    baker.make(StripePaymentIntent, invoice=invoice3)
    baker.make(StripePaymentIntent, invoice=invoice4)
    baker.make(StripePaymentIntent, invoice=invoice5)

    yield [invoice1, invoice2, invoice3, invoice4, invoice5]


def test_delete_unpaid_unused_invoices(setup_invoices):
    # unpaid invoice, no items
    invoice6 = baker.make(Invoice, paid=False)
    baker.make(StripePaymentIntent, invoice=invoice6)
    assert Invoice.objects.count() == 6
    assert StripePaymentIntent.objects.count() == 6
    management.call_command('delete_unused_invoices')
    activitylog = ActivityLog.objects.latest("id")
    assert activitylog.log == f'1 unpaid unused invoice(s) deleted: invoice_ids {invoice6.invoice_id}'
    assert Invoice.objects.count() == 5
    assert StripePaymentIntent.objects.count() == 5


def test_delete_unpaid_unused_invoice_no_payment_intent(setup_invoices):
    # unpaid invoice, no items, no associated payment intent
    baker.make(Invoice, paid=False)
    assert Invoice.objects.count() == 6
    assert StripePaymentIntent.objects.count() == 5
    management.call_command('delete_unused_invoices')
    assert Invoice.objects.count() == 5
    assert StripePaymentIntent.objects.count() == 5


def test_no_invoices_to_delete(setup_invoices):
    assert Invoice.objects.count() == 5
    management.call_command('delete_unused_invoices')
    assert Invoice.objects.count() == 5
