import os

from unittest.mock import patch

from model_bakery import baker
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

from django.contrib.auth.models import User
from django.urls import reverse
from django.test import TestCase
from django.contrib.auth.models import Permission
from django.utils import timezone

from accounts.models import PrintDisclaimer, OnlineDisclaimer, \
    DataPrivacyPolicy
from accounts.utils import has_active_data_privacy_agreement

from booking.models import Event, BlockVoucher, Booking, EventVoucher, GiftVoucher
from booking.views import EventListView, EventDetailView
from common.tests.helpers import TestSetupMixin, format_content, \
    make_data_privacy_agreement


class GiftVoucherPurchseViewTests(TestSetupMixin, TestCase):

    def setUpTestData(cls):
        super().setUpTestData()
        eventtype_pc = baker.make_recipe('booking.event_type_PC')
        eventtype_pp = baker.make_recipe('booking.event_type_PP')
        # Need to make at least one event of each type, it'll be used for the voucher cost
        baker.make_recipe(Event, event_type=eventtype_pc, cost=10)
        baker.make_recipe(Event, event_type=eventtype_pp, cost=5)
        blocktype5 = baker.make_recipe('booking.blocktype5', cost=20)
        blocktype10 = baker.make_recipe('booking.blocktype10', cost=40)

        for voucher_type in [eventtype_pc, eventtype_pp]:
            baker.make(GiftVoucher, event_type=voucher_type)
        for voucher_type in [blocktype5, blocktype10]:
            baker.make(GiftVoucher, block_type=voucher_type)


    def test_gift_voucher_view_no_login_required(self):
        pass

    def test_purchase_gift_voucher_block(self):
        # creates event voucher
        # redirects to payment view
        pass

    def test_purchase_gift_voucher_event(self):
        # creates block voucher
        # redirects to payment view
        pass

    def test_update_gift_voucher(self):
        # deactivated gift voucher redirects to payment view
        pass

    def test_update_gift_voucher_existing_paypal_payment_transaction(self):
        # deactivated gift voucher redirects to payment view, same invoice number
        pass

    def test_update_activated_gift_voucher(self):
        # can't update voucher type or email
        # redirects to voucher detail page
        pass