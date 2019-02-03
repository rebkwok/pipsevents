# -*- coding: utf-8 -*-
import pytz
from datetime import  date, datetime

from unittest.mock import patch
from model_mommy import mommy

from django.urls import reverse
from django.test import TestCase
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone

from accounts.models import OnlineDisclaimer, PrintDisclaimer
from booking.models import Event, Booking, BlockType
from common.tests.helpers import _create_session, format_content
from studioadmin.views import (
    register_view_new, booking_register_add_view, ajax_toggle_attended,
    ajax_toggle_paid, ajax_assign_block
)
from studioadmin.tests.test_views.helpers import TestPermissionMixin


class NewRegisterViewTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.pc = mommy.make_recipe('booking.future_PC', max_participants=3)
        cls.pc_no_max = mommy.make_recipe('booking.future_PC')
        cls.ev = mommy.make_recipe('booking.future_EV', max_participants=3)
        cls.pc_url = reverse('studioadmin:event_register', args=(cls.pc.slug,))
        cls.pc_no_max_url = reverse('studioadmin:event_register', args=(cls.pc_no_max.slug,))
        cls.ev_url = reverse('studioadmin:event_register', args=(cls.ev.slug,))

    def setUp(self):
        super().setUp()
        self.client.login(username=self.staff_user.username, password='test')

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(self.pc_url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('account_login') + "?next={}".format(self.pc_url))

    def test_staff_or_instructor_required(self):
        self.client.logout()
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.pc_url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.get(self.pc_url)
        self.assertEqual(resp.status_code, 200)

        self.client.logout()
        self.client.login(username=self.instructor_user.username, password='test')
        resp = self.client.get(self.pc_url)
        self.assertEqual(resp.status_code, 200)

    def test_sidenav_selection(self):
        resp = self.client.get(self.pc_url)
        self.assertEqual(resp.context_data['sidenav_selection'], 'lessons_register')

        resp = self.client.get(self.ev_url)
        self.assertEqual(resp.context_data['sidenav_selection'], 'events_register')

    def test_register_no_bookings(self):
        resp = self.client.get(self.pc_url)
        self.assertEqual(resp.context_data['event'], self.pc)
        self.assertFalse(resp.context_data['bookings'].exists())
        self.assertTrue(resp.context_data['can_add_more'])

    def test_register_shows_event_bookings(self):
        bookings = mommy.make_recipe('booking.booking', status='OPEN', event=self.pc, _quantity=2)
        mommy.make_recipe('booking.booking', status='OPEN', event=self.ev, _quantity=3)
        resp = self.client.get(self.pc_url)
        self.assertEqual(
            sorted([booking.id for booking in resp.context_data['bookings']]),
            sorted([booking.id for booking in bookings]))

    def test_cancelled_bookings_not_shown(self):
        bookings = mommy.make_recipe('booking.booking', status='OPEN', event=self.pc, _quantity=2)
        mommy.make_recipe('booking.booking', status='CANCELLED', event=self.pc, _quantity=2)
        resp = self.client.get(self.pc_url)
        self.assertEqual(
            sorted([booking.id for booking in resp.context_data['bookings']]),
            sorted([booking.id for booking in bookings]))

    def test_no_show_bookings_shown(self):
        bookings = mommy.make_recipe('booking.booking', status='OPEN', event=self.pc, _quantity=2)
        no_show_bookings = mommy.make_recipe('booking.booking', status='OPEN', no_show=True, event=self.pc, _quantity=1)
        resp = self.client.get(self.pc_url)
        self.assertEqual(
            sorted([booking.id for booking in resp.context_data['bookings']]),
            sorted([booking.id for booking in bookings + no_show_bookings]))

    def test_full_event_shows_no_new_booking_button(self):
        mommy.make_recipe('booking.booking', status='OPEN', event=self.pc, _quantity=2)
        resp = self.client.get(self.pc_url)
        self.assertTrue(resp.context_data['can_add_more'])

        mommy.make_recipe('booking.booking', status='OPEN', event=self.pc)
        resp = self.client.get(self.pc_url)
        self.assertFalse(resp.context_data['can_add_more'])

    def test_with_available_block_type_for_event(self):
        mommy.make(BlockType, event_type=self.pc.event_type)
        resp = self.client.get(self.pc_url)
        self.assertTrue(resp.context_data['available_block_type'])

    def test_status_choices(self):
        open_bookings = mommy.make_recipe('booking.booking', status='OPEN', event=self.pc, _quantity=2)
        cancelled_bookings = mommy.make_recipe('booking.booking', status='CANCELLED', event=self.pc, _quantity=2)

        resp = self.client.get(self.pc_url + '?status_choice=CANCELLED')
        self.assertEqual(
            sorted([booking.id for booking in resp.context_data['bookings']]),
            sorted([booking.id for booking in cancelled_bookings])
        )

        resp = self.client.get(self.pc_url + '?status_choice=OPEN')
        self.assertEqual(
            sorted([booking.id for booking in resp.context_data['bookings']]),
            sorted([booking.id for booking in open_bookings])
        )

        resp = self.client.get(self.pc_url + '?status_choice=ALL')
        self.assertEqual(
            sorted([booking.id for booking in resp.context_data['bookings']]),
            sorted([booking.id for booking in open_bookings + cancelled_bookings])
        )


class RegisterAjaxViewsTests(TestPermissionMixin, TestCase):

    pass