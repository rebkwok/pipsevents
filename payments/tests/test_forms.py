from model_bakery import baker
from django.test import TestCase

from booking.context_helpers import (
    get_paypal_dict, get_paypal_cart_dict, get_paypal_custom
)
from common.tests.helpers import PatchRequestMixin
from payments import helpers
from payments.forms import (
    PayPalPaymentsUpdateForm, PayPalPaymentsShoppingBasketForm
)
from payments.tests.utils import get_mock_request


class PayPalPaymentsUpdateFormTests(PatchRequestMixin, TestCase):

    def test_form_renders_buy_it_now_button(self):
        booking = baker.make_recipe('booking.booking')
        pptrans = helpers.create_booking_paypal_transaction(
            booking.user, booking
        )
        form = PayPalPaymentsUpdateForm(
            initial=get_paypal_dict(
                        get_mock_request(booking.user),
                        booking.event.cost,
                        booking.event,
                        pptrans.invoice_id,
                        get_paypal_custom("booking", str(booking.id), None, None, None))
        )
        self.assertIn('Buy it Now', form.render())


class PayPalPaymentsShoppingBasketFormTests(PatchRequestMixin, TestCase):

    def test_form_renders_buy_it_now_button(self):
        booking = baker.make_recipe('booking.booking')
        invoice_id = helpers.create_multibooking_paypal_transaction(
            booking.user, [booking]
        )
        form = PayPalPaymentsShoppingBasketForm(
            initial=get_paypal_cart_dict(
                        get_mock_request(booking.user),
                        'booking',
                        [booking],
                        invoice_id,
                        get_paypal_custom(
                            'booking', str(booking.id), None, [], booking.user.email
                        )
                    )
        )
        self.assertIn('Checkout Now', form.render())
