from model_mommy import mommy
from django.test import TestCase

from booking.context_helpers import (
    get_paypal_dict, get_paypal_cart_dict, get_paypal_custom
)
from common.tests.helpers import PatchRequestMixin
from payments import helpers
from payments.forms import (
    PayPalPaymentsUpdateForm, PayPalPaymentsShoppingBasketForm
)


class PayPalPaymentsUpdateFormTests(PatchRequestMixin, TestCase):

    def test_form_renders_buy_it_now_button(self):
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


class PayPalPaymentsShoppingBasketFormTests(PatchRequestMixin, TestCase):

    def test_form_renders_buy_it_now_button(self):
        booking = mommy.make_recipe('booking.booking')
        invoice_id = helpers.create_multibooking_paypal_transaction(
            booking.user, [booking]
        )
        form = PayPalPaymentsShoppingBasketForm(
            initial=get_paypal_cart_dict(
                        'http://example.com',
                        'booking',
                        [booking],
                        invoice_id,
                        get_paypal_custom(
                            'booking', str(booking.id), None, booking.user.email
                        )
                    )
        )
        self.assertIn('Checkout Now', form.render())
