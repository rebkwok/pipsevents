# -*- coding: utf-8 -*-

from model_bakery import baker

from django.test import TestCase
from common.tests.helpers import PatchRequestMixin
from studioadmin.forms import ConfirmPaymentForm, StatusFilter


class StatusFilterTests(TestCase):

    def test_form_valid(self):
        form = StatusFilter({'status_choice': 'OPEN'})
        self.assertTrue(form.is_valid())


class ConfirmPaymentFormTests(PatchRequestMixin, TestCase):

    def test_form_valid(self):
        user = baker.make_recipe('booking.user')
        event = baker.make_recipe('booking.future_PC')
        booking = baker.make_recipe('booking.booking', user=user, event=event)
        form = ConfirmPaymentForm(data={'paid': 'true'}, instance=booking)
        self.assertTrue(form.is_valid())
