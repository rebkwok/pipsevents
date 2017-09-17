from model_mommy import mommy
from django.test import TestCase

from booking.context_helpers import get_paypal_dict
from booking.tests.helpers import PatchRequestMixin
from payments import helpers
from payments.forms import PayPalPaymentsListForm, PayPalPaymentsUpdateForm


class PayPalFormTests(PatchRequestMixin, TestCase):

    def test_PayPalPaymentsListForm_renders_buy_it_now_button(self):
        booking = mommy.make_recipe('booking.booking')
        pptrans = helpers.create_booking_paypal_transaction(
            booking.user, booking
        )
        form = PayPalPaymentsListForm(
            initial=get_paypal_dict(
                        'http://example.com',
                        booking.event.cost,
                        booking.event,
                        pptrans.invoice_id,
                        '{} {}'.format('booking', booking.id)
                    )
        )
        self.assertIn('Buy it Now', form.render())

    def test_PayPalPaymentsUpdateForm_renders_buy_it_now_button(self):
        booking = mommy.make_recipe('booking.booking')
        pptrans = helpers.create_booking_paypal_transaction(
            booking.user, booking
        )
        form = PayPalPaymentsUpdateForm(
            initial=get_paypal_dict(
                        'http://example.com',
                        booking.event.cost,
                        booking.event,
                        pptrans.invoice_id,
                        '{} {}'.format('booking', booking.id)
                    )
        )
        self.assertIn('Buy it Now', form.render())
