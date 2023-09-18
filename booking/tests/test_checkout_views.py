# -*- coding: utf-8 -*-
from decimal import Decimal
from model_bakery import baker
from unittest.mock import Mock, patch

import pytest

from django.contrib.sites.models import Site
from django.urls import reverse
from django.test import TestCase
from django.utils import timezone

from stripe.error import InvalidRequestError

from booking.models import (
    Booking, EventVoucher, BlockVoucher
)
from common.tests.helpers import create_configured_user, TestSetupMixin
from stripe_payments.models import Invoice, Seller


class StripeCheckoutTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        baker.make(Seller, site=Site.objects.get_current())
        cls.url = reverse('stripe_checkout')

    def setUp(self):
        super().setUp()
        self.client.login(username=self.user.username, password='test')
        self.pole_class = baker.make_recipe("booking.future_CL", cost=10)

        self.voucher = baker.make(
            EventVoucher, code='foo', discount=10, max_per_user=10
        )
        self.voucher.event_types.add(self.pole_class.event_type)

        self.block_voucher = baker.make(
            BlockVoucher, code='foo', discount=10, max_per_user=2
        )
        self.block_type = baker.make_recipe("booking.blocktype5", cost=20)
        self.block_voucher.block_types.add(self.block_type)

        self.gift_voucher = baker.make(
            EventVoucher, code='gift_booking', discount=100, max_per_user=1,
            is_gift_voucher=True
        )
        self.gift_voucher.event_types.add(self.pole_class.event_type)
        self.block_gift_voucher = baker.make(
            BlockVoucher, code='gift_block', discount=100, max_per_user=1,
            is_gift_voucher=True
        )

    def get_mock_payment_intent(self, **params):
        defaults = {
            "id": "mock-intent-id",
            "amount": 1000,
            "description": "",
            "status": "succeeded",
            "metadata": {},
            "currency": "gbp",
            "client_secret": "secret"
        }
        options = {**defaults, **params}
        return Mock(**options)
        
    def test_anon_user_no_unpaid_items(self):
        self.client.logout()
        # bookings, blocks and ticket_bookings require login
        
        for data_dict in [
            {"cart_bookings_total": 10},
            {"cart_blocks_total": 10},
            {"cart_ticket_bookings_total": 10},
        ]:
            resp = self.client.post(self.url, data=data_dict)
            assert resp.status_code == 302
            assert resp.url == reverse("account_login")

        # If no unpaid gift vouchers, ignore any cart total passed and return to
        # gift voucher purchase page
        # invalid gift voucher id
        resp = self.client.post(self.url, data={"cart_gift_voucher": "9999", "cart_gift_voucher_total": 10})
        assert resp.status_code == 302
        assert resp.url == reverse("booking:buy_gift_voucher")

    def test_logged_in_user_no_unpaid_items(self):
        create_configured_user(
            username='newtest', email='newtest@test.com', password='test'
        )
        
        self.client.login(username="newtest", password="test")
        # bookings, blocks and ticket_bookings require login
        
        for data_dict, redirect_url in [
            ({"cart_bookings_total": 10}, reverse("booking:shopping_basket")),
            ({"cart_blocks_total": 10}, reverse("booking:shopping_basket")),
            ({"cart_ticket_bookings_total": 10, "tbref": "1234"}, reverse("booking:ticketed_events")),
            ({"cart_gift_voucher_total": 10, "cart_gift_voucher": "9999"}, reverse("booking:buy_gift_voucher")),
        ]:
            resp = self.client.post(self.url, data=data_dict)
            assert resp.status_code == 302
            assert resp.url == redirect_url

    def test_invalid_total(self):
        # If no unpaid items, ignore any cart total passed and return to shopping basket
        for data_dict, redirect_url in [
            ({"cart_bookings_total": "foo"}, reverse("booking:shopping_basket")),
            ({"cart_blocks_total": ""}, reverse("booking:shopping_basket")),
            ({"cart_ticket_bookings_total": "bar"}, reverse("booking:ticketed_events")),
            ({"cart_gift_voucher_total": "", "cart_gift_voucher": "1"}, reverse("booking:buy_gift_voucher")),
            ({"cart_stripe_test_total": 10}, reverse("studioadmin:stripe_test")),
        ]:
            resp = self.client.post(self.url, data=data_dict)
            assert resp.status_code == 302
            assert resp.url == redirect_url

    @patch("booking.views.checkout_views.stripe.PaymentIntent")
    def test_cant_identify_checkout_type(self, mock_payment_intent):
        mock_payment_intent_obj = self.get_mock_payment_intent(id="foo", amount=2000)
        mock_payment_intent.create.return_value = mock_payment_intent_obj

        resp = self.client.post(self.url, data={"unknown_cart": "foo"})
        assert resp.status_code == 302
        assert resp.url == reverse("booking:shopping_basket")

    @patch("booking.views.checkout_views.stripe.PaymentIntent")
    def test_creates_invoice_and_applies_to_unpaid_bookings(self, mock_payment_intent):
        mock_payment_intent_obj = self.get_mock_payment_intent(id="foo")
        mock_payment_intent.create.return_value = mock_payment_intent_obj

        assert Invoice.objects.exists() is False
        booking = baker.make_recipe(
            'booking.booking', event=self.pole_class,
            user=self.user, paid=False
        )
        # bookings and blocks are checked out separately, so this unpaid block doesn't count
        # towards the total
        block = baker.make_recipe(
            'booking.block_5', user=self.user, paid=False, block_type=self.block_type
        )
        # total is correct
        resp = self.client.post(self.url, data={"cart_bookings_total": 10})
        assert resp.status_code == 200
        assert resp.context_data["cart_total"] == 10.00
        assert resp.context_data["checkout_type"] == "bookings"
        booking.refresh_from_db()

        assert Invoice.objects.exists()
        invoice = Invoice.objects.first()
        assert invoice.username == self.user.email
        assert invoice.amount == 10
        assert booking.invoice == invoice

    @patch("booking.views.checkout_views.stripe.PaymentIntent")
    def test_incorrect_unpaid_bookings_total(self, mock_payment_intent):
        mock_payment_intent_obj = self.get_mock_payment_intent(id="foo", amount=2000)
        mock_payment_intent.create.return_value = mock_payment_intent_obj

        # no bookings, redirects
        resp = self.client.post(self.url, data={"cart_bookings_total": 10})
        assert resp.status_code == 302
        assert resp.url == reverse("booking:shopping_basket")

        booking = baker.make_recipe(
            'booking.booking', event=self.pole_class,
            user=self.user, paid=False, voucher_code="foo"
        )
        # total is incorrect
        resp = self.client.post(self.url, data={"cart_bookings_total": 30})
        assert resp.status_code == 302
        assert resp.url == reverse("booking:shopping_basket")
        # voucher is reset
        booking.refresh_from_db()
        assert booking.voucher_code is None

    @patch("booking.views.checkout_views.stripe.PaymentIntent")
    def test_creates_invoice_and_applies_to_unpaid_blocks(self, mock_payment_intent):
        mock_payment_intent_obj = self.get_mock_payment_intent(id="foo", amount=2000)
        mock_payment_intent.create.return_value = mock_payment_intent_obj

        assert Invoice.objects.exists() is False
        block = baker.make_recipe(
            'booking.block_5', user=self.user, paid=False, block_type__cost=20,
            start_date=timezone.now(),
        )
        # total is correct
        resp = self.client.post(self.url, data={"cart_blocks_total": 20})
        assert resp.status_code == 200
        assert resp.context_data["cart_total"] == 20.00
        assert resp.context_data["checkout_type"] == "blocks"
        block.refresh_from_db()

        assert Invoice.objects.exists()
        invoice = Invoice.objects.first()
        assert invoice.username == self.user.email
        assert invoice.amount == 20
        assert block.invoice == invoice

    @patch("booking.views.checkout_views.stripe.PaymentIntent")
    def test_incorrect_unpaid_blocks_total(self, mock_payment_intent):
        mock_payment_intent_obj = self.get_mock_payment_intent(id="foo", amount=2000)
        mock_payment_intent.create.return_value = mock_payment_intent_obj

        # no blocks, redirects
        resp = self.client.post(self.url, data={"cart_blocks_total": 30})
        assert resp.status_code == 302
        assert resp.url == reverse("booking:shopping_basket")

        block = baker.make_recipe(
            'booking.block_5', user=self.user, paid=False, block_type__cost=20,
            start_date=timezone.now(), voucher_code="foo"
        )
        # total is incorrect
        resp = self.client.post(self.url, data={"cart_blocks_total": 30})
        assert resp.status_code == 302
        assert resp.url == reverse("booking:shopping_basket")
        # voucher is reset
        block.refresh_from_db()
        assert block.voucher_code is None

    @patch("booking.views.checkout_views.stripe.PaymentIntent")
    def test_creates_invoice_and_applies_to_unpaid_gift_voucher(self, mock_payment_intent):
        mock_payment_intent_obj = self.get_mock_payment_intent(id="foo")
        mock_payment_intent.create.return_value = mock_payment_intent_obj

        assert Invoice.objects.exists() is False
        
        # total is correct
        resp = self.client.post(
            self.url, 
            data={
                "cart_gift_voucher": self.gift_voucher.id, 
                "cart_gift_voucher_total": 10
            }
        )
        assert resp.status_code == 200
        assert resp.context_data["cart_total"] == 10.00
        assert resp.context_data["checkout_type"] == "gift_vouchers"
        self.gift_voucher.refresh_from_db()

        assert Invoice.objects.exists()
        invoice = Invoice.objects.first()
        assert invoice.username == self.user.email
        assert invoice.amount == 10
        assert self.gift_voucher.invoice == invoice

    @patch("booking.views.checkout_views.stripe.PaymentIntent")
    def test_creates_incorrect_gift_voucher_total(self, mock_payment_intent):
        mock_payment_intent_obj = self.get_mock_payment_intent(id="foo")
        mock_payment_intent.create.return_value = mock_payment_intent_obj

        assert Invoice.objects.exists() is False
        
        # total is incorrect
        resp = self.client.post(
            self.url, 
            data={
                "cart_gift_voucher": self.gift_voucher.id, 
                "cart_gift_voucher_total": 100
            }
        )
        assert resp.status_code == 302
        assert resp.url == reverse("booking:buy_gift_voucher")

    @patch("booking.views.checkout_views.stripe.PaymentIntent")
    def test_unconfigured_gift_voucher(self, mock_payment_intent):
        mock_payment_intent_obj = self.get_mock_payment_intent(id="foo", amount=2000)
        mock_payment_intent.create.return_value = mock_payment_intent_obj

        # no blocks configured, redirects
        resp = self.client.post(
            self.url, 
            data={
                "cart_gift_voucher": self.block_gift_voucher.id,
                "cart_gift_voucher_total": 20
            }
        )
        assert resp.status_code == 302
        assert resp.url == reverse("booking:buy_gift_voucher")

        self.block_gift_voucher.block_types.add(self.block_type)
        resp = self.client.post(
            self.url, 
            data={
                "cart_gift_voucher": self.block_gift_voucher.id,
                "cart_gift_voucher_total": 20
            }
        )
        assert resp.status_code == 200

    @patch("booking.views.checkout_views.stripe.PaymentIntent")
    def test_creates_invoice_and_applies_to_unpaid_ticket_booking(self, mock_payment_intent):
        mock_payment_intent_obj = self.get_mock_payment_intent(id="foo")
        mock_payment_intent.create.return_value = mock_payment_intent_obj

        assert Invoice.objects.exists() is False
        ticket_booking = baker.make_recipe(
            'booking.ticket_booking', ticketed_event__ticket_cost=5,
            user=self.user, paid=False
        )
        baker.make("booking.Ticket", ticket_booking=ticket_booking, _quantity=2)
        
        # total is correct
        resp = self.client.post(
            self.url, 
            data={
                "cart_ticket_booking_ref": ticket_booking.booking_reference,
                "cart_ticket_bookings_total": 10
            })
        assert resp.status_code == 200
        assert resp.context_data["cart_total"] == 10.00
        assert resp.context_data["checkout_type"] == "ticket_bookings"
        assert resp.context_data["tbref"] == ticket_booking.booking_reference
        ticket_booking.refresh_from_db()

        assert Invoice.objects.exists()
        invoice = Invoice.objects.first()
        assert invoice.username == self.user.email
        assert invoice.amount == 10
        assert ticket_booking.invoice == invoice

    @patch("booking.views.checkout_views.stripe.PaymentIntent")
    def test_incorrect_ticket_booking_total(self, mock_payment_intent):
        mock_payment_intent_obj = self.get_mock_payment_intent(id="foo")
        mock_payment_intent.create.return_value = mock_payment_intent_obj

        assert Invoice.objects.exists() is False
        ticket_booking = baker.make_recipe(
            'booking.ticket_booking', ticketed_event__ticket_cost=5,
            user=self.user, paid=False
        )
        baker.make("booking.Ticket", ticket_booking=ticket_booking, _quantity=2)
        
        # total is incorrect
        resp = self.client.post(
            self.url, 
            data={
                "cart_ticket_bookings_total": 20,
                "cart_ticket_booking_ref": ticket_booking.booking_reference,
            })
        assert resp.status_code == 302
        assert resp.url == reverse(
            "booking:book_ticketed_event", args=(ticket_booking.ticketed_event.slug,)
        )

    @patch("booking.views.checkout_views.stripe.PaymentIntent")
    def test_incorrect_ticket_bookings_total(self, mock_payment_intent):
        mock_payment_intent_obj = self.get_mock_payment_intent(id="foo")
        mock_payment_intent.create.return_value = mock_payment_intent_obj

        assert Invoice.objects.exists() is False
        ticket_booking = baker.make_recipe(
            'booking.ticket_booking', ticketed_event__ticket_cost=5,
            user=self.user, paid=False
        )
        baker.make("booking.Ticket", ticket_booking=ticket_booking, _quantity=2)
        
        # total is incorrect
        resp = self.client.post(
            self.url, 
            data={
                "cart_ticket_bookings_total": 20
            })
        assert resp.status_code == 302
        assert resp.url == reverse("booking:ticketed_events")

    @patch("booking.views.checkout_views.stripe.PaymentIntent")
    def test_creates_invoice_and_applies_to_unpaid_ticket_bookings(self, mock_payment_intent):
        mock_payment_intent_obj = self.get_mock_payment_intent(id="foo")
        mock_payment_intent.create.return_value = mock_payment_intent_obj

        assert Invoice.objects.exists() is False
        ticket_booking = baker.make_recipe(
            'booking.ticket_booking', ticketed_event__ticket_cost=5,
            user=self.user, paid=False
        )
        baker.make("booking.Ticket", ticket_booking=ticket_booking, _quantity=2)
        ticket_booking1 = baker.make_recipe(
            'booking.ticket_booking', ticketed_event__ticket_cost=10,
            user=self.user, paid=False
        )
        baker.make("booking.Ticket", ticket_booking=ticket_booking1, _quantity=3)
        
        # total is correct
        resp = self.client.post(self.url, data={"cart_ticket_bookings_total": 40})
        assert resp.status_code == 200
        assert resp.context_data["cart_total"] == 40.00
        assert resp.context_data["checkout_type"] == "ticket_bookings"
        assert resp.context_data["tbref"] == ""
        ticket_booking.refresh_from_db()

        assert Invoice.objects.exists()
        invoice = Invoice.objects.first()
        assert invoice.username == self.user.email
        assert invoice.amount == 40
        assert invoice.ticket_bookings.count() == 2

    @patch("booking.views.checkout_views.stripe.PaymentIntent")
    def test_no_ticket_bookings(self, mock_payment_intent):
        mock_payment_intent_obj = self.get_mock_payment_intent(id="foo", amount=2000)
        mock_payment_intent.create.return_value = mock_payment_intent_obj

        # no ticket bookings, redirects
        resp = self.client.post(
            self.url, 
            data={
                "cart_ticket_booking_ref": "none",
                "cart_ticket_bookings_total": 10
            }
        )
        assert resp.status_code == 302
        assert resp.url == reverse("booking:ticketed_events")

    @patch("booking.views.checkout_views.stripe.PaymentIntent")
    def test_creates_invoice_and_applies_to_unpaid_gift_vouchers_anon_user(
            self, mock_payment_intent
    ):
        self.client.logout()
        self.gift_voucher.purchaser_email = "test@test.com"
        self.gift_voucher.save()
        mock_payment_intent_obj = self.get_mock_payment_intent(id="foo")
        mock_payment_intent.create.return_value = mock_payment_intent_obj

        assert Invoice.objects.exists() is False
        
        # total is correct
        resp = self.client.post(
            self.url, 
            data={"cart_gift_voucher": self.gift_voucher.id, "cart_gift_voucher_total": 10}
        )
        assert resp.status_code == 200
        assert resp.context_data["cart_total"] == 10.00
        assert resp.context_data["checkout_type"] == "gift_vouchers"
        self.gift_voucher.refresh_from_db()

        assert Invoice.objects.exists()
        invoice = Invoice.objects.first()
        assert invoice.username == "test@test.com"
        assert invoice.amount == 10
        assert self.gift_voucher.invoice == invoice

    @patch("booking.views.checkout_views.stripe.PaymentIntent")
    def test_creates_invoice_and_applies_to_unpaid_blocks_with_vouchers(self, mock_payment_intent):
        mock_payment_intent_obj = self.get_mock_payment_intent(id="foo", amount=1800)
        mock_payment_intent.create.return_value = mock_payment_intent_obj
        
        block = baker.make(
            "booking.Block", user=self.user, voucher_code=self.block_voucher.code,
            block_type=self.block_type
        )  # 20, 18 with voucher

        assert Invoice.objects.exists() is False
        # total is correct
        resp = self.client.post(self.url, data={"cart_blocks_total": 18})
        assert resp.status_code == 200
        
        block.refresh_from_db()
        assert Invoice.objects.exists()
        invoice = Invoice.objects.first()
        assert invoice.username == self.user.email
        assert invoice.amount == 18
        block.invoice == invoice
        assert resp.context_data["cart_total"] == 18.00

    @patch("booking.views.checkout_views.stripe.PaymentIntent")
    def test_incorrect_stripe_test_total(self, mock_payment_intent):
        mock_payment_intent_obj = self.get_mock_payment_intent(id="foo")
        mock_payment_intent.create.return_value = mock_payment_intent_obj

        assert Invoice.objects.exists() is False
        
        # total is incorrect
        resp = self.client.post(
            self.url, 
            data={
                "cart_stripe_test_total": 20,
            })
        assert resp.status_code == 302
        assert resp.url == reverse("studioadmin:stripe_test")

    @patch("booking.views.checkout_views.stripe.PaymentIntent")
    def test_creates_invoice_for_stripe_test(self, mock_payment_intent):
        mock_payment_intent_obj = self.get_mock_payment_intent(id="foo")
        mock_payment_intent.create.return_value = mock_payment_intent_obj

        assert Invoice.objects.exists() is False
        
        # total is correct
        resp = self.client.post(self.url, data={"cart_stripe_test_total": "0.30"})
        assert resp.status_code == 200
        assert resp.context_data["cart_total"] == Decimal("0.30")
        assert resp.context_data["checkout_type"] == "stripe_test"

        assert Invoice.objects.exists()
        invoice = Invoice.objects.first()
        assert invoice.username == self.user.email
        assert invoice.amount == Decimal("0.30")
        assert invoice.item_count() == 1
        assert invoice.is_stripe_test

    def test_zero_total(self):
        booking = baker.make(
            Booking, event=self.pole_class, user=self.user, voucher_code=self.gift_voucher.code
        )
        resp = self.client.post(self.url, data={"cart_bookings_total": 0})
        booking.refresh_from_db()
        assert booking.paid
        assert booking.voucher_code == self.gift_voucher.code

        # invoice is still created, but with 0 total and no PI
        invoice = Invoice.objects.first()
        assert invoice.stripe_payment_intent_id is None
        assert invoice.username == self.user.email
        assert invoice.amount == 0
        assert booking.invoice == invoice

        assert resp.status_code == 302
        assert resp.url == reverse("booking:lessons")

    def test_zero_total_blocks(self):
        block = baker.make(
            "booking.Block", user=self.user, voucher_code=self.block_gift_voucher.code,
            block_type=self.block_type, start_date=timezone.now()
        )
        
        resp = self.client.post(self.url, data={"cart_blocks_total": 0})
        block.refresh_from_db()
        assert block.paid
        assert block.voucher_code == self.block_gift_voucher.code

        # invoice is still created, but with 0 total and no PI
        invoice = Invoice.objects.first()
        assert invoice.stripe_payment_intent_id is None
        assert invoice.username == self.user.email
        assert invoice.amount == 0
        assert block.invoice == invoice

        assert resp.status_code == 302
        assert resp.url == reverse("booking:lessons")

    @patch("booking.views.checkout_views.stripe.PaymentIntent")
    def test_uses_existing_invoice(self, mock_payment_intent):
        mock_payment_intent_obj = self.get_mock_payment_intent(id="foo")
        mock_payment_intent.modify.return_value = mock_payment_intent_obj
        invoice = baker.make(
            Invoice, username=self.user.email, amount=20, paid=False,
            stripe_payment_intent_id="foo"
        )
        booking = baker.make(Booking, event=self.pole_class, user=self.user, invoice=invoice)

        # total is correct
        resp = self.client.post(self.url, data={"cart_bookings_total": 10})
        booking.refresh_from_db()
        assert Invoice.objects.count() == 1
        assert booking.invoice == invoice
        assert invoice.amount == 20
        assert resp.context_data["cart_total"] ==10.00

    @patch("booking.views.checkout_views.stripe.PaymentIntent")
    def test_uses_existing_invoice_for_gift_voucher(self, mock_payment_intent):
        mock_payment_intent_obj = self.get_mock_payment_intent(id="foo")
        mock_payment_intent.modify.return_value = mock_payment_intent_obj
        invoice = baker.make(
            Invoice, username="test@test.com", amount=10, paid=False,
            stripe_payment_intent_id="foo"
        )
        self.gift_voucher.purchaser_email = "test@test.com"
        self.gift_voucher.invoice = invoice
        self.gift_voucher.save()
        # total is correct
        resp = self.client.post(
            self.url, 
            data={
                "cart_gift_voucher": self.gift_voucher.id,
                "cart_gift_voucher_total": 10
            }
        )
        self.gift_voucher.refresh_from_db()
        assert Invoice.objects.count() == 1
        assert self.gift_voucher.invoice == invoice
        assert invoice.amount == 10
        assert resp.context_data["cart_total"] ==10.00

    def test_no_seller(self):
        Seller.objects.all().delete()
        baker.make("booking.booking", event=self.pole_class, user=self.user)

        resp = self.client.post(self.url, data={"cart_bookings_total": 10})
        assert resp.status_code == 200
        assert resp.context_data["preprocessing_error"] is True

    @patch("booking.views.checkout_views.stripe.PaymentIntent")
    def test_invoice_already_succeeded(self, mock_payment_intent):
        mock_payment_intent_obj = self.get_mock_payment_intent(id="foo", status="succeeded")
        mock_payment_intent.modify.side_effect = InvalidRequestError("error", None)
        mock_payment_intent.retrieve.return_value = mock_payment_intent_obj

        invoice = baker.make(
            Invoice, username=self.user.email, amount=10, paid=False,
            stripe_payment_intent_id="foo"
        )
        baker.make(Booking, event=self.pole_class, user=self.user, invoice=invoice)
        resp = self.client.post(self.url, data={"cart_bookings_total": 10})
        assert resp.context_data["preprocessing_error"] is True

    @patch("booking.views.checkout_views.stripe.PaymentIntent")
    def test_other_error_modifying_payment_intent(self, mock_payment_intent):
        mock_payment_intent_obj = self.get_mock_payment_intent(id="foo", status="pending")
        mock_payment_intent.modify.side_effect = InvalidRequestError("error", None)
        mock_payment_intent.retrieve.return_value = mock_payment_intent_obj

        invoice = baker.make(
            Invoice, username=self.user.email, amount=30, paid=False,
            stripe_payment_intent_id="foo"
        )
        baker.make(Booking, event=self.pole_class, user=self.user, invoice=invoice)
        
        resp = self.client.post(self.url, data={"cart_bookings_total": 10})
        assert resp.context_data["preprocessing_error"] is True

    def test_check_total(self):
        # This is the last check immediately before submitting payment; just returns the current total
        # so the js can check it

        # no unpaid items, no checkout_type specified
        url = reverse("booking:check_total")
        resp = self.client.get(url)
        assert resp.json() == {"total": 0}

        baker.make(Booking, event=self.pole_class, user=self.user)
        # no checkout_type specified
        resp = self.client.get(url)
        assert resp.json() == {"total": 0}
        # with checkout type
        resp = self.client.get(url, {"checkout_type": "bookings"})
        assert resp.json() == {"total": "10.00"}

        baker.make_recipe(
            'booking.block_5', user=self.user, paid=False, block_type=self.block_type,
            voucher_code=self.block_voucher.code, start_date=timezone.now()
        )

        resp = self.client.get(url, {"checkout_type": "blocks"})
        assert resp.json() == {"total": "18.00"}

        ticket_booking = baker.make_recipe(
            'booking.ticket_booking', ticketed_event__ticket_cost=6,
            user=self.user, paid=False
        )
        baker.make("booking.Ticket", ticket_booking=ticket_booking, _quantity=2)
        resp = self.client.get(
            url, 
            {"checkout_type": "ticket_bookings", "tbref": ticket_booking.booking_reference}
        )
        assert resp.json() == {"total": "12.00"}

        resp = self.client.get(
            url, {"checkout_type": "gift_vouchers", "voucher_id": self.gift_voucher.id}
        )
        assert resp.json() == {"total": "10.00"}

        # no valid block types on voucher
        with pytest.raises(ValueError):
            resp = self.client.get(
                url, {"checkout_type": "gift_vouchers", "voucher_id": self.block_gift_voucher.id}
            )
        self.block_gift_voucher.block_types.add(self.block_type)
        resp = self.client.get(
                url, {"checkout_type": "gift_vouchers", "voucher_id": self.block_gift_voucher.id}
            )
        assert resp.json() == {"total": "20.00"}

        # stripe test
        resp = self.client.get(url, {"checkout_type": "stripe_test"})
        assert resp.json() == {"total": "0.30"}

    def test_check_total_anon_user(self):
        self.client.logout()
        url = reverse("booking:check_total")
        resp = self.client.get(url)
        assert resp.json() == {"total": 0}

        # voucher invalid
        # self.gift_voucher.purchaser_email = "test@test.com"
        # self.gift_voucher.save()
        self.gift_voucher.event_types.remove(self.pole_class.event_type)
        
        with pytest.raises(ValueError):
            resp = self.client.get(
                url, {"checkout_type": "gift_vouchers", "voucher_id": self.gift_voucher.id}
            )

        self.gift_voucher.event_types.add(self.pole_class.event_type)
        resp = self.client.get(
                url, {"checkout_type": "gift_vouchers", "voucher_id": self.gift_voucher.id}
            )
        assert resp.json() == {"total": "10.00"}
