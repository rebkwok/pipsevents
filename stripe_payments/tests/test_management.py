from model_bakery import baker
import pytest

from django.core import management

from booking.models import Membership, Booking, GiftVoucher
from ..models import Invoice, StripePaymentIntent
from activitylog.models import ActivityLog


pytestmark = pytest.mark.django_db


@pytest.fixture
def setup_invoices():
    # unpaid invoice with membership
    invoice1 = baker.make(
        Invoice, memberships=baker.make(Membership, paid=False, _quantity=1), paid=False
    )
    # unpaid invoice with booking
    invoice2 = baker.make(Invoice, bookings=baker.make(Booking, paid=False, _quantity=1), paid=False)
    # unpaid invoice with gift vouchers
    invoice3 = baker.make(
        Invoice,
        gift_vouchers=baker.make(GiftVoucher, gift_voucher_type__discount_amount=10, paid=False, _quantity=1), paid=False
    )
    # paid invoice, no booking, membership or gift vouchers
    invoice4 = baker.make(Invoice, paid=True)
    baker.make(StripePaymentIntent, invoice=invoice1)
    baker.make(StripePaymentIntent, invoice=invoice2)
    baker.make(StripePaymentIntent, invoice=invoice3)
    baker.make(StripePaymentIntent, invoice=invoice4)

    yield [invoice1, invoice2, invoice3, invoice4]


def test_delete_unpaid_unused_invoices(setup_invoices):
    # unpaid invoice, no items
    invoice5 = baker.make(Invoice, paid=False)
    baker.make(StripePaymentIntent, invoice=invoice5)
    assert Invoice.objects.count() == 5
    assert StripePaymentIntent.objects.count() == 5
    management.call_command('delete_unused_invoices')
    activitylog = ActivityLog.objects.latest("id")
    assert activitylog.log == f'1 unpaid unused invoice(s) deleted: invoice_ids {invoice5.invoice_id}'
    assert Invoice.objects.count() == 4
    assert StripePaymentIntent.objects.count() == 4


def test_delete_unpaid_unused_invoice_no_payment_intent(setup_invoices):
    # unpaid invoice, no items, no associated payment intent
    baker.make(Invoice, paid=False)
    assert Invoice.objects.count() == 5
    assert StripePaymentIntent.objects.count() == 4
    management.call_command('delete_unused_invoices')
    assert Invoice.objects.count() == 4
    assert StripePaymentIntent.objects.count() == 4


def test_no_invoices_to_delete(setup_invoices):
    assert Invoice.objects.count() == 4
    management.call_command('delete_unused_invoices')
    assert Invoice.objects.count() == 4
