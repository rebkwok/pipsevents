# -*- coding: utf-8 -*-
import pytz
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

from unittest.mock import patch
from model_bakery import baker

from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from django.test import TestCase, RequestFactory

from booking.models import Event, Block, BlockType, WaitingListUser
from common.tests.helpers import format_content
from stripe_payments.tests.mock_connector import MockConnector
from studioadmin.views.register import process_event_booking_updates
from studioadmin.forms.register_forms import AddRegisterBookingForm
from studioadmin.tests.test_views.helpers import TestPermissionMixin


class EventRegisterListViewTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.url = reverse('studioadmin:event_register_list')
        cls.lessons_url = reverse('studioadmin:class_register_list')
    
    def setUp(self):
        self.client.force_login(self.staff_user)

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        self.client.logout()
        resp = self.client.get(self.url)
        redirected_url = reverse('account_login') + "?next={}".format(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

        resp = self.client.get(self.lessons_url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_can_access_class_registers_if_instructor(self):
        """
        test that the page can be accessed by a non staff user if in the
        instructors group for both classes and events
        """
        self.client.force_login(self.instructor_user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

        resp = self.client.get(self.lessons_url)
        self.assertEqual(resp.status_code, 200)

    def test_event_context(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context_data['type'], 'events')
        self.assertEqual(
            resp.context_data['sidenav_selection'], 'events_register'
            )
        self.assertIn("Events", resp.rendered_content)

    def test_lesson_context(self):
        resp = self.client.get(self.lessons_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context_data['type'], 'lessons')
        self.assertEqual(
            resp.context_data['sidenav_selection'], 'lessons_register'
            )
        self.assertIn("Classes", resp.rendered_content)

    def test_event_register_list_shows_future_events_only(self):
        baker.make_recipe('booking.future_EV', _quantity=4)
        baker.make_recipe('booking.past_event', _quantity=4)
        resp = self.client.get(self.url)
        self.assertEqual(len(resp.context_data['events']), 4)

    def test_event_register_list_shows_todays_events(self):
        baker.make_recipe('booking.future_EV', _quantity=4)
        baker.make_recipe('booking.past_event', _quantity=4)
        past_today = baker.make_recipe('booking.past_event', date=timezone.now().replace(hour=0, minute=1))
        resp = self.client.get(self.url)
        self.assertEqual(len(resp.context_data['events']), 5)

    def test_event_register_list_shows_events_only(self):
        baker.make_recipe('booking.future_EV', _quantity=4)
        baker.make_recipe('booking.future_PC', _quantity=5)
        resp = self.client.get(self.url)
        self.assertEqual(len(resp.context_data['events']), 4)

    def test_class_register_list_excludes_events(self):
        baker.make_recipe('booking.future_EV', _quantity=4)
        baker.make_recipe('booking.future_PC', _quantity=5)
        resp = self.client.get(self.lessons_url)
        self.assertEqual(len(resp.context_data['events']), 5)

    def test_class_register_list_shows_room_hire_with_classes(self):
        baker.make_recipe('booking.future_EV', _quantity=4)
        baker.make_recipe('booking.future_PC', _quantity=5)
        baker.make_recipe('booking.future_RH', _quantity=5)

        resp = self.client.get(self.lessons_url)
        self.assertEqual(len(resp.context_data['events']), 10)

    def test_event_register_list_shows_correct_booking_count(self):
        event = baker.make_recipe('booking.future_EV')
        baker.make_recipe('booking.booking', event=event, _quantity=2)
        baker.make_recipe('booking.booking', event=event, status='CANCELLED')
        baker.make_recipe('booking.booking', event=event, no_show=True)
        resp = self.client.get(self.url)
        self.assertIn(
            '{} {} 2'.format(
                event.date.astimezone(
                    pytz.timezone('Europe/London')
                ).strftime('%a %d %b, %H:%M'), event.name,
            ),
            format_content(resp.rendered_content)
        )


class RegisterViewTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.pc = baker.make_recipe('booking.future_PC', max_participants=3)
        cls.pc_no_max = baker.make_recipe('booking.future_PC')
        cls.ev = baker.make_recipe('booking.future_EV', max_participants=3)
        cls.pc_url = reverse('studioadmin:event_register', args=(cls.pc.slug,))
        cls.pc_no_max_url = reverse('studioadmin:event_register', args=(cls.pc_no_max.slug,))
        cls.ev_url = reverse('studioadmin:event_register', args=(cls.ev.slug,))
        cls.ot = baker.make_recipe('booking.future_OT', max_participants=3)
        cls.ot_url = reverse('studioadmin:event_register', args=(cls.ot.slug,))

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

        resp = self.client.get(self.ot_url)
        self.assertEqual(resp.context_data['sidenav_selection'], 'online_tutorials_register')

    def test_register_no_bookings(self):
        resp = self.client.get(self.pc_url)
        self.assertEqual(resp.context_data['event'], self.pc)
        self.assertFalse(resp.context_data['bookings'].exists())
        self.assertTrue(resp.context_data['can_add_more'])

    def test_register_shows_event_bookings(self):
        bookings = baker.make_recipe('booking.booking', status='OPEN', event=self.pc, _quantity=2)
        baker.make_recipe('booking.booking', status='OPEN', event=self.ev, _quantity=3)
        resp = self.client.get(self.pc_url)
        self.assertEqual(
            sorted([booking.id for booking in resp.context_data['bookings']]),
            sorted([booking.id for booking in bookings]))

    def test_cancelled_bookings_not_shown(self):
        bookings = baker.make_recipe('booking.booking', status='OPEN', event=self.pc, _quantity=2)
        baker.make_recipe('booking.booking', status='CANCELLED', event=self.pc, _quantity=2)
        resp = self.client.get(self.pc_url)
        self.assertEqual(
            sorted([booking.id for booking in resp.context_data['bookings']]),
            sorted([booking.id for booking in bookings]))

    def test_confirmed_no_show_bookings_shown(self):
        bookings = baker.make_recipe('booking.booking', status='OPEN', event=self.pc, _quantity=2)
        no_show_booking = baker.make_recipe('booking.booking', status='OPEN', no_show=True, event=self.pc)
        resp = self.client.get(self.pc_url)
        assert sorted([booking.id for booking in resp.context_data['bookings']]) == sorted([bk.id for bk in bookings])

        # confirmed no-shows are shown
        no_show_booking.instructor_confirmed_no_show = True
        no_show_booking.save()
        resp = self.client.get(self.pc_url)
        assert sorted([booking.id for booking in resp.context_data['bookings']]) == \
               sorted([bk.id for bk in [*bookings, no_show_booking]])

    def test_full_event_shows_no_new_booking_button(self):
        baker.make_recipe('booking.booking', status='OPEN', event=self.pc, _quantity=2)
        resp = self.client.get(self.pc_url)
        self.assertTrue(resp.context_data['can_add_more'])

        baker.make_recipe('booking.booking', status='OPEN', event=self.pc)
        resp = self.client.get(self.pc_url)
        self.assertFalse(resp.context_data['can_add_more'])

    def test_with_available_block_type_for_event(self):
        baker.make(BlockType, event_type=self.pc.event_type, duration=1)
        resp = self.client.get(self.pc_url)
        self.assertTrue(resp.context_data['available_block_type'])

    def test_status_choices(self):
        open_bookings = baker.make_recipe('booking.booking', status='OPEN', event=self.pc, _quantity=2)
        cancelled_bookings = baker.make_recipe('booking.booking', status='CANCELLED', event=self.pc, _quantity=2)
        no_shows =  baker.make_recipe(
            'booking.booking', status='OPEN', no_show=True, event=self.pc, instructor_confirmed_no_show=True, _quantity=2
        )
        late_cancel =  baker.make_recipe(
            'booking.booking', status='OPEN', no_show=True, event=self.pc, instructor_confirmed_no_show=False, _quantity=2
        )

        resp = self.client.get(self.pc_url + '?status_choice=CANCELLED')
        self.assertEqual(
            sorted([booking.id for booking in resp.context_data['bookings']]),
            sorted([booking.id for booking in cancelled_bookings + late_cancel])
        )

        resp = self.client.get(self.pc_url + '?status_choice=OPEN')
        self.assertEqual(
            sorted([booking.id for booking in resp.context_data['bookings']]),
            sorted([booking.id for booking in open_bookings + no_shows])
        )

        resp = self.client.get(self.pc_url + '?status_choice=NO_SHOWS')
        self.assertEqual(
            sorted([booking.id for booking in resp.context_data['bookings']]),
            sorted([booking.id for booking in no_shows])
        )

        resp = self.client.get(self.pc_url + '?status_choice=LATE_CANCELLATIONS')
        self.assertEqual(
            sorted([booking.id for booking in resp.context_data['bookings']]),
            sorted([booking.id for booking in late_cancel])
        )

        resp = self.client.get(self.pc_url + '?status_choice=ALL')
        self.assertEqual(
            sorted([booking.id for booking in resp.context_data['bookings']]),
            sorted([booking.id for booking in [*open_bookings, *cancelled_bookings, *no_shows, *late_cancel]])
        )

        resp = self.client.get(self.pc_url + '?status_choice=INVALID_CHOICE')
        self.assertEqual(
            sorted([booking.id for booking in resp.context_data['bookings']]),
            sorted([booking.id for booking in [*open_bookings, *cancelled_bookings, *no_shows, *late_cancel]])
        )


class RegisterAjaxAddBookingViewsTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        baker.make("stripe_payments.Seller", site=Site.objects.get_current())
        cls.pc = baker.make_recipe('booking.future_PC', max_participants=3)
        cls.ev = baker.make_recipe('booking.future_EV', max_participants=3)
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
        booking = baker.make_recipe('booking.booking', user=self.user, event=self.pc, status='CANCELLED')
        self.assertEqual(self.pc.bookings.count(), 1)

        self.client.post(self.pc_url, {'user': booking.user.id})
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'OPEN')
        self.assertFalse(booking.no_show)

    def test_reopen_no_show_booking(self):
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=self.pc, status='OPEN', no_show=True,
            instructor_confirmed_no_show=True
        )
        self.assertEqual(self.pc.bookings.count(), 1)

        self.client.post(self.pc_url, {'user': booking.user.id})
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'OPEN')
        self.assertFalse(booking.no_show)
        assert booking.instructor_confirmed_no_show is False

    def test_user_choices(self):
        user = baker.make_recipe('booking.user')
        user1 = baker.make_recipe('booking.user')
        user2 = baker.make_recipe('booking.user')
        # open booking
        baker.make_recipe('booking.booking', user=self.user, event=self.pc, status='OPEN')
        # no_show_booking
        baker.make_recipe('booking.booking', user=user, event=self.pc, status='OPEN', no_show=True)
        # cancelled_booking
        baker.make_recipe('booking.booking', user=user1, event=self.pc, status='CANCELLED')

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
        baker.make_recipe('booking.booking', user=self.user, event=self.pc, status='OPEN')

        # try to process the form
        factory = RequestFactory()
        request = factory.get(self.pc_url)
        process_event_booking_updates(form, self.pc, request)

        mock_messages.assert_called_once_with(request, 'Open booking for this user already exists')

    def test_full_class(self):
        baker.make_recipe('booking.booking', event=self.pc, _quantity=3)
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
        baker.make_recipe('booking.booking', event=self.ev, _quantity=3)
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
        baker.make_recipe('booking.block', user=self.user)  # block for different event type

        self.client.post(self.pc_url, {'user': self.user.id})
        booking = self.pc.bookings.first()
        self.assertEqual(booking.user, self.user)
        self.assertIsNone(booking.block)
        self.assertFalse(booking.paid)

        booking.status = 'CANCELLED'
        booking.save()

        block_type = baker.make_recipe('booking.blocktype5', event_type=self.pc.event_type)
        block = baker.make_recipe('booking.block', user=self.user, block_type=block_type, paid=True)
        self.client.post(self.pc_url, {'user': self.user.id})
        booking = self.pc.bookings.first()
        self.assertEqual(booking.user, self.user)
        self.assertEqual(booking.block, block)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)

    @patch("booking.models.membership_models.StripeConnector", MockConnector)
    def test_assigns_available_membership(self):
        assert not self.pc.bookings.exists()
        membership = baker.make('booking.Membership', name="mem")
        baker.make("booking.MembershipItem", membership=membership, event_type=self.pc.event_type, quantity=2)
        user_membership = baker.make('booking.UserMembership', user=self.user, membership=membership, subscription_status="active")
        assert user_membership.valid_for_event(self.pc)

        self.client.post(self.pc_url, {'user': self.user.id})
        booking = self.pc.bookings.first()
        assert booking.user == self.user
        assert booking.block is None
        assert booking.membership == user_membership
        assert booking.paid

    def test_remove_user_from_waiting_list(self):
        baker.make(WaitingListUser, user=self.user, event=self.pc)
        self.assertEqual(WaitingListUser.objects.count(), 1)

        self.client.post(self.pc_url, {'user': self.user.id})
        self.assertFalse(WaitingListUser.objects.exists())


class RegisterAjaxDisplayUpdateTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.pc = baker.make_recipe('booking.future_PC', max_participants=3)
        cls.block_type = baker.make(BlockType, size=2, duration=4, event_type=cls.pc.event_type)

    def setUp(self):
        super().setUp()
        self.client.login(username=self.staff_user.username, password='test')
        self.booking = baker.make_recipe('booking.booking', user=self.user, event=self.pc)
        self.toggle_attended_url = reverse('studioadmin:toggle_attended', args=(self.booking.id,))

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
        assert resp.json()['attended'] is True
        assert resp.json()['alert_msg'] is None

        self.booking.refresh_from_db()
        assert self.booking.attended
        assert self.booking.no_show is False
        assert self.booking.instructor_confirmed_no_show is False

    def test_ajax_toggle_attended_unset(self):
        # post once to set
        resp = self.client.post(self.toggle_attended_url,  {'attendance': 'attended'})
        self.booking.refresh_from_db()
        assert self.booking.attended
        
        # post again to unset
        resp = self.client.post(self.toggle_attended_url,  {'attendance': 'attended'})
        self.booking.refresh_from_db()
        assert resp.json()['attended'] is False
        assert resp.json()['unset'] is True
        assert resp.json()['alert_msg'] is None
        assert not self.booking.attended
        assert not self.booking.no_show
        assert not self.booking.instructor_confirmed_no_show

    def test_ajax_toggle_no_show_unset(self):
        # booking within 1 hr, so will be marked as instructor confirmed
        self.booking.event.date = timezone.now() - timedelta(seconds=55)
        self.booking.event.save()

        # post once to set
        resp = self.client.post(self.toggle_attended_url,  {'attendance': 'no-show'})
        self.booking.refresh_from_db()
        assert not self.booking.attended
        assert self.booking.no_show
        assert self.booking.instructor_confirmed_no_show
        
        # post again to unset
        resp = self.client.post(self.toggle_attended_url,  {'attendance': 'no-show'})
        self.booking.refresh_from_db()
        assert resp.json()['attended'] is False
        assert resp.json()['unset'] is True
        assert resp.json()['alert_msg'] is None
        assert not self.booking.attended
        assert not self.booking.no_show
        assert not self.booking.instructor_confirmed_no_show

    def test_ajax_toggle_no_show(self):
        resp = self.client.post(self.toggle_attended_url, {'attendance': 'no-show'})
        assert resp.json()['attended'] is False
        assert resp.json()['alert_msg'] is None

        self.booking.refresh_from_db()
        assert self.booking.attended is False
        assert self.booking.no_show
        assert self.booking.instructor_confirmed_no_show is False

    def test_toggle_no_show_within_one_hour_of_class(self):
        self.booking.event.date = timezone.now() - timedelta(seconds=55)
        self.booking.event.save()
        self.client.post(self.toggle_attended_url, {'attendance': 'no-show'})
        self.booking.refresh_from_db()
        assert self.booking.attended is False
        assert self.booking.no_show
        assert self.booking.instructor_confirmed_no_show is True

        self.client.post(self.toggle_attended_url, {'attendance': 'attended'})
        self.booking.refresh_from_db()
        assert self.booking.attended
        assert self.booking.no_show is False
        assert self.booking.instructor_confirmed_no_show is False

        self.booking.event.date = timezone.now() + timedelta(seconds=55)
        self.booking.event.save()
        self.client.post(self.toggle_attended_url, {'attendance': 'no-show'})
        self.booking.refresh_from_db()
        assert self.booking.attended is False
        assert self.booking.no_show
        assert self.booking.instructor_confirmed_no_show is True

    def test_ajax_toggle_no_show_send_waiting_list_email_for_full_event(self):
        baker.make_recipe('booking.booking', event=self.pc, _quantity=2)
        pc = Event.objects.get(id=self.pc.id)
        self.assertEqual(pc.spaces_left, 0)
        baker.make(WaitingListUser, user__email="waitinglist@user.com", event=self.pc)

        self.client.post(self.toggle_attended_url, {'attendance': 'no-show'})
        self.booking.refresh_from_db()
        self.assertFalse(self.booking.attended)
        self.assertTrue(self.booking.no_show)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].bcc, ["waitinglist@user.com"])

    def test_ajax_toggle_no_show_no_waiting_list_email_for_full_event_within_1_hour(self):
        baker.make_recipe('booking.booking', event=self.pc, _quantity=2)
        pc = Event.objects.get(id=self.pc.id)
        self.assertEqual(pc.spaces_left, 0)
        baker.make(WaitingListUser, user__email="waitinglist@user.com", event=self.pc)

        pc.date = timezone.now() + timedelta(minutes=58)
        pc.save()
        self.client.post(self.toggle_attended_url, {'attendance': 'no-show'})
        self.booking.refresh_from_db()
        self.assertFalse(self.booking.attended)
        self.assertTrue(self.booking.no_show)
        # No waiting list email for events within 1 hr of current time
        self.assertEqual(len(mail.outbox), 0)

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
        baker.make_recipe('booking.booking', event=self.pc, _quantity=2)
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
        baker.make_recipe('booking.booking', event=self.pc, _quantity=3)
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
        baker.make_recipe('booking.booking', event=self.pc, _quantity=3)
        pc = Event.objects.get(id=self.pc.id)
        self.assertEqual(pc.spaces_left, 0)
        resp = self.client.post(self.toggle_attended_url, {'attendance': 'attended'})
        self.assertFalse(resp.json()['attended'])
        self.assertEqual(resp.json()['alert_msg'], 'Class is now full, cannot reopen booking.')

        self.booking.refresh_from_db()
        self.assertFalse(self.booking.attended)
        self.assertTrue(self.booking.no_show)


class RegisterByDateTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.url = reverse('studioadmin:register-day')
    
    def setUp(self):
        self.client.force_login(self.staff_user)

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        self.client.logout()
        resp = self.client.get(self.url)
        redirected_url = reverse('account_login') + "?next={}".format(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    @patch('studioadmin.forms.register_forms.date')
    @patch('studioadmin.views.register.datetime')
    def test_events_and_classes_in_form_for_instructors(
            self, mock_tz, mock_date
    ):
        self.client.force_login(self.instructor_user)
        mock_tz.now.return_value = datetime(
            year=2015, month=9, day=7, hour=10, tzinfo=dt_timezone.utc
        )
        mock_date.today.return_value = date(year=2015, month=9, day=7)
        events = baker.make_recipe(
            'booking.future_EV',
            date=datetime(
                year=2015, month=9, day=7,
                hour=18, minute=0, tzinfo=dt_timezone.utc
            ),
            _quantity=3
        )
        pole_classes = baker.make_recipe(
            'booking.future_PC',
            date=datetime(
                year=2015, month=9, day=7,
                hour=18, minute=0, tzinfo=dt_timezone.utc
            ),
            _quantity=3
        )
        resp = self.client.get(self.url)

        form = resp.context_data['form']
        self.assertEqual(len(form.events), 6)

        all_events = events + pole_classes
        self.assertEqual(
            sorted([ev.id for ev in form.events]),
            sorted([ev.id for ev in all_events])
        )

    def test_show_events_by_selected_date(self):

        events = baker.make_recipe(
            'booking.future_EV',
            date=datetime(
                year=2015, month=9, day=7,
                hour=18, minute=0, tzinfo=dt_timezone.utc
            ),
            _quantity=3
        )
        baker.make_recipe(
            'booking.future_EV',
            date=datetime(
                year=2015, month=9, day=6,
                hour=18, minute=0, tzinfo=dt_timezone.utc
            ),
            _quantity=3
        )
        data = {
            'register_date': 'Mon 07 Sep 2015',
            'exclude_ext_instructor': True,
            'register_format': 'full',
            'show': 'show'
        }
        resp = self.client.post(self.url, data)
        self.assertEqual(Event.objects.count(), 6)

        form = resp.context_data['form']
        self.assertIn('select_events', form.fields)
        selected_events = form.fields['select_events'].choices

        self.assertCountEqual(
            [ev[0] for ev in selected_events],
            [event.id for event in events]
        )

    def test_show_events_by_selected_date_for_instructor(self):
        self.client.force_login(self.instructor_user)
        events = baker.make_recipe(
            'booking.future_EV',
            date=datetime(
                year=2015, month=9, day=7,
                hour=18, minute=0, tzinfo=dt_timezone.utc
            ),
            _quantity=3
        )
        pole_classes = baker.make_recipe(
            'booking.future_CL',
            date=datetime(
                year=2015, month=9, day=7,
                hour=18, minute=0, tzinfo=dt_timezone.utc
            ),
            _quantity=3
        )
        baker.make_recipe(
            'booking.future_EV',
            date=datetime(
                year=2015, month=9, day=6,
                hour=18, minute=0, tzinfo=dt_timezone.utc
            ),
            _quantity=3
        )
        baker.make_recipe(
            'booking.future_CL',
            date=datetime(
                year=2015, month=9, day=6,
                hour=18, minute=0, tzinfo=dt_timezone.utc
            ),
            _quantity=3
        )

        data = {
                'register_date': 'Mon 07 Sep 2015',
                'exclude_ext_instructor': True,
                'register_format': 'full',
                'show': 'show'
        }
        resp = self.client.post(self.url, data)
        
        self.assertEqual(Event.objects.count(), 12)

        form = resp.context_data['form']
        self.assertIn('select_events', form.fields)
        selected_events = form.fields['select_events'].choices

        selected = pole_classes + events
        self.assertEqual(
            sorted([ev[0] for ev in selected_events]),
            sorted([event.id for event in selected])
        )

    def test_no_events_on_selected_date(self):
        baker.make_recipe(
            'booking.future_EV',
            date=datetime(
                year=2015, month=9, day=7,
                hour=18, minute=0, tzinfo=dt_timezone.utc
            ),
            _quantity=3
        )

        data = {
            'register_date': 'Mon 06 Sep 2015',
            'exclude_ext_instructor': True,
            'register_format': 'full',
            'show': 'show'
        }
        resp = self.client.post(self.url, data, follow=True)
        self.assertEqual(Event.objects.count(), 3)

        content = format_content(resp.rendered_content)
        self.assertIn(
            'There are no classes/workshops/events on the date selected',
            content
        )

    def test_no_events_selected_to_print(self):
        baker.make_recipe(
            'booking.future_EV',
            date=datetime(
                year=2015, month=9, day=7,
                hour=18, minute=0, tzinfo=dt_timezone.utc
            ),
            _quantity=3
        )

        url = reverse('studioadmin:register-day')
        data = {
            'register_date': 'Mon 07 Sep 2015',
            'exclude_ext_instructor': True,
            'register_format': 'full',
            'print': 'print'
        }
        resp = self.client.post(self.url, data, follow=True)
        self.assertEqual(Event.objects.count(), 3)

        content = format_content(resp.rendered_content)
        self.assertIn(
            'Please select at least one register to print',
            content
        )

    def test_print_selected_events(self):
        events = baker.make_recipe(
            'booking.future_EV',
            date=datetime(
                year=2015, month=9, day=7,
                hour=18, minute=0, tzinfo=dt_timezone.utc
            ),
            _quantity=3
        )

        data = {
            'register_date': 'Mon 07 Sep 2015',
            'exclude_ext_instructor': True,
            'register_format': 'full',
            'print': 'print',
            'select_events': [events[0].id, events[1].id]
        }
        resp = self.client.post(self.url, data)
        self.assertEqual(len(resp.context_data['events']), 2)

        for event in resp.context_data['events']:
            self.assertTrue(event['event'] in [events[0], events[1]])

    def test_print_unselected_events(self):
        """
        If no events selected (i.e. print button pressed without using the
        "show classes" button first), all events for that date are printed,
         with exception of ext instructor classes which are based on the
         checkbox value
        """
        events = baker.make_recipe(
            'booking.future_EV',
            date=datetime(
                year=2015, month=9, day=7,
                hour=18, minute=0, tzinfo=dt_timezone.utc
            ),
            _quantity=3
        )

        data = {
                'register_date': 'Mon 07 Sep 2015',
                'exclude_ext_instructor': True,
                'register_format': 'full',
                'print': 'print',
                'select_events': [event.id for event in events]
        }
        resp = self.client.post(self.url, data)
        self.assertEqual(len(resp.context_data['events']), 3)

        for event in resp.context_data['events']:
            self.assertTrue(event['event'] in events)

    def test_print_open_bookings_for_events(self):
        event1 = baker.make_recipe(
            'booking.future_EV',
            name="event1",
            date=datetime(
                year=2015, month=9, day=7,
                hour=18, minute=0, tzinfo=dt_timezone.utc
            ),
        )
        event2 = baker.make_recipe(
            'booking.future_EV',
            name='event2',
            date=datetime(
                year=2015, month=9, day=7,
                hour=19, minute=0, tzinfo=dt_timezone.utc
            ),
        )

        ev1_bookings = baker.make_recipe(
            'booking.booking',
            event=event1,
            _quantity=2
        )
        ev1_cancelled_booking = baker.make_recipe(
            'booking.booking',
            event=event2,
            status='CANCELLED'
        )
        ev2_bookings = baker.make_recipe(
            'booking.booking',
            event=event1,
            _quantity=2
        )

        data = {
            'register_date': 'Mon 07 Sep 2015',
            'exclude_ext_instructor': True,
            'register_format': 'full',
            'print': 'print',
            'select_events': [event1.id, event2.id]
        }
        resp = self.client.post(self.url, data)

        self.assertEqual(len(resp.context_data['events']), 2)

        for event in resp.context_data['events']:
            self.assertTrue(event['event'] in [event1, event2])
            for booking in event['bookings']:
                self.assertTrue(booking['booking'] in event['event'].bookings.all())

    def test_print_extra_lines(self):
        event1 = baker.make_recipe(
            'booking.future_EV',
            name="event1",
            date=datetime(
                year=2015, month=9, day=7,
                hour=18, minute=0, tzinfo=dt_timezone.utc
            ),
            max_participants=10,
        )

        ev1_bookings = baker.make_recipe(
            'booking.booking',
            event=event1,
            _quantity=2
        )
        ev1_cancelled_booking = baker.make_recipe(
            'booking.booking',
            event=event1,
            status='CANCELLED'
        )

        # event has max_participants; extra lines are max - open bookings
        data = {
            'register_date': 'Mon 07 Sep 2015',
            'exclude_ext_instructor': True,
            'register_format': 'full',
            'print': 'print',
            'select_events': [event1.id]
        }
        resp = self.client.post(self.url, data)

        self.assertEqual(len(resp.context_data['events']), 1)
        self.assertEqual(resp.context_data['events'][0]['extra_lines'], 8)

        event1.max_participants = None
        event1.save()
        # event has no max_participants and <15 bookings; extra lines are
        # 15 - open bookings
        data = {
            'register_date': 'Mon 07 Sep 2015',
            'exclude_ext_instructor': True,
            'register_format': 'full',
            'print': 'print',
            'select_events': [event1.id]
        }
        resp = self.client.post(self.url, data)

        self.assertEqual(len(resp.context_data['events']), 1)
        self.assertEqual(resp.context_data['events'][0]['extra_lines'], 13)

        baker.make_recipe('booking.booking', event=event1,  _quantity=14)
        # event has no max_participants and >15 bookings; extra lines = 2
        data = {
            'register_date': 'Mon 07 Sep 2015',
            'exclude_ext_instructor': True,
            'register_format': 'full',
            'print': 'print',
            'select_events': [event1.id]
        }
        resp = self.client.post(self.url, data)

        self.assertEqual(len(resp.context_data['events']), 1)
        self.assertEqual(resp.context_data['events'][0]['extra_lines'], 2)

    def test_print_format_no_available_blocktype(self):
        event = baker.make_recipe(
            'booking.future_EV',
            name="event1",
            date=datetime(
                year=2015, month=9, day=7,
                hour=18, minute=0, tzinfo=dt_timezone.utc
            ),
        )

        data = {
            'register_date': 'Mon 07 Sep 2015',
            'exclude_ext_instructor': True,
            'register_format': 'full',
            'print': 'print',
            'select_events': [event.id]
        }
        resp = self.client.post(self.url, data)

        self.assertEqual(len(resp.context_data['events']), 1)
        # check correct headings are present
        self.assertIn('>Attended<', resp.rendered_content)
        self.assertIn('>Status<', resp.rendered_content)
        self.assertIn('>User<', resp.rendered_content)
        self.assertIn('>Deposit Paid<', resp.rendered_content)
        self.assertIn('>Fully Paid<', resp.rendered_content)

        data = {
            'register_date': 'Mon 07 Sep 2015',
            'exclude_ext_instructor': True,
            'register_format': 'namesonly',
            'print': 'print',
            'select_events': [event.id]
        }
        resp = self.client.post(self.url, data)

        self.assertEqual(len(resp.context_data['events']), 1)
        # check correct headings are present
        self.assertIn('>Attended<', resp.rendered_content)
        self.assertIn('>User<', resp.rendered_content)
        self.assertNotIn('>Status<', resp.rendered_content)
        self.assertNotIn('>Deposit Paid<', resp.rendered_content)
        self.assertNotIn('>Fully Paid<', resp.rendered_content)

    def test_print_format_with_available_blocktype(self):
        event = baker.make_recipe(
            'booking.future_EV',
            name="event1",
            date=datetime(
                year=2015, month=9, day=7,
                hour=18, minute=0, tzinfo=dt_timezone.utc
            ),
        )

        baker.make_recipe(
            'booking.blocktype',
            event_type=event.event_type
        )

        data = {
            'register_date': 'Mon 07 Sep 2015',
            'exclude_ext_instructor': True,
            'register_format': 'full',
            'print': 'print',
            'select_events': [event.id]
        }
        resp = self.client.post(self.url, data)

        self.assertEqual(len(resp.context_data['events']), 1)
        # check correct headings are present
        headings = [
            '>Attended<', 
            '>Status<',
            '>Disclaimer<',
            '>User<', 
            '>Deposit Paid<',
            '>Fully Paid<', 
            '>Booked with<br/>block<',
            '>User\'s block</br>expiry date<', 
            '>Block size<',
            '>Block bookings</br>used<'
        ]
        for heading in headings:
            assert heading in resp.rendered_content
        data = {
            'register_date': 'Mon 07 Sep 2015',
            'exclude_ext_instructor': True,
            'register_format': 'namesonly',
            'print': 'print',
            'select_events': [event.id]
        }
        resp = self.client.post(self.url, data, follow=True)

        self.assertEqual(len(resp.context_data['events']), 1)
        # check correct headings are present
        for heading in ['>Attended<', '>User<', '>Disclaimer<']:
            assert heading in resp.rendered_content

        for heading in [
            '>Status<',
            '>Deposit Paid<',
            '>Fully Paid<', 
            '>Booked with<br/>block<',
            '>User\'s block</br>expiry date<', 
            '>Block size<',
            '>Block bookings</br>used<'
        ]:
            assert heading not in resp.rendered_content    

    def test_print_with_invalid_date_format(self):
        baker.make_recipe(
            'booking.future_EV',
            date=datetime(
                year=2015, month=9, day=7,
                hour=18, minute=0, tzinfo=dt_timezone.utc
            ),
        )
        data = {
            'register_date': 'Mon 33 Sep 2015',
            'exclude_ext_instructor': True,
            'register_format': 'full',
            'print': 'print'
        }
        resp = self.client.post(self.url, data, follow=True)

        content = format_content(resp.rendered_content)
        self.assertIn(
            'Please correct the following errors: register_date',
            content
        )
