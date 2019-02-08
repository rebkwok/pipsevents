# -*- coding: utf-8 -*-
import pytz
from datetime import  date, datetime

from unittest.mock import patch
from model_mommy import mommy

from django.contrib.auth.models import User
from django.contrib import messages
from django.urls import reverse
from django.test import RequestFactory, TestCase

from booking.models import Event, Booking, Block, BlockType, WaitingListUser
from common.tests.helpers import _create_session, format_content
from studioadmin.views import (
    register_view_new, booking_register_add_view, ajax_toggle_attended,
    ajax_toggle_paid, ajax_assign_block
)
from studioadmin.views.register import process_event_booking_updates
from studioadmin.forms.register_forms import AddRegisterBookingForm
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


class RegisterAjaxAddBookingViewsTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.pc = mommy.make_recipe('booking.future_PC', max_participants=3)
        cls.ev = mommy.make_recipe('booking.future_EV', max_participants=3)
        cls.pc_url = reverse('studioadmin:bookingregisteradd', args=(cls.pc.id,))
        cls.ev_url = reverse('studioadmin:bookingregisteradd', args=(cls.ev.id,))

    def setUp(self):
        super().setUp()
        self.client.login(username=self.staff_user.username, password='test')

    def test_add_booking_user_permissions(self):
        self.client.logout()
        resp = self.client.get(self.pc_url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('account_login') + "?next={}".format(self.pc_url))

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

    def test_add_booking(self):
        self.assertFalse(self.pc.bookings.exists())
        self.client.post(self.pc_url, {'user': self.user.id})
        booking = self.pc.bookings.first()
        self.assertEqual(booking.user.id, self.user.id)
        self.assertEqual(booking.status, 'OPEN')
        self.assertFalse(booking.no_show)
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)

    def test_reopen_cancelled_booking(self):
        booking = mommy.make_recipe('booking.booking', user=self.user, event=self.pc, status='CANCELLED')
        self.assertEqual(self.pc.bookings.count(), 1)

        self.client.post(self.pc_url, {'user': booking.user.id})
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'OPEN')
        self.assertFalse(booking.no_show)

    def test_reopen_no_show_booking(self):
        booking = mommy.make_recipe('booking.booking', user=self.user, event=self.pc, status='OPEN', no_show=True)
        self.assertEqual(self.pc.bookings.count(), 1)

        self.client.post(self.pc_url, {'user': booking.user.id})
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'OPEN')
        self.assertFalse(booking.no_show)

    def test_user_choices(self):
        user = mommy.make_recipe('booking.user')
        user1 = mommy.make_recipe('booking.user')
        user2 = mommy.make_recipe('booking.user')
        # open booking
        mommy.make_recipe('booking.booking', user=self.user, event=self.pc, status='OPEN')
        # no_show_booking
        mommy.make_recipe('booking.booking', user=user, event=self.pc, status='OPEN', no_show=True)
        # cancelled_booking
        mommy.make_recipe('booking.booking', user=user1, event=self.pc, status='CANCELLED')

        # form shows users with cancelled, no-show or no bookings
        form = AddRegisterBookingForm(event=self.pc)
        self.assertEqual(
            sorted([choice[0] for choice in form.fields['user'].choices]),
            sorted([user.id for user in User.objects.exclude(id=self.user.id)])
        )

    @patch('studioadmin.views.register.messages.info')
    def test_already_open_booking(self, mock_messages):
        # The user choices in the form exclude users with open bookings already, but we could post a form with an open
        # booking if the booking was made in another session and the add booking forw was still open

        # get the user form
        form = AddRegisterBookingForm({'user': self.user.id}, event=self.pc)
        self.assertTrue(form.is_valid())

        # make booking for this user
        mommy.make_recipe('booking.booking', user=self.user, event=self.pc, status='OPEN')

        # try to process the form
        request = self.factory.get(self.pc_url)
        process_event_booking_updates(form, self.pc, request)

        mock_messages.assert_called_once_with(request, 'Open booking for this user already exists')

    def test_full_class(self):
        mommy.make_recipe('booking.booking', event=self.pc, _quantity=3)
        # fetch from db again b/c spaces left is cached
        pc = Event.objects.get(id=self.pc.id)
        self.assertEqual(pc.spaces_left, 0)
        resp = self.client.post(self.pc_url, {'user': self.user.id})
        form = resp.context_data['form']
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.non_field_errors(),
            ['Class is now full, booking could not be created. Please close this window and refresh register page.']
        )

    def test_full_event(self):
        mommy.make_recipe('booking.booking', event=self.ev, _quantity=3)
        # fetch from db again b/c spaces left is cached
        ev = Event.objects.get(id=self.ev.id)
        self.assertEqual(ev.spaces_left, 0)
        resp = self.client.post(self.ev_url, {'user': self.user.id})
        form = resp.context_data['form']
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.non_field_errors(),
            ['Event is now full, booking could not be created. Please close this window and refresh register page.']
        )

    def test_assigns_available_block(self):
        self.assertFalse(self.pc.bookings.exists())
        mommy.make_recipe('booking.block', user=self.user)  # block for different event type

        self.client.post(self.pc_url, {'user': self.user.id})
        booking = self.pc.bookings.first()
        self.assertEqual(booking.user, self.user)
        self.assertIsNone(booking.block)
        self.assertFalse(booking.paid)

        booking.status = 'CANCELLED'
        booking.save()

        block_type = mommy.make_recipe('booking.blocktype5', event_type=self.pc.event_type)
        block = mommy.make_recipe('booking.block', user=self.user, block_type=block_type, paid=True)
        self.client.post(self.pc_url, {'user': self.user.id})
        booking = self.pc.bookings.first()
        self.assertEqual(booking.user, self.user)
        self.assertEqual(booking.block, block)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)

    def test_remove_user_from_waiting_list(self):
        mommy.make(WaitingListUser, user=self.user, event=self.pc)
        self.assertEqual(WaitingListUser.objects.count(), 1)

        self.client.post(self.pc_url, {'user': self.user.id})
        self.assertFalse(WaitingListUser.objects.exists())


class RegisterAjaxDisplayUpdateTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.pc = mommy.make_recipe('booking.future_PC', max_participants=3)
        cls.block_type = mommy.make(BlockType, size=2, event_type=cls.pc.event_type)

    def setUp(self):
        super().setUp()
        self.client.login(username=self.staff_user.username, password='test')
        self.booking = mommy.make_recipe('booking.booking', user=self.user, event=self.pc)
        self.assign_block_url = reverse('studioadmin:assign_block', args=(self.booking.id,))
        self.toggle_paid_url = reverse('studioadmin:toggle_paid', args=(self.booking.id,))
        self.toggle_attended_url = reverse('studioadmin:toggle_attended', args=(self.booking.id,))

    def test_ajax_assign_block_get(self):
        # get just returns block display html for current booking
        # no block, not paid
        resp = self.client.get(self.assign_block_url)
        self.assertEqual(resp.context['booking'], self.booking)
        self.assertEqual(resp.context['alert_msg'], {})
        self.assertEqual(resp.context['available_block_type'], True)
        self.assertIn('No active block', resp.content.decode('utf-8'))

        # no block, paid
        self.booking.paid = True
        self.booking.save()
        resp = self.client.get(self.assign_block_url)
        self.assertIn('N/A', resp.content.decode('utf-8'))

        # available block, paid
        block = mommy.make(Block, user=self.user, paid=True, block_type=self.block_type)
        resp = self.client.get(self.assign_block_url)
        self.assertIn('Available block not used', resp.content.decode('utf-8'))

        # available block, not paid
        # We shouldn't get here, because the main register page should be showing the "assign available block" button instead for
        # unpaid bookings, but just in case
        self.booking.paid = False
        self.booking.save()
        resp = self.client.get(self.assign_block_url)
        self.assertIn('Block is available', resp.content.decode('utf-8'))

        # block used
        self.booking.block = block
        self.booking.save()
        resp = self.client.get(self.assign_block_url)
        self.assertIn('{} (1/2 left)'.format(self.pc.event_type.subtype), resp.content.decode('utf-8'))

    def test_ajax_assign_block_post_paid_no_block(self):
        self.booking.paid = True
        self.booking.save()
        resp = self.client.post(self.assign_block_url)
        self.assertEqual(resp.context['booking'], self.booking)
        self.assertEqual(
            resp.context['alert_msg'],
            {'status': 'error', 'msg': 'Booking is already marked as paid; uncheck "Paid" checkbox and try again.'}
        )
        self.assertEqual(resp.context['available_block_type'], True)
        self.assertIn('N/A', resp.content.decode('utf-8'))

    def test_ajax_assign_block_post_paid_with_block_already(self):
        block = mommy.make(Block, user=self.user, paid=True, block_type=self.block_type)
        self.booking.block = block
        self.booking.save()
        resp = self.client.post(self.assign_block_url)
        self.assertEqual(resp.context['booking'], self.booking)
        self.assertEqual(
            resp.context['alert_msg'],
            {'status': 'warning', 'msg': 'Block already assigned.'}
        )

    def test_ajax_assign_block_post_not_paid_no_available_block(self):
        resp = self.client.post(self.assign_block_url)
        self.assertEqual(resp.context['booking'], self.booking)
        self.assertEqual(
            resp.context['alert_msg'],
            {'status': 'error', 'msg': 'No available block to assign.'}
        )
        self.assertEqual(resp.context['available_block_type'], True)
        self.assertIn('No active block', resp.content.decode('utf-8'))

    def test_ajax_assign_block_post_not_paid_block_available(self):
        block = mommy.make(Block, user=self.user, paid=True, block_type=self.block_type)
        self.assertIsNone(self.booking.block)
        resp = self.client.post(self.assign_block_url)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.block, block)
        self.assertEqual(
            resp.context['alert_msg'],
            {'status': 'success', 'msg': 'Block assigned.'}
        )

    def test_ajax_toggle_paid_get(self):
        # get just returns paid status for current booking
        resp = self.client.get(self.toggle_paid_url)
        self.assertCountEqual(
            resp.json(), {'paid': False, 'has_available_block': False, 'alert_msg': {}}
        )

        self.booking.paid = True
        self.booking.save()
        resp = self.client.get(self.toggle_paid_url)
        self.assertCountEqual(
            resp.json(), {'paid': True, 'has_available_block': False, 'alert_msg': {}}
        )

    def test_ajax_toggle_paid_post_toggle_to_paid_paid_without_block(self):
        self.assertFalse(self.booking.paid)
        self.assertFalse(self.booking.payment_confirmed)
        self.assertIsNone(self.booking.block)
        resp = self.client.post(self.toggle_paid_url)
        self.booking.refresh_from_db()
        self.assertTrue(self.booking.paid)
        self.assertTrue(self.booking.payment_confirmed)
        self.assertIsNone(self.booking.block)
        self.assertTrue(resp.json()['paid'])
        self.assertEqual(resp.json()['alert_msg']['status'], 'success')
        self.assertEqual(resp.json()['alert_msg']['msg'], 'Booking set to paid.')

    def test_ajax_toggle_paid_post_toggle_to_paid_with_availble_block(self):
        mommy.make(Block, user=self.user, paid=True, block_type=self.block_type)
        self.assertFalse(self.booking.paid)
        self.assertFalse(self.booking.payment_confirmed)
        self.assertIsNone(self.booking.block)
        resp = self.client.post(self.toggle_paid_url)
        self.booking.refresh_from_db()
        self.assertTrue(self.booking.paid)
        self.assertTrue(self.booking.payment_confirmed)
        self.assertIsNone(self.booking.block)
        self.assertTrue(resp.json()['paid'])
        self.assertEqual(resp.json()['alert_msg']['status'], 'warning')
        self.assertEqual(resp.json()['alert_msg']['msg'], 'Booking set to paid. Available block NOT assigned.')

    def test_ajax_toggle_paid_post_toggle_to_not_paid(self):
        self.booking.paid = True
        self.booking.save()
        resp = self.client.post(self.toggle_paid_url)
        self.booking.refresh_from_db()
        self.assertFalse(self.booking.paid)
        self.assertFalse(self.booking.payment_confirmed)
        self.assertIsNone(self.booking.block)
        self.assertFalse(resp.json()['paid'])
        self.assertEqual(resp.json()['alert_msg']['status'], 'success')
        self.assertEqual(resp.json()['alert_msg']['msg'], 'Booking set to unpaid.')

    def test_ajax_toggle_paid_with_block_post_toggle_to_not_paid(self):
        block = mommy.make(Block, user=self.user, paid=True, block_type=self.block_type)
        self.booking.block = block
        self.booking.save()
        resp = self.client.post(self.toggle_paid_url)
        self.booking.refresh_from_db()
        self.assertFalse(self.booking.paid)
        self.assertFalse(self.booking.payment_confirmed)
        self.assertIsNone(self.booking.block)
        self.assertFalse(resp.json()['paid'])
        self.assertEqual(resp.json()['alert_msg']['status'], 'warning')
        self.assertEqual(resp.json()['alert_msg']['msg'], 'Booking set to unpaid and block unassigned.')

    def test_ajax_toggle_paid_post_not_paid_block_available(self):
        mommy.make(Block, user=self.user, paid=True, block_type=self.block_type)
        self.booking.paid = True
        self.booking.save()
        self.assertIsNone(self.booking.block)
        resp = self.client.post(self.toggle_paid_url)
        self.booking.refresh_from_db()
        self.assertFalse(self.booking.paid)
        self.assertFalse(self.booking.payment_confirmed)
        self.assertIsNone(self.booking.block)
        self.assertFalse(resp.json()['paid'])
        self.assertEqual(resp.json()['alert_msg']['status'], 'success')
        self.assertEqual(resp.json()['alert_msg']['msg'], 'Booking set to unpaid.')

    def test_ajax_toggle_paid_post_free_class(self):
        mommy.make(Block, user=self.user, paid=True, block_type=self.block_type)
        self.booking.paid = True
        self.booking.free_class = True
        self.booking.save()
        self.assertIsNone(self.booking.block)
        resp = self.client.post(self.toggle_paid_url)
        self.booking.refresh_from_db()
        self.assertFalse(self.booking.paid)
        self.assertFalse(self.booking.free_class)
        self.assertFalse(self.booking.payment_confirmed)
        self.assertIsNone(self.booking.block)
        self.assertFalse(resp.json()['paid'])
        self.assertEqual(resp.json()['alert_msg']['status'], 'success')
        self.assertEqual(resp.json()['alert_msg']['msg'], 'Booking set to unpaid.')

    def test_ajax_toggle_attended_get(self):
        # get not allowed
        resp = self.client.get(self.toggle_attended_url)
        self.assertEqual(resp.status_code, 405)

    def test_ajax_toggle_attended_no_data(self):
        resp = self.client.post(self.toggle_attended_url)
        self.assertEqual(resp.status_code, 400)

    def test_ajax_toggle_attended_bad_data(self):
        resp = self.client.post(self.toggle_attended_url, {'attendance': 'foo'})
        self.assertEqual(resp.status_code, 400)

    def test_ajax_toggle_attended(self):
        resp = self.client.post(self.toggle_attended_url,  {'attendance': 'attended'})
        self.assertTrue(resp.json()['attended'])
        self.assertIsNone(resp.json()['alert_msg'])

        self.booking.refresh_from_db()
        self.assertTrue(self.booking.attended)
        self.assertFalse(self.booking.no_show)

    def test_ajax_toggle_no_show(self):
        resp = self.client.post(self.toggle_attended_url, {'attendance': 'no-show'})
        self.assertFalse(resp.json()['attended'])
        self.assertIsNone(resp.json()['alert_msg'])

        self.booking.refresh_from_db()
        self.assertFalse(self.booking.attended)
        self.assertTrue(self.booking.no_show)

    def test_ajax_toggle_attended_cancelled_booking(self):
        self.booking.status = 'CANCELLED'
        self.booking.save()
        resp = self.client.post(self.toggle_attended_url, {'attendance': 'attended'})
        self.assertTrue(resp.json()['attended'])
        self.assertIsNone(resp.json()['alert_msg'])

        self.booking.refresh_from_db()
        self.assertTrue(self.booking.attended)
        self.assertFalse(self.booking.no_show)
        self.assertEqual(self.booking.status, 'OPEN')

    def test_ajax_toggle_attended_no_show_booking(self):
        self.booking.no_show = True
        self.booking.save()
        resp = self.client.post(self.toggle_attended_url, {'attendance': 'attended'})
        self.assertTrue(resp.json()['attended'])
        self.assertIsNone(resp.json()['alert_msg'])

        self.booking.refresh_from_db()
        self.assertTrue(self.booking.attended)
        self.assertFalse(self.booking.no_show)
        self.assertEqual(self.booking.status, 'OPEN')

    def test_ajax_toggle_attended_open_booking_full_event(self):
        mommy.make_recipe('booking.booking', event=self.pc, _quantity=2)
        pc = Event.objects.get(id=self.pc.id)
        self.assertEqual(pc.spaces_left, 0)
        resp = self.client.post(self.toggle_attended_url, {'attendance': 'attended'})
        self.assertTrue(resp.json()['attended'])
        self.assertIsNone(resp.json()['alert_msg'])

        self.booking.refresh_from_db()
        self.assertTrue(self.booking.attended)
        self.assertFalse(self.booking.no_show)

    def test_ajax_toggle_attended_cancelled_booking_full_event(self):
        self.booking.status = 'CANCELLED'
        self.booking.save()
        mommy.make_recipe('booking.booking', event=self.pc, _quantity=3)
        pc = Event.objects.get(id=self.pc.id)
        self.assertEqual(pc.spaces_left, 0)
        resp = self.client.post(self.toggle_attended_url, {'attendance': 'attended'})
        self.assertFalse(resp.json()['attended'])
        self.assertEqual(resp.json()['alert_msg'], 'Class is now full, cannot reopen booking.')

        self.booking.refresh_from_db()
        self.assertFalse(self.booking.attended)
        self.assertFalse(self.booking.no_show)

    def test_ajax_toggle_attended_no_show_booking_full_event(self):
        self.booking.no_show = True
        self.booking.save()
        mommy.make_recipe('booking.booking', event=self.pc, _quantity=3)
        pc = Event.objects.get(id=self.pc.id)
        self.assertEqual(pc.spaces_left, 0)
        resp = self.client.post(self.toggle_attended_url, {'attendance': 'attended'})
        self.assertFalse(resp.json()['attended'])
        self.assertEqual(resp.json()['alert_msg'], 'Class is now full, cannot reopen booking.')

        self.booking.refresh_from_db()
        self.assertFalse(self.booking.attended)
        self.assertTrue(self.booking.no_show)
