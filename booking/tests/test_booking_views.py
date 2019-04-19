# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from unittest.mock import patch
from model_mommy import mommy

from urllib.parse import urlsplit

from django.conf import settings
from django.core import mail
from django.urls import reverse
from django.test import override_settings, TestCase, RequestFactory
from django.contrib.auth.models import Group, Permission, User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone

from activitylog.models import ActivityLog
from accounts.models import OnlineDisclaimer

from booking.models import BlockType, Event, EventType, Booking, \
    Block, EventVoucher,UsedEventVoucher,  WaitingListUser
from booking.views import BookingListView, BookingHistoryListView, \
    BookingCreateView, BookingDeleteView, BookingUpdateView, \
    duplicate_booking, fully_booked, cancellation_period_past, \
    update_booking_cancelled
from common.tests.helpers import _create_session, assert_mailchimp_post_data, \
    TestSetupMixin, format_content, make_data_privacy_agreement

from payments.helpers import create_booking_paypal_transaction


class BookingListViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(BookingListViewTests, cls).setUpTestData()
        # name events explicitly to avoid invoice id conflicts in tests
        # (should never happen in reality since the invoice id is built from
        # (event name initials and datetime)
        cls.events = [
            mommy.make_recipe('booking.future_EV',  name="First Event"),
            mommy.make_recipe('booking.future_PC',  name="Scnd Event"),
            mommy.make_recipe('booking.future_RH',  name="Third Event")
        ]
        cls.url = reverse('booking:bookings')

    def setUp(self):
        super(BookingListViewTests, self).setUp()
        [mommy.make_recipe(
            'booking.booking', user=self.user,
            event=event) for event in self.events]
        mommy.make_recipe('booking.past_booking', user=self.user)

    def test_login_required(self):
        """
        test that page redirects if there is no user logged in
        """
        url = reverse('booking:bookings')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

    def test_booking_list(self):
        """
        Test that only future bookings are listed)
        """
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)

        self.assertEquals(Booking.objects.all().count(), 4)
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context_data['bookings'].count(), 3)

    def test_booking_list_by_user(self):
        """
        Test that only bookings for this user are listed
        """
        another_user = mommy.make_recipe('booking.user')
        mommy.make_recipe(
            'booking.booking', user=another_user, event=self.events[0]
        )
        # check there are now 5 bookings
        self.assertEquals(Booking.objects.all().count(), 5)
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)

        # event listing should still only show this user's future bookings
        self.assertEquals(resp.context_data['bookings'].count(), 3)

    def test_cancelled_booking_shown_in_booking_list(self):
        """
        Test that all future bookings for this user are listed
        """
        ev = mommy.make_recipe('booking.future_EV', name="future event")
        mommy.make_recipe(
            'booking.booking', user=self.user, event=ev,
            status='CANCELLED'
        )
        # check there are now 5 bookings (3 future, 1 past, 1 cancelled)
        self.assertEquals(Booking.objects.all().count(), 5)
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)

        # booking listing should show this user's future bookings,
        # including the cancelled one
        self.assertEquals(resp.context_data['bookings'].count(), 4)

    def test_cancelled_events_shown_in_booking_list(self):
        """
        Test that all future bookings for cancelled events for this user are
        listed
        """
        Booking.objects.all().delete()
        ev = mommy.make_recipe(
            'booking.future_EV', name="future event", cancelled=True
        )
        mommy.make_recipe(
            'booking.booking', user=self.user, event=ev,
            status='CANCELLED'
        )
        # check there are now 5 bookings (3 future, 1 past, 1 cancelled)
        self.assertEquals(Booking.objects.all().count(), 1)
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)

        # booking listing should show this user's future bookings,
        # including the cancelled one
        self.assertEquals(resp.context_data['bookings'].count(), 1)
        self.assertIn('EVENT CANCELLED', resp.rendered_content)

    @patch('booking.views.booking_views.timezone')
    def test_show_due_date_time_event_with_payment_due_date(self, mock_tz):
        """
        Test events with advance payment required.
        Booking list shows date payment due.

        1) Payment due date --> show due date
        2) and 3) Payment time allowed --> show time after booking OR rebooking time
        4) cancellation period --> show time before event datetime
        """

        mock_tz.now.return_value = datetime(2015, 2, 1, tzinfo=timezone.utc)

        Event.objects.all().delete()
        Booking.objects.all().delete()
        event = mommy.make_recipe(
            'booking.future_PC', advance_payment_required=True, cost=10,
            date=datetime(2015, 2, 14, 18, 0, tzinfo=timezone.utc),
            payment_due_date=datetime(2015, 2, 12, 16, 0, tzinfo=timezone.utc),
        )
        mommy.make_recipe('booking.booking', user=self.user, event=event)

        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)

        self.assertEquals(len(resp.context_data['bookingformlist']), 1)
        bookingform = resp.context_data['bookingformlist'][0]
        self.assertEqual(bookingform['due_date_time'], event.payment_due_date)

    @patch('booking.views.booking_views.timezone')
    def test_show_due_date_time_event_with_payment_time_allowed(self, mock_tz):
        """
        Test events with advance payment required.
        Booking list shows date payment due.

        1) Payment due date --> show due date
        2) and 3) Payment time allowed --> show time after booking OR rebooking time
        4) cancellation period --> show time before event datetime
        """

        mock_tz.now.return_value = datetime(2015, 2, 1, tzinfo=timezone.utc)

        Event.objects.all().delete()
        Booking.objects.all().delete()
        event = mommy.make_recipe(
            'booking.future_PC', advance_payment_required=True,
            date=datetime(2015, 2, 14, 18, 0, tzinfo=timezone.utc),
            payment_time_allowed=6, cost=10
        )
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event
        )
        booking.date_booked = datetime(2015, 1, 18, tzinfo=timezone.utc)
        booking.save()
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)

        self.assertEquals(len(resp.context_data['bookingformlist']), 1)
        bookingform = resp.context_data['bookingformlist'][0]
        self.assertEqual(
            bookingform['due_date_time'],
            datetime(2015, 1, 18, 6, 0, tzinfo=timezone.utc)
        )

        booking.date_rebooked = datetime(2015, 2, 1, tzinfo=timezone.utc)
        booking.save()
        resp = self.client.get(self.url)

        self.assertEquals(len(resp.context_data['bookingformlist']), 1)
        bookingform = resp.context_data['bookingformlist'][0]
        self.assertEqual(
            bookingform['due_date_time'],
            datetime(2015, 2, 1, 6, 0, tzinfo=timezone.utc)
        )

    @patch('booking.views.booking_views.timezone')
    def test_show_due_date_time_event_with_cancellation_period(self, mock_tz):
        """
        Test events with advance payment required.
        Booking list shows date payment due.

        1) Payment due date --> show due date
        2) and 3) Payment time allowed --> show time after booking OR rebooking time
        4) cancellation period --> show time before event datetime
        """

        mock_tz.now.return_value = datetime(2015, 2, 1, tzinfo=timezone.utc)

        Event.objects.all().delete()
        Booking.objects.all().delete()
        event = mommy.make_recipe(
            'booking.future_PC', advance_payment_required=True,
            date=datetime(2015, 2, 14, 18, 0, tzinfo=timezone.utc),
            cancellation_period=24, cost=10
        )
        mommy.make_recipe(
            'booking.booking', user=self.user, event=event
        )
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)

        self.assertEquals(len(resp.context_data['bookingformlist']), 1)
        bookingform = resp.context_data['bookingformlist'][0]
        self.assertEqual(
            bookingform['due_date_time'],
            datetime(2015, 2, 13, 18, 0, tzinfo=timezone.utc)
        )

    def test_paid_status_display(self):
        Event.objects.all().delete()
        Booking.objects.all().delete()
        event_with_cost = mommy.make_recipe('booking.future_PC', cost=10)
        event_without_cost = mommy.make_recipe('booking.future_PC', cost=0)

        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event_with_cost,
            paid=True
        )
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)
        self.assertIn(
            '<span class="confirmed fa fa-check"></span>',
            resp.rendered_content
        )

        booking.free_class = True
        booking.save()

        resp = self.client.get(self.url)
        self.assertIn(
            '<span class="confirmed">Free class</span>',
            resp.rendered_content
        )

        block = mommy.make_recipe(
            'booking.block', block_type__identifier='transferred'
        )
        booking.free_class = False
        booking.block = block
        booking.save()
        resp = self.client.get(self.url)
        self.assertIn(
            '<span class="confirmed">Transferred</span>',
            resp.rendered_content
        )

        booking.block = None
        booking.paid = False
        booking.save()
        resp = self.client.get(self.url)
        self.assertIn(
            '<span class="not-confirmed fa fa-times"></span>',
            resp.rendered_content
        )

        booking.delete()
        mommy.make_recipe(
            'booking.booking', user=self.user, event=event_without_cost,
        )
        resp = self.client.get(self.url)
        self.assertIn('<strong>N/A</strong>', resp.rendered_content)

        booking.event=event_with_cost
        booking.paid=False
        booking.paypal_pending=True
        booking.save()
        resp = self.client.get(self.url)
        self.assertIn(
            '<span class="not-confirmed">PayPal pending</span>',
            resp.rendered_content
        )

    def test_auto_cancelled_booking(self):
        """
        Test that auto_cancelled bookings for this user are listed with rebook
        button disabled
        """
        ev = mommy.make_recipe('booking.future_EV', name="future event")
        mommy.make_recipe(
            'booking.booking', user=self.user, event=ev,
            status='CANCELLED', auto_cancelled=True
        )
        # check there are now 5 bookings (3 future, 1 past, 1 cancelled)
        self.assertEquals(Booking.objects.all().count(), 5)
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)

        # booking listing should show this user's future bookings,
        # including the cancelled one
        self.assertEquals(resp.context_data['bookings'].count(), 4)
        self.assertIn(
            'rebook_button_auto_cancelled_disabled', resp.rendered_content
        )


class BookingHistoryListViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(BookingHistoryListViewTests, cls).setUpTestData()
        cls.event = mommy.make_recipe('booking.future_EV')
        cls.url = reverse('booking:booking_history')

    def setUp(self):
        super(BookingHistoryListViewTests, self).setUp()
        self.booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=self.event
        )
        self.past_booking = mommy.make_recipe(
            'booking.past_booking', user=self.user
        )

    def test_login_required(self):
        """
        test that page redirects if there is no user logged in
        """
        url = reverse('booking:booking_history')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

    def test_booking_history_list(self):
        """
        Test that only past bookings are listed)
        """
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)

        self.assertEquals(Booking.objects.all().count(), 2)
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context_data['bookings'].count(), 1)

    def test_booking_history_list_by_user(self):
        """
        Test that only past booking for this user are listed
        """
        another_user = mommy.make_recipe('booking.user')
        mommy.make_recipe(
            'booking.booking', user=another_user, event=self.past_booking.event
        )
        # check there are now 3 bookings
        self.assertEquals(Booking.objects.all().count(), 3)
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)

        #  listing should still only show this user's past bookings
        self.assertEquals(resp.context_data['bookings'].count(), 1)


class BookingCreateViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(BookingCreateViewTests, cls).setUpTestData()
        cls.pole_class_event_type = mommy.make(
            EventType, event_type='CL', subtype='Pole level class'
        )
        cls.free_blocktype = mommy.make_recipe(
            'booking.blocktype', size=1, cost=0,
            event_type=cls.pole_class_event_type, identifier='free class'
        )
        cls.group, _ = Group.objects.get_or_create(name='subscribed')

    def setUp(self):
        super(BookingCreateViewTests, self).setUp()
        self.user_no_disclaimer = mommy.make_recipe('booking.user')
        make_data_privacy_agreement(self.user_no_disclaimer)

    def _post_response(self, user, event, form_data={}):
        url = reverse('booking:book_event', kwargs={'event_slug': event.slug})
        store = _create_session()
        form_data['event'] = event.id
        request = self.factory.post(url, form_data)
        request.session = store
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        view = BookingCreateView.as_view()
        return view(request, event_slug=event.slug)

    def _get_response(self, user, event):
        url = reverse('booking:book_event', kwargs={'event_slug': event.slug})
        store = _create_session()
        request = self.factory.get(url, {'event': event.id})
        request.session = store
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        view = BookingCreateView.as_view()
        return view(request, event_slug=event.slug)

    def test_cannot_access_if_no_disclaimer(self):
        event = mommy.make_recipe('booking.future_EV', max_participants=3)
        resp = self._get_response(self.user_no_disclaimer, event)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:disclaimer_required'))

        resp = self._post_response(self.user_no_disclaimer, event)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:disclaimer_required'))

        resp = self._get_response(self.user, event)
        self.assertEqual(resp.status_code, 200)

    def test_cannot_access_if_expired_disclaimer(self):
        event = mommy.make_recipe('booking.future_EV', max_participants=3)
        user = mommy.make_recipe('booking.user')
        make_data_privacy_agreement(user)
        disclaimer = mommy.make_recipe(
           'booking.online_disclaimer', user=user,
            date=datetime(2015, 2, 1, tzinfo=timezone.utc)
        )
        self.assertFalse(disclaimer.is_active)

        resp = self._get_response(user, event)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:disclaimer_required'))

        resp = self._post_response(user, event)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:disclaimer_required'))

        mommy.make(OnlineDisclaimer, user=user)
        resp = self._get_response(user, event)
        self.assertEqual(resp.status_code, 200)

    def test_get_create_booking_page(self):
        """
        Get the booking page with the event context
        """
        event = mommy.make_recipe('booking.future_EV', max_participants=3)
        resp = self._get_response(self.user, event)
        self.assertEqual(resp.context_data['event'], event)

    def test_login_required(self):
        event = mommy.make_recipe('booking.future_EV', max_participants=3)
        url = reverse('booking:book_event', kwargs={'event_slug': event.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

    def test_create_booking(self):
        """
        Test creating a booking
        """
        event = mommy.make_recipe('booking.future_EV', max_participants=3)
        self.assertEqual(Booking.objects.all().count(), 0)
        self._post_response(self.user, event)
        self.assertEqual(Booking.objects.all().count(), 1)

    def test_cancellation_messages(self):
        """
        Test creating a booking creates correct cancellation messages

        event with cost and advance_payment_required and allow_booking_cancellation:
         - by payment due date
         - within payment allowed time
         - by cancellation period

         if cost but not adv payment require or not cancellation allowed
         - just show "pay asap" message

        """
        event = mommy.make_recipe(
            'booking.future_EV', max_participants=3, cost=10,
        )
        self.assertEqual(Booking.objects.all().count(), 0)
        self.assertTrue(
            self.client.login(username=self.user.username, password='test')
        )
        url = reverse('booking:book_event', kwargs={'event_slug': event.slug})
        resp = self.client.post(
            url, {'book_one_off': 'book_one_off', 'event': event.id},
            follow=True
        )
        self.assertEqual(Booking.objects.all().count(), 1)

        auto_cancel_warning = \
            'Please make your payment as soon as possible. Note that if ' \
            'payment has not been received {}, your ' \
            'booking will be automatically cancelled and you will need to ' \
            'contact the studio directly to rebook.'
        # event has cancellation period
        self.assertIn(
            auto_cancel_warning.format('by the cancellation period'),
            format_content(resp.rendered_content)
        )

        Booking.objects.all().delete()
        # add event payment due date
        event.payment_due_date = timezone.now() + timedelta(3)
        event.save()
        resp = self.client.post(
            url, {'book_one_off': 'book_one_off', 'event': event.id},
            follow=True
        )
        self.assertEqual(Booking.objects.all().count(), 1)
        self.assertIn(
            auto_cancel_warning.format('by the payment due date'),
            format_content(resp.rendered_content)
        )

        Booking.objects.all().delete()
        # if there are both payment due date and payment time allowed, payment
        # due date takes precedence
        event.payment_time_allowed = 8
        event.save()
        resp = self.client.post(
            url, {'book_one_off': 'book_one_off', 'event': event.id},
            follow=True
        )
        self.assertEqual(Booking.objects.all().count(), 1)
        self.assertIn(
            auto_cancel_warning.format('by the payment due date'),
            format_content(resp.rendered_content)
        )

        Booking.objects.all().delete()
        event.payment_due_date = None
        event.save()
        resp = self.client.post(
            url, {'book_one_off': 'book_one_off', 'event': event.id},
            follow=True
        )
        self.assertEqual(Booking.objects.all().count(), 1)
        self.assertIn(
            auto_cancel_warning.format('within 8 hours'),
            format_content(resp.rendered_content)
        )

        Booking.objects.all().delete()
        # make advance payment not required
        event.advance_payment_required = False
        # payment due date automatically sets advance payment required to True
        event.payment_time_allowed = None
        event.save()
        self.assertFalse(event.advance_payment_required)
        resp = self.client.post(
            url, {'book_one_off': 'book_one_off', 'event': event.id},
            follow=True
        )
        self.assertEqual(Booking.objects.all().count(), 1)
        self.assertIn(
            'Please make your payment as soon as possible.',
            format_content(resp.rendered_content)
        )
        self.assertNotIn(
            'Note that if payment has not been received',
            format_content(resp.rendered_content)
        )

        Booking.objects.all().delete()
        # make cancellation not allowed
        event.advance_payment_required = True
        event.allow_booking_cancellation = False
        event.save()
        resp = self.client.post(
            url, {'book_one_off': 'book_one_off', 'event': event.id},
            follow=True
        )
        self.assertEqual(Booking.objects.all().count(), 1)
        self.assertIn(
            'Please make your payment as soon as possible.',
            format_content(resp.rendered_content)
        )
        self.assertNotIn(
            'Note that if payment has not been received',
            format_content(resp.rendered_content)
        )

    def test_create_booking_sends_email(self):
        """
        Test creating a booking sends email to user only by default
        """
        event = mommy.make_recipe('booking.future_EV', max_participants=3)
        self.assertEqual(Booking.objects.all().count(), 0)
        self._post_response(self.user, event)
        self.assertEqual(Booking.objects.all().count(), 1)
        # email to student only
        self.assertEqual(len(mail.outbox), 1)

    def test_create_booking_sends_email_to_studio_if_set(self):
        """
        Test creating a booking send email to user and studio if flag sent on
        event
        """
        event = mommy.make_recipe(
            'booking.future_EV', max_participants=3,
            email_studio_when_booked=True
        )
        self.assertEqual(Booking.objects.all().count(), 0)
        self._post_response(self.user, event)
        self.assertEqual(Booking.objects.all().count(), 1)
        # email to student and studio
        self.assertEqual(len(mail.outbox), 2)

    @override_settings(WATCHLIST=['foo@test.com', 'bar@test.com'])
    def test_create_booking_sends_email_to_studio_for_users_on_watchlist(self):
        event = mommy.make_recipe(
            'booking.future_EV', max_participants=3,
            email_studio_when_booked=False
        )
        self._post_response(self.user, event)
        self.assertEqual(Booking.objects.count(), 1)
        # email to student only
        self.assertEqual(len(mail.outbox), 1)

        # create watched user and book
        watched_user = User.objects.create(
            username='foo', email='foo@test.com', password='test'
        )
        mommy.make(OnlineDisclaimer, user=watched_user)
        make_data_privacy_agreement(watched_user)
        self._post_response(watched_user, event)
        self.assertEqual(Booking.objects.count(), 2)
        # 2 addition emails in mailbox for this booking, to student and studio
        self.assertEqual(len(mail.outbox), 3)

    @patch('booking.views.booking_views.send_mail')
    def test_create_booking_with_email_error(self, mock_send_emails):
        """
        Test creating a booking sends email to support if there is an email
        error but still creates booking
        """
        mock_send_emails.side_effect = Exception('Error sending mail')

        event = mommy.make_recipe(
            'booking.future_EV', email_studio_when_booked=True,
            max_participants=3
        )
        self.assertEqual(Booking.objects.all().count(), 0)
        self._post_response(self.user, event)
        self.assertEqual(Booking.objects.all().count(), 1)
        # email to support only
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, [settings.SUPPORT_EMAIL])

    @patch('booking.views.booking_views.send_mail')
    @patch('booking.email_helpers.send_mail')
    def test_create_booking_with_all_email_error(
            self, mock_send_emails, mock_send_emails1
    ):
        """
        Test if all emails fail when creating a booking
        """
        mock_send_emails.side_effect = Exception('Error sending mail')
        mock_send_emails1.side_effect = Exception('Error sending mail')

        event = mommy.make_recipe(
            'booking.future_EV', max_participants=3,
            email_studio_when_booked=True
        )
        self.assertEqual(Booking.objects.all().count(), 0)
        self._post_response(self.user, event)
        self.assertEqual(Booking.objects.all().count(), 1)
        # no emails sent
        self.assertEqual(len(mail.outbox), 0)

        # exception is logged in activity log
        log = ActivityLog.objects.last()
        self.assertEqual(
            log.log,
            'Problem sending an email '
            '(booking.views.booking_views: Error sending mail)'
        )

    def test_create_room_hire(self):
        """
        Test creating a room hire booking
        """
        room_hire = mommy.make_recipe('booking.future_RH', max_participants=3)
        self.assertEqual(Booking.objects.all().count(), 0)
        self._post_response(self.user, room_hire)
        self.assertEqual(Booking.objects.all().count(), 1)

    def test_cannot_get_create_page_for_duplicate_booking(self):
        """
        Test trying to get the create page for existing redirects
        """
        event = mommy.make_recipe('booking.future_EV', max_participants=3)
        mommy.make_recipe('booking.booking', user=self.user, event=event)

        self.client.login(username=self.user.username, password='test')
        url = reverse('booking:book_event', kwargs={'event_slug': event.slug})
        resp = self.client.get(url)
        duplicate_url = reverse(
            'booking:duplicate_booking', kwargs={'event_slug': event.slug}
        )
        # test redirect to duplicate booking url
        self.assertEqual(resp.url, duplicate_url)

    def test_cannot_create_duplicate_booking(self):
        """
        Test trying to create a duplicate booking redirects
        """
        event = mommy.make_recipe('booking.future_EV', max_participants=3)
        mommy.make_recipe('booking.booking', user=self.user, event=event)

        self.client.login(username=self.user.username, password='test')
        url = reverse('booking:book_event', kwargs={'event_slug': event.slug})

        resp = self.client.post(url, {'event': event.id})
        duplicate_url = reverse(
            'booking:duplicate_booking', kwargs={'event_slug': event.slug}
        )
        # test redirect to duplicate booking url
        self.assertEqual(resp.url, duplicate_url)

    def test_cannot_get_create_booking_page_for_full_event(self):
        """
        Test trying to get create booking page for a full event redirects
        """
        event = mommy.make_recipe('booking.future_EV', max_participants=3)
        users = mommy.make_recipe('booking.user', _quantity=3)
        for user in users:
            mommy.make_recipe('booking.booking', event=event, user=user)
        # check event is full; we need to get the event again as spaces_left is
        # cached property
        event = Event.objects.get(id=event.id)
        self.assertEqual(event.spaces_left, 0)

        # try to book for event
        resp = self._get_response(self.user, event)
        # test redirect to duplicate booking url
        self.assertEqual(
            resp.url,
            reverse(
                'booking:fully_booked',
                kwargs={'event_slug': event.slug}
            )
        )

    def test_cannot_book_for_full_event(self):
        """cannot create booking for a full event
        """
        event = mommy.make_recipe('booking.future_EV', max_participants=3)
        users = mommy.make_recipe('booking.user', _quantity=3)
        for user in users:
            mommy.make_recipe('booking.booking', event=event, user=user)

        # check event is full; we need to get the event again as spaces_left is
        # cached property
        event = Event.objects.get(id=event.id)
        self.assertEqual(event.spaces_left, 0)

        # try to book for event
        resp = self._post_response(self.user, event)

        # test redirect to duplicate booking url
        self.assertEqual(
            resp.url,
            reverse(
                'booking:fully_booked',
                kwargs={'event_slug': event.slug}
            )
        )

    def test_cancelled_booking_can_be_rebooked(self):
        """
        Test can load create booking page with a cancelled booking
        """

        event = mommy.make_recipe('booking.future_EV')
        # book for event
        self._post_response(self.user, event)

        booking = Booking.objects.get(user=self.user, event=event)
        # cancel booking
        booking.status = 'CANCELLED'
        booking.save()

        # try to book again
        resp = self._get_response(self.user, event)
        self.assertEqual(resp.status_code, 200)

    def test_no_show_booking_can_be_rebooked(self):
        """
        Test can load create booking page with a no_show open booking
        No option to book with block
        """
        pclass = mommy.make_recipe(
            'booking.future_PC', allow_booking_cancellation=False, cost=10
        )
        block = mommy.make_recipe(
            'booking.block', block_type__event_type=pclass.event_type,
            user=self.user, paid=True
        )
        # book for non-refundable event and mark as no_show
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=pclass, paid=True,
            no_show=True, status='OPEN'
        )

        # try to get booking page again
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(
            reverse('booking:book_event', kwargs={'event_slug': pclass.slug}),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context_data['reopening_paid_booking'])
        # active block is present but not an option in the page b/c already paid
        self.assertTrue(resp.context_data['active_user_block'])
        self.assertNotIn('Book & pay with block', resp.rendered_content)

    def test_rebook_cancelled_booking(self):
        """
        Test can rebook a cancelled booking
        """

        event = mommy.make_recipe('booking.future_EV')
        # book for event
        self._post_response(self.user, event)

        booking = Booking.objects.get(user=self.user, event=event)
        # cancel booking
        booking.status = 'CANCELLED'
        booking.save()
        self.assertIsNone(booking.date_rebooked)

        # try to book again
        self._post_response(self.user, event)
        booking.refresh_from_db()
        self.assertEqual('OPEN', booking.status)
        self.assertIsNotNone(booking.date_rebooked)

    def test_rebook_no_show_booking(self):
        """
        Test can rebook a booking marked as no_show
        """

        pclass = mommy.make_recipe(
            'booking.future_PC', allow_booking_cancellation=False, cost=10
        )
        # book for non-refundable event and mark as no_show
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=pclass, paid=True,
            no_show=True
        )
        self.assertIsNone(booking.date_rebooked)

        # try to book again
        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(
            reverse('booking:book_event', kwargs={'event_slug': pclass.slug}),
            {'event': pclass.id},
            follow=True
        )
        booking.refresh_from_db()
        self.assertEqual('OPEN', booking.status)
        self.assertFalse(booking.no_show)
        self.assertIsNotNone(booking.date_rebooked)
        self.assertIn(
            "You previously paid for this booking and your "
            "booking has been reopened.",
            resp.rendered_content
        )

        # emails sent to student
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ['test@test.com'])

    def test_rebook_no_show_block_booking(self):
        """
        Test can rebook a block booking marked as no_show
        """

        pclass = mommy.make_recipe(
            'booking.future_PC', allow_booking_cancellation=False, cost=10
        )
        block = mommy.make_recipe(
            'booking.block', user=self.user, paid=True,
            block_type__event_type =pclass.event_type
        )
        # book for non-refundable event and mark as no_show
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=pclass, paid=True,
            no_show=True, block=block
        )

        # cancel booking
        self.assertIsNone(booking.date_rebooked)

        # try to book again
        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(
            reverse('booking:book_event', kwargs={'event_slug': pclass.slug}),
            {'event': pclass.id},
            follow=True
        )

        booking.refresh_from_db()
        self.assertEqual('OPEN', booking.status)
        self.assertFalse(booking.no_show)
        self.assertIsNotNone(booking.date_rebooked)
        self.assertIn(
            "You previously paid for this booking with a block and your "
            "booking has been reopened.",
            resp.rendered_content
        )

        # emails sent to student
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ['test@test.com'])

    def test_rebook_cancelled_paid_booking(self):

        """
        Test rebooking a cancelled booking still marked as paid reopend booking
        and emails studi
        """
        event = mommy.make_recipe('booking.future_PC')
        mommy.make_recipe(
            'booking.booking', event=event, user=self.user, paid=True,
            payment_confirmed=True, status='CANCELLED'
        )

        # try to book again
        self._post_response(self.user, event)
        booking = Booking.objects.get(user=self.user, event=event)
        self.assertEqual('OPEN', booking.status)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)

        # email to user and to studio
        self.assertEqual(len(mail.outbox), 2)
        mail_to_user = mail.outbox[0]
        mail_to_studio = mail.outbox[1]

        self.assertEqual(mail_to_user.to, [self.user.email])
        self.assertEqual(mail_to_studio.to, [settings.DEFAULT_STUDIO_EMAIL])

    def test_rebook_cancelled_paypal_paid_booking(self):

        """
        Test rebooking a cancelled booking still marked as paid by paypal makes
        booking status open but does not confirm space, fetches the paypal
        transaction id
        """
        event = mommy.make_recipe('booking.future_PC')
        booking = mommy.make_recipe(
            'booking.booking', event=event, user=self.user, paid=True,
            payment_confirmed=True, status='CANCELLED'
        )
        pptrans = create_booking_paypal_transaction(
            booking=booking, user=self.user
        )
        pptrans.transaction_id = "txn"
        pptrans.save()

        # try to book again
        self._post_response(self.user, event)
        booking = Booking.objects.get(user=self.user, event=event)
        self.assertEqual('OPEN', booking.status)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)

        # email to user and to studio
        self.assertEqual(len(mail.outbox), 2)
        mail_to_user = mail.outbox[0]
        mail_to_studio = mail.outbox[1]

        self.assertEqual(mail_to_user.to, [self.user.email])
        self.assertEqual(mail_to_studio.to, [settings.DEFAULT_STUDIO_EMAIL])
        self.assertIn(pptrans.transaction_id, mail_to_studio.body)
        self.assertIn(pptrans.invoice_id, mail_to_studio.body)

    def test_booking_page_has_active_user_block_context(self):
        """
        Test that a user with an active block can book using their block
        """
        event_type = mommy.make_recipe('booking.event_type_PC')
        event = mommy.make_recipe('booking.future_PC', event_type=event_type)
        blocktype = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type
        )
        block = mommy.make_recipe(
            'booking.block', block_type=blocktype, user=self.user, paid=True
        )
        self.assertTrue(block.active_block())
        resp = self._get_response(self.user, event)
        self.assertIn('active_user_block', resp.context_data)

    def test_booking_page_has_unpaid_user_block_context(self):
        """
        Test that a user with an active block can book using their block
        """
        event_type = mommy.make_recipe('booking.event_type_PC')
        event = mommy.make_recipe('booking.future_PC', event_type=event_type)
        blocktype = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type
        )
        mommy.make_recipe(
            'booking.block', block_type=blocktype, user=self.user, paid=False
        )
        resp = self._get_response(self.user, event)
        self.assertFalse('active_user_block' in resp.context_data)
        self.assertIn('active_user_block_unpaid', resp.context_data)

    def test_creating_booking_with_active_user_block(self):
        """
        Test that a user with an active block can book using their block
        """
        event_type = mommy.make_recipe('booking.event_type_PC')

        event = mommy.make_recipe('booking.future_PC', event_type=event_type)
        blocktype = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type
        )
        block = mommy.make_recipe(
            'booking.block', block_type=blocktype, user=self.user, paid=True
        )
        self.assertTrue(block.active_block())
        form_data = {'block_book': True}
        self._post_response(self.user, event, form_data)

        bookings = Booking.objects.filter(user=self.user)
        self.assertEqual(bookings.count(), 1)
        self.assertEqual(bookings[0].block, block)

    def test_requesting_free_class(self):
        """
        Test that requesting a free class emails the studio and creates booking
        as unpaid
        """
        event_type = mommy.make_recipe('booking.event_type_PC')
        event = mommy.make_recipe('booking.future_PC', event_type=event_type)

        bookings = Booking.objects.filter(user=self.user)
        self.assertEqual(bookings.count(), 0)

        form_data = {'claim_free': True}
        self._post_response(self.user, event, form_data)
        bookings = Booking.objects.filter(user=self.user)
        self.assertEqual(bookings.count(), 1)
        self.assertEqual(len(mail.outbox), 2)

        free_booking = bookings[0]
        self.assertTrue(free_booking.free_class_requested)
        self.assertFalse(free_booking.free_class)
        self.assertFalse(free_booking.paid)
        self.assertFalse(free_booking.payment_confirmed)

    @patch('booking.views.booking_views.send_mail')
    def test_requesting_free_class_with_email_error(self, mock_send_emails):
        """
        Test that requesting a free class with email error emails support and
        still creates booking
        """
        mock_send_emails.side_effect = Exception('Error sending mail')

        event_type = mommy.make_recipe('booking.event_type_PC')
        event = mommy.make_recipe('booking.future_PC', event_type=event_type)

        bookings = Booking.objects.filter(user=self.user)
        self.assertEqual(bookings.count(), 0)

        form_data = {'claim_free': True}
        self._post_response(self.user, event, form_data)
        bookings = Booking.objects.filter(user=self.user)
        self.assertEqual(bookings.count(), 1)

        # 2 support emails sent for each of the attempted emails
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, [settings.SUPPORT_EMAIL])
        self.assertEqual(mail.outbox[1].to, [settings.SUPPORT_EMAIL])

    @patch('booking.views.booking_views.send_mail')
    @patch('booking.email_helpers.send_mail')
    def test_requesting_free_class_with_all_email_error(
            self, mock_send_emails, mock_send_emails1
    ):
        """
        Test if all emails fail when creating a booking
        """
        mock_send_emails.side_effect = Exception('Error sending mail')
        mock_send_emails1.side_effect = Exception('Error sending mail')

        event_type = mommy.make_recipe('booking.event_type_PC')
        event = mommy.make_recipe('booking.future_PC', event_type=event_type)

        bookings = Booking.objects.filter(user=self.user)
        self.assertEqual(bookings.count(), 0)

        form_data = {'claim_free': True}
        self._post_response(self.user, event, form_data)
        bookings = Booking.objects.filter(user=self.user)
        self.assertEqual(bookings.count(), 1)

        # no emails sent
        self.assertEqual(len(mail.outbox), 0)

        # exception is logged in activity log
        log = ActivityLog.objects.last()
        self.assertEqual(
            log.log,
            'Problem sending an email '
            '(booking.views.booking_views: Error sending mail)'
        )

    def test_rebook_cancelled_booking_as_free_class(self):
        """
        Test can rebook a cancelled booking
        """

        event = mommy.make_recipe('booking.future_EV')
        # book for event
        resp = self._post_response(self.user, event, {'claim_free': True})

        booking = Booking.objects.get(user=self.user, event=event)
        # cancel booking
        booking.status = 'CANCELLED'
        booking.save()
        self.assertIsNone(booking.date_rebooked)

        # try to book again
        self._post_response(self.user, event)
        booking.refresh_from_db()
        self.assertEqual('OPEN', booking.status)
        self.assertIsNotNone(booking.date_rebooked)
        self.assertTrue(booking.free_class_requested)
        self.assertFalse(booking.free_class)
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)

    def test_free_class_context(self):
        """
        Test that only pole classes and pole practice can be requested as
        free by users with permission
        """
        pp_event_type = mommy.make_recipe(
            'booking.event_type_OC', subtype="Pole practice"
        )
        rh_event_type = mommy.make_recipe(
            'booking.event_type_RH', subtype="Room hire"
        )

        pole_class = mommy.make_recipe(
            'booking.future_PC', event_type=self.pole_class_event_type
        )
        pole_practice = mommy.make_recipe(
            'booking.future_CL', event_type=pp_event_type
        )
        room_hire = mommy.make_recipe(
            'booking.future_RH', event_type=rh_event_type
        )

        perm = Permission.objects.get(codename='is_regular_student')
        self.user.user_permissions.add(perm)

        # get user from db to refresh permissions cache
        user = User.objects.get(pk=self.user.pk)

        response = self._get_response(user, pole_class)
        self.assertNotIn('can_be_free_class', response.context_data)

        response = self._get_response(user, pole_practice)
        self.assertNotIn('can_be_free_class', response.context_data)

        response = self._get_response(user, room_hire)
        self.assertNotIn('can_be_free_class', response.context_data)

        # give user permission
        perm1 = Permission.objects.get(codename='can_request_free_class')
        self.user.user_permissions.add(perm1)
        user = User.objects.get(id=self.user.id)

        # now user can request free pole practice and class, but not room hire
        response = self._get_response(user, pole_class)
        self.assertIn('can_be_free_class', response.context_data)

        response = self._get_response(user, pole_practice)
        self.assertIn('can_be_free_class', response.context_data)

        response = self._get_response(user, room_hire)
        self.assertNotIn('can_be_free_class', response.context_data)

    def test_free_class_context_with_permission(self):
        """
        Test that pole classes and pole practice can be requested as free if
        user has 'can_request_free_class' permission
        """
        pp_event_type = mommy.make_recipe(
            'booking.event_type_OC', subtype="Pole practice"
        )

        pole_class = mommy.make_recipe(
            'booking.future_PC', event_type=self.pole_class_event_type
                                       )
        pole_practice = mommy.make_recipe(
            'booking.future_CL', event_type=pp_event_type
        )

        user = mommy.make_recipe('booking.user')
        make_data_privacy_agreement(user)
        mommy.make(OnlineDisclaimer, user=user)
        perm = Permission.objects.get(codename='can_request_free_class')
        perm1 = Permission.objects.get(codename='is_regular_student')
        user.user_permissions.add(perm)
        user.user_permissions.add(perm1)
        user.save()

        response = self._get_response(user, pole_class)
        self.assertIn('can_be_free_class', response.context_data)

        response = self._get_response(user, pole_practice)
        self.assertIn('can_be_free_class', response.context_data)

    def test_cannot_book_for_cancelled_event(self):
        """
        Test trying to create a booking for a cancelled event redirects
        """
        event = mommy.make_recipe('booking.future_EV', cancelled=True)

        # try to book for event
        resp = self._get_response(self.user, event)
        # test redirect to permission denied page
        self.assertEqual(
            resp.url,
            reverse(
                'booking:permission_denied',
            )
        )

    def test_cannot_book_for_pole_practice_if_not_regular_student(self):
        """
        Test trying to create a booking for pole practice if not regular
         student redirects
        """
        Event.objects.all().delete()
        event = mommy.make_recipe(
            'booking.future_PP', event_type__subtype='Pole practice'
        )
        self.user.user_permissions.all().delete()
        # try to get booking page
        resp = self._get_response(self.user, event)
        # test redirect to permission denied page
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url,
            reverse(
                'booking:permission_denied',
            )
        )

        perm = Permission.objects.get(codename='is_regular_student')
        self.user.user_permissions.add(perm)
        # this is necessary to get around django's caching of permissions
        user = User.objects.get(id=self.user.id)

        # try again
        resp = self._get_response(user, event)
        self.assertEqual(resp.status_code, 200)

    @patch('booking.models.timezone')
    def test_booking_with_block_if_multiple_blocks_available(self, mock_tz):
        """
        Usually there should be only one block of each type available, but in
        case an admin has added additional blocks, ensure that the one with the
        earlier expiry date is used
        """
        mock_tz.now.return_value = datetime(2015, 1, 10, tzinfo=timezone.utc)
        event_type = mommy.make_recipe('booking.event_type_PC')

        event = mommy.make_recipe('booking.future_PC', event_type=event_type)
        blocktype = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type, duration=2
        )
        block1 = mommy.make_recipe(
            'booking.block', block_type=blocktype, user=self.user, paid=True,
            start_date=datetime(2015, 1, 2, tzinfo=timezone.utc)
        )
        block2 = mommy.make_recipe(
            'booking.block', block_type=blocktype, user=self.user, paid=True,
            start_date=datetime(2015, 1, 1, tzinfo=timezone.utc)
        )
        # block1 was created first, but block2 has earlier expiry date so
        # should be used first
        self.assertGreater(block1.expiry_date, block2.expiry_date)

        form_data = {'block_book': True}
        self._post_response(self.user, event, form_data)

        bookings = Booking.objects.filter(user=self.user)
        self.assertEqual(bookings.count(), 1)
        self.assertEqual(bookings[0].block, block2)

        # change start dates so block1 now has the earlier expiry date
        bookings[0].delete()
        block2.start_date = datetime(2015, 1, 3, tzinfo=timezone.utc)
        block2.save()
        self._post_response(self.user, event, form_data)

        bookings = Booking.objects.filter(user=self.user)
        self.assertEqual(bookings.count(), 1)
        self.assertEqual(bookings[0].block, block1)

    @patch('booking.models.timezone')
    def test_booking_with_block_if_original_and_free_available(self, mock_tz):
        """
        Usually there will only be an open free block attached to another block
        if the original is full, but in case an admin has changed this, ensure
        that the original block is used first (free block with parent block
        should always be created after the original block)
        """
        mock_tz.now.return_value = datetime(2015, 1, 10, tzinfo=timezone.utc)

        event = mommy.make_recipe(
            'booking.future_PC', event_type=self.pole_class_event_type
        )

        blocktype = mommy.make_recipe(
            'booking.blocktype', size=10, cost=60, duration=4,
            event_type=self.pole_class_event_type, identifier='standard'
        )

        block = mommy.make_recipe(
            'booking.block', user=self.user, block_type=blocktype, paid=True
        )
        free_block = mommy.make_recipe(
            'booking.block', user=self.user, block_type=self.free_blocktype,
            paid=True, parent=block
        )

        self.assertTrue(block.active_block())
        self.assertTrue(free_block.active_block())
        self.assertEqual(block.expiry_date, free_block.expiry_date)

        blocks = self.user.blocks.all()
        active_blocks = [
            block for block in blocks if block.active_block()
            and block.block_type.event_type == event.event_type
        ]
        # the original and free block are both available blocks for this event
        self.assertEqual(set(active_blocks), set([block, free_block]))

        form_data = {'block_book': True}
        self._post_response(self.user, event, form_data)

        # booking created using the original block
        bookings = Booking.objects.filter(user=self.user)
        self.assertEqual(bookings.count(), 1)
        self.assertEqual(bookings[0].block, block)

    @patch('booking.models.timezone')
    def test_trying_to_block_book_with_no_available_block(self, mock_tz):
        """
        The template should prevent attempts to block book if no block is
        available; however, if this is submitted, make the booking without
        the block
        """
        mock_tz.now.return_value = datetime(2015, 1, 10, tzinfo=timezone.utc)
        event_type = mommy.make_recipe('booking.event_type_PC')
        event_type1 = mommy.make_recipe('booking.event_type_PC')

        event = mommy.make_recipe('booking.future_PC', event_type=event_type)
        # make block with different event type to the event we're trying to
        # book
        blocktype = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type1, duration=2
        )
        block = mommy.make_recipe(
            'booking.block', block_type=blocktype, user=self.user, paid=True,
            start_date=datetime(2015, 1, 2, tzinfo=timezone.utc)
        )

        self.assertTrue(block.active_block())
        self.assertNotEqual(block.block_type.event_type, event.event_type)

        self.assertEqual(Booking.objects.count(), 0)
        # try to block book
        form_data = {'block_book': True}
        self._post_response(self.user, event, form_data)

        # booking has been made, but no block assigned
        self.assertEqual(Booking.objects.count(), 1)
        booking = Booking.objects.first()
        self.assertIsNone(booking.block)
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)

    def test_create_booking_uses_last_of_free_class_allowed_blocks(self):
        block = mommy.make_recipe(
            'booking.block_10', user=self.user,
            block_type__event_type=self.pole_class_event_type,
            block_type__assign_free_class_on_completion=True,
            paid=True, start_date=timezone.now()
        )
        event = mommy.make_recipe(
            'booking.future_CL', cost=10, event_type=self.pole_class_event_type
        )

        mommy.make_recipe(
            'booking.booking', block=block, user=self.user, _quantity=9
        )

        self.assertEqual(Block.objects.count(), 1)
        self._post_response(self.user, event, {'block_book': 'yes'})

        self.assertEqual(block.bookings.count(), 10)
        self.assertEqual(Block.objects.count(), 2)
        self.assertEqual(Block.objects.latest('id').block_type, self.free_blocktype)

    def test_booking_uses_last_of_free_class_allowed_free_block_already_exists(self):
        block = mommy.make_recipe(
            'booking.block_10', user=self.user,
            block_type__event_type=self.pole_class_event_type,
            block_type__assign_free_class_on_completion=True,
            paid=True, start_date=timezone.now()
        )
        event = mommy.make_recipe(
            'booking.future_EV', cost=10, event_type=self.pole_class_event_type
        )

        mommy.make_recipe(
            'booking.block', user=self.user, block_type=self.free_blocktype,
            paid=True, parent=block
        )

        mommy.make_recipe(
            'booking.booking', block=block, user=self.user, _quantity=9
        )
        self.assertEqual(Block.objects.count(), 2)
        self._post_response(self.user, event, {'block_book': 'yes'})

        self.assertEqual(block.bookings.count(), 10)
        self.assertEqual(Block.objects.count(), 2)

    def test_create_booking_uses_last_of_block_but_doesnt_qualify_for_free(self):
        block = mommy.make_recipe(
            'booking.block_10', user=self.user,
            block_type__event_type=self.pole_class_event_type,
            block_type__assign_free_class_on_completion=False,
            paid=True, start_date=timezone.now()
        )
        event = mommy.make_recipe(
            'booking.future_CL', cost=10, event_type=self.pole_class_event_type
        )

        mommy.make_recipe(
            'booking.booking', block=block, user=self.user, _quantity=9
        )

        self.assertEqual(Block.objects.count(), 1)
        self._post_response(self.user, event, {'block_book': 'yes'})

        self.assertEqual(block.bookings.count(), 10)
        self.assertTrue(block.full)
        # 5 class blocks do not qualify for free classes, no free class block
        # created
        self.assertEqual(Block.objects.count(), 1)

    def test_create_booking_sets_flag_on_session(self):
        self.client.login(username=self.user.username, password='test')
        event = mommy.make_recipe('booking.future_EV')
        self.client.post(
            reverse('booking:book_event', kwargs={'event_slug': event.slug}),
            {'event': event.id}
        )
        booking = Booking.objects.latest('id')
        self.assertIn(
            'booking_created_{}'.format(booking.id), self.client.session.keys()
        )

    def test_create_booking_redirects_to_events_if_flag_on_session(self):
        """
        When a booking is created, "booking_created" flag is set on the
        session so that if the user clicks the back button they get returned
        to the events list page instead of the create booking page again
        """
        event = mommy.make_recipe('booking.future_EV')
        url = reverse('booking:book_event', kwargs={'event_slug': event.slug})
        self.client.login(username=self.user.username, password='test')
        booking = mommy.make_recipe(
            'booking.booking', event=event, user=self.user
        )

        # with no flag, redirects to duplicate booking page
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(
            resp.url,
            reverse(
                'booking:duplicate_booking', kwargs={'event_slug': event.slug}
            )
        )

        # with flag, redirects to events page
        booking.delete()
        self.client.post(
            reverse('booking:book_event', kwargs={'event_slug': event.slug}),
            {'event': event.id}
        )
        booking = Booking.objects.latest('id')
        self.assertIn(
            'booking_created_{}'.format(booking.id), self.client.session.keys()
        )

        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(resp.url, reverse('booking:events'))
        # flag has been removed
        self.assertNotIn(
            'booking_created_{}'.format(booking.id), self.client.session.keys()
        )

    def test_create_booking_redirects_to_classes_if_flag_on_session(self):
        event = mommy.make_recipe('booking.future_PC')
        url = reverse('booking:book_event', kwargs={'event_slug': event.slug})
        self.client.login(username=self.user.username, password='test')

        self.client.post(url, {'event': event.id})
        booking = Booking.objects.latest('id')
        self.assertIn(
            'booking_created_{}'.format(booking.id), self.client.session.keys()
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(resp.url, reverse('booking:lessons'))
        self.assertNotIn(
            'booking_created_{}'.format(booking.id), self.client.session.keys()
        )

    def test_create_booking_redirects_to_classes_if_flag_on_session(self):
        event = mommy.make_recipe('booking.future_RH')
        url = reverse('booking:book_event', kwargs={'event_slug': event.slug})
        self.client.login(username=self.user.username, password='test')

        self.client.post(url, {'event': event.id})
        booking = Booking.objects.latest('id')
        self.assertIn(
            'booking_created_{}'.format(booking.id), self.client.session.keys()
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(resp.url, reverse('booking:room_hires'))
        self.assertNotIn(
            'booking_created_{}'.format(booking.id), self.client.session.keys()
        )

    def test_reopen_booking_does_not_redirect_if_flag_on_session(self):
        """
        A user might create a booking, cancel it, and immediately try to
        rebook while the booking_created flag is still on the session.  In this
        case, allow the booking page to be retrieved
        """
        event = mommy.make_recipe('booking.future_EV')
        url = reverse('booking:book_event', kwargs={'event_slug': event.slug})
        self.client.login(username=self.user.username, password='test')

        self.client.post(url, {'event': event.id})
        booking = Booking.objects.latest('id')
        self.assertIn(
            'booking_created_{}'.format(booking.id), self.client.session.keys()
        )

        booking.status = 'CANCELLED'
        booking.save()
        # with flag, still gets the create booking page
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_not_added_to_mailing_list_on_first_pole_class_booking(self):
        # functionality to add user to mailing list on first class has been
        # removed
        event = mommy.make_recipe('booking.future_PC')
        url = reverse('booking:book_event', kwargs={'event_slug': event.slug})
        self.client.login(username=self.user.username, password='test')
        self.assertFalse(self.user.subscribed())
        self.assertFalse(Booking.objects.filter(user=self.user).exists())

        self.client.post(url, {'event': event.id})
        self.user.refresh_from_db()
        self.assertFalse(self.user.subscribed())
        self.assertEqual(self.mock_request.call_count, 0)

    def test_not_added_to_mailing_list_on_subsequent_pole_class_booking(self):
        event = mommy.make_recipe('booking.future_PC')
        url = reverse('booking:book_event', kwargs={'event_slug': event.slug})
        self.client.login(username=self.user.username, password='test')

        # Unsubscribes user
        self.assertFalse(self.user.subscribed())

        # Second booking
        self.mock_request.reset_mock()
        event1 = mommy.make_recipe('booking.future_PC')
        url = reverse('booking:book_event', kwargs={'event_slug': event1.slug})
        self.client.post(url, {'event': event1.id})
        self.user.refresh_from_db()
        self.assertFalse(self.user.subscribed())
        self.assertEqual(self.mock_request.call_count, 0)

    def test_not_added_to_mailing_list_on_event_booking(self):
        event = mommy.make_recipe('booking.future_EV')
        url = reverse('booking:book_event', kwargs={'event_slug': event.slug})
        self.client.login(username=self.user.username, password='test')
        self.assertFalse(self.user.subscribed())
        self.assertFalse(Booking.objects.filter(user=self.user).exists())

        self.client.post(url, {'event': event.id})
        self.user.refresh_from_db()
        self.assertFalse(self.user.subscribed())
        self.assertEqual(self.mock_request.call_count, 0)


class BookingErrorRedirectPagesTests(TestSetupMixin, TestCase):

    def _get_duplicate_booking(self, user, event):
        url = reverse(
            'booking:duplicate_booking', kwargs={'event_slug': event.slug}
        )
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return duplicate_booking(request, event.slug)

    def _get_fully_booked(self, user, event):
        url = reverse(
            'booking:fully_booked', kwargs={'event_slug': event.slug}
        )
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return fully_booked(request, event.slug)

    def _get_update_booking_cancelled(self, user, booking):
        url = reverse(
            'booking:update_booking_cancelled', kwargs={'pk': booking.pk}
        )
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return update_booking_cancelled(request, booking.pk)

    def test_duplicate_event_booking(self):
        """
        Get the duplicate booking page with the event context
        """
        event = mommy.make_recipe('booking.future_EV')
        resp = self._get_duplicate_booking(self.user, event)
        self.assertIn(event.name, str(resp.content))

        poleclass = mommy.make_recipe('booking.future_PC')
        resp = self._get_duplicate_booking(self.user, poleclass)
        self.assertIn(poleclass.name, str(resp.content))

        roomhire = mommy.make_recipe('booking.future_RH')
        resp = self._get_duplicate_booking(self.user, roomhire)
        self.assertIn(roomhire.name, str(resp.content))

    def test_fully_booked(self):
        """
        Get the fully booked page with the event context
        """
        event = mommy.make_recipe('booking.future_EV')
        resp = self._get_fully_booked(self.user, event)
        self.assertIn(event.name, str(resp.content))

        poleclass = mommy.make_recipe('booking.future_PC')
        resp = self._get_fully_booked(self.user, poleclass)
        self.assertIn(poleclass.name, str(resp.content))

        roomhire = mommy.make_recipe('booking.future_RH')
        resp = self._get_fully_booked(self.user, roomhire)
        self.assertIn(roomhire.name, str(resp.content))

    def test_update_booking_cancelled(self):
        """
        Get the redirected page when trying to update a cancelled booking
        with the event context
        """
        event = mommy.make_recipe('booking.future_EV')
        booking = mommy.make_recipe(
            'booking.booking', status='CANCELLED', event=event
        )
        resp = self._get_update_booking_cancelled(self.user, booking)
        self.assertIn(event.name, str(resp.content))

        poleclass = mommy.make_recipe('booking.future_PC')
        booking = mommy.make_recipe(
            'booking.booking', status='CANCELLED', event=poleclass
        )
        resp = self._get_update_booking_cancelled(self.user, booking)
        self.assertIn(poleclass.name, str(resp.content))

        roomhire = mommy.make_recipe('booking.future_RH')
        booking = mommy.make_recipe(
            'booking.booking', status='CANCELLED', event=roomhire
        )
        resp = self._get_update_booking_cancelled(self.user, booking)
        self.assertIn(roomhire.name, str(resp.content))

    def test_update_booking_cancelled_for_full_event(self):
        """
        Get the redirected page when trying to update a cancelled booking
        for an event that's now full
        """
        event = mommy.make_recipe('booking.future_EV', max_participants=3)
        booking = mommy.make_recipe(
            'booking.booking', status='CANCELLED', event=event
        )
        mommy.make_recipe(
            'booking.booking', status='OPEN', event=event, _quantity=3
        )
        # check event is full; we need to get the event again as spaces_left is
        # cached property
        event = Event.objects.get(id=event.id)
        self.assertEqual(event.spaces_left, 0)
        resp = self._get_update_booking_cancelled(self.user, booking)
        self.assertIn(event.name, str(resp.content))
        self.assertIn("This event is now full", str(resp.content))

    def test_already_cancelled(self):
        """
        Get the redirected page when trying to cancel a cancelled booking
        for an event that's now full
        """
        booking = mommy.make_recipe('booking.booking', status='CANCELLED')
        resp = self.client.get(
            reverse('booking:already_cancelled', args=[booking.id])
        )
        self.assertIn(booking.event.name, str(resp.content))

    def test_cannot_cancel_after_cancellation_period(self):
        """
        Get the cannot cancel page with the event context
        """
        event = mommy.make_recipe('booking.future_EV')
        url = reverse(
            'booking:cancellation_period_past',
            kwargs={'event_slug': event.slug}
        )
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = self.user
        messages = FallbackStorage(request)
        request._messages = messages
        resp = cancellation_period_past(request, event.slug)
        self.assertIn(event.name, str(resp.content))

    def test_has_active_block(self):
        response = self.client.get(reverse('booking:has_active_block'))
        self.assertEqual(response.status_code, 200)

    def test_already_paid(self):
        booking = mommy.make_recipe('booking.booking', paid=True)
        resp = self.client.get(
            reverse('booking:already_paid', args=[booking.id])
        )
        self.assertIn(booking.event.name, str(resp.content))

    def test_disclaimer_required(self):
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(reverse('booking:disclaimer_required'))
        self.assertIn(
            'Please submit a disclaimer form and try again',
            format_content(str(resp.content))
        )


class BookingDeleteViewTests(TestSetupMixin, TestCase):

    def _delete_response(self, user, booking):
        url = reverse('booking:delete_booking', args=[booking.id])
        session = _create_session()
        request = self.factory.delete(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        view = BookingDeleteView.as_view()
        return view(request, pk=booking.id)

    def test_get_delete_booking_page(self):
        """
        Get the delete booking page with the event context
        """
        event = mommy.make_recipe('booking.future_EV')
        booking = mommy.make_recipe('booking.booking', event=event, user=self.user)
        url = reverse(
            'booking:delete_booking', args=[booking.id]
        )
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = self.user
        messages = FallbackStorage(request)
        request._messages = messages
        view = BookingDeleteView.as_view()
        resp = view(request, pk=booking.id)
        self.assertEqual(resp.context_data['event'], event)

    def test_cancel_booking(self):
        """
        Test deleting a booking
        """
        event = mommy.make_recipe('booking.future_EV')
        booking = mommy.make_recipe('booking.booking', event=event,
                                    user=self.user, paid=True)
        self.assertEqual(Booking.objects.all().count(), 1)
        self._delete_response(self.user, booking)
        # after cancelling, the booking is still there, but status has changed
        self.assertEqual(Booking.objects.all().count(), 1)
        booking = Booking.objects.get(id=booking.id)
        self.assertEqual('CANCELLED', booking.status)

    def test_cancel_booking_from_shopping_basket_ajax(self):
        """
        Test deleting a booking from shopping basket (ajax)
        """
        event = mommy.make_recipe('booking.future_PC')
        booking = mommy.make_recipe('booking.booking', event=event,
                                    user=self.user, paid=True)
        self.assertEqual(Booking.objects.all().count(), 1)

        url = reverse('booking:delete_booking', args=[booking.id]) + '?ref=basket'
        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b'Booking cancelled')

        # after cancelling, the booking is still there, but status has changed
        self.assertEqual(Booking.objects.all().count(), 1)
        booking = Booking.objects.get(id=booking.id)
        self.assertEqual('CANCELLED', booking.status)
        self.assertEqual(len(mail.outbox), 1)

    def test_cancel_unpaid_booking(self):
        """
        Test deleting a booking; unpaid, not rebooked, no paypal transaction associated
        """
        event = mommy.make_recipe('booking.future_PC')
        booking = mommy.make_recipe('booking.booking', event=event, user=self.user, paid=False)
        self.assertEqual(Booking.objects.all().count(), 1)
        self._delete_response(self.user, booking)
        # booking deleted
        self.assertEqual(Booking.objects.all().count(), 0)
        # no emails sent
        self.assertEqual(len(mail.outbox), 0)

    def test_cancel_unpaid_rebooking(self):
        """
        Test deleting a rebooking; unpaid, set to cancelled
        """
        event = mommy.make_recipe('booking.future_PC')
        booking = mommy.make_recipe(
            'booking.booking', event=event, user=self.user, paid=False,
            date_rebooked=datetime(2018, 1, 1, tzinfo=timezone.utc)
        )
        self.assertEqual(Booking.objects.all().count(), 1)
        self._delete_response(self.user, booking)
        # after cancelling, the booking is still there, but status has changed
        self.assertEqual(Booking.objects.all().count(), 1)
        booking = Booking.objects.get(id=booking.id)
        self.assertEqual('CANCELLED', booking.status)

        # one cancel email sent
        self.assertEqual(len(mail.outbox), 1)

    def test_cancel_unpaid_with_paypal_transaction(self):
        """
        Test deleting an unpaid booking with an associated paypal transaction (i.e. refunded);
        set to cancelled
        """
        event = mommy.make_recipe('booking.future_PC')
        booking = mommy.make_recipe(
            'booking.booking', event=event, user=self.user, paid=False
        )
        ppt = create_booking_paypal_transaction(self.user, booking)
        ppt.transaction_id = 'test'
        ppt.save()

        self.assertEqual(Booking.objects.all().count(), 1)
        self._delete_response(self.user, booking)
        # after cancelling, the booking is still there, but status has changed
        self.assertEqual(Booking.objects.all().count(), 1)
        booking = Booking.objects.get(id=booking.id)
        self.assertEqual('CANCELLED', booking.status)

        # one cancel email sent
        self.assertEqual(len(mail.outbox), 1)

    def test_cancelling_only_this_booking(self):
        """
        Test cancelling a booking when user has more than one
        """
        events = mommy.make_recipe('booking.future_EV', _quantity=3)

        for event in events:
            mommy.make_recipe('booking.booking', user=self.user, event=event, paid=True)

        self.assertEqual(Booking.objects.all().count(), 3)
        booking = Booking.objects.all()[0]
        self._delete_response(self.user, booking)
        self.assertEqual(Booking.objects.all().count(), 3)
        cancelled_bookings = Booking.objects.filter(status='CANCELLED')
        self.assertEqual([cancelled.id for cancelled in cancelled_bookings],
                         [booking.id])

    def test_cancelling_booking_sets_payment_confirmed_to_False(self):
        event_with_cost = mommy.make_recipe('booking.future_EV', cost=10)
        booking = mommy.make_recipe('booking.booking', user=self.user,
                                    event=event_with_cost)
        booking.confirm_space()
        self.assertTrue(booking.payment_confirmed)
        self._delete_response(self.user, booking)

        booking = Booking.objects.get(user=self.user,
                                      event=event_with_cost)
        self.assertEqual('CANCELLED', booking.status)
        self.assertFalse(booking.payment_confirmed)

    def test_cancelling_booking_with_block(self):
        """
        Test that cancelling a booking bought with a block removes the
        booking and updates the block
        """
        event_type = mommy.make_recipe('booking.event_type_PC')

        event = mommy.make_recipe('booking.future_PC', event_type=event_type)
        blocktype = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type
        )
        block = mommy.make_recipe(
            'booking.block', block_type=blocktype, user=self.user
        )
        booking = mommy.make_recipe(
            'booking.booking', event=event, user=self.user, block=block
        )
        booking.confirm_space()
        block = Block.objects.get(user=self.user)
        self.assertEqual(block.bookings_made(), 1)

        # cancel booking
        self._delete_response(self.user, booking)

        booking = Booking.objects.get(user=self.user, event=event)
        self.assertEqual('CANCELLED', booking.status)
        self.assertFalse(booking.block)
        self.assertFalse(booking.paid)

        block = Block.objects.get(user=self.user)
        self.assertEqual(block.bookings_made(), 0)

    @patch("booking.views.booking_views.timezone")
    def test_can_cancel_after_cancellation_period(self, mock_tz):
        """
        Test trying to cancel after cancellation period
        Cancellation is allowed but shows warning message
        """
        mock_tz.now.return_value = datetime(2015, 2, 1, tzinfo=timezone.utc)
        event = mommy.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 2, tzinfo=timezone.utc),
            cancellation_period=48
        )
        booking = mommy.make_recipe(
            'booking.booking', event=event, user=self.user,
            paid=True
        )

        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(url)

        self.assertEqual(200, resp.status_code)
        self.assertIn(
            'If you continue, you will not be eligible for any refund or '
            'transfer credit.',
            resp.rendered_content
        )

    @patch("booking.views.booking_views.timezone")
    def test_cancelling_after_cancellation_period(self, mock_tz):
        """
        Test cancellation after cancellation period sets no_show to True
        """
        mock_tz.now.return_value = datetime(2015, 2, 1, tzinfo=timezone.utc)
        event = mommy.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 2, tzinfo=timezone.utc),
            cancellation_period=48
        )
        booking = mommy.make_recipe(
            'booking.booking', event=event, user=self.user, paid=True
        )

        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        resp = self.client.delete(url, follow=True)
        self.assertIn(
            'Please note that this booking is not eligible for refunds or '
            'transfer credit as the allowed cancellation period has passed.',
            resp.rendered_content
        )
        booking.refresh_from_db()
        self.assertTrue(booking.no_show)
        self.assertEqual(booking.status, 'OPEN')
        self.assertTrue(booking.paid)

    @patch("booking.views.booking_views.timezone")
    def test_cancelling_block_paid_after_cancellation_period(self, mock_tz):
        """
        Test cancellation after cancellation period for block paid is allowed for
        15 mins after booking time
        """
        mock_tz.now.return_value = datetime(2015, 2, 1, 10, 0, tzinfo=timezone.utc)
        event = mommy.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 2, tzinfo=timezone.utc),
            cancellation_period=48
        )
        block = mommy.make_recipe('booking.block_5', user=self.user, paid=True)
        # booking made 10 mins ago
        booking = mommy.make_recipe(
            'booking.booking', event=event, user=self.user, block=block, paid=True,
            date_booked=datetime(2015, 2, 1, 9, 50, tzinfo=timezone.utc)
        )

        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        resp = self.client.delete(url, follow=True)
        self.assertNotIn(
            'Please note that this booking is not eligible for refunds or '
            'transfer credit as the allowed cancellation period has passed.',
            resp.rendered_content
        )
        booking.refresh_from_db()
        self.assertFalse(booking.no_show)
        self.assertEqual(booking.status, 'CANCELLED')
        self.assertFalse(booking.paid)
        self.assertIsNone(booking.block)

        # delete booking so it doesn't have a rebooked date
        booking.delete()
        # block booking made 20 mins ago
        booking = mommy.make_recipe(
            'booking.booking', event=event, user=self.user, block=block, paid=True,
            date_booked=datetime(2015, 2, 1, 9, 40, tzinfo=timezone.utc)
        )
        url = reverse('booking:delete_booking', args=[booking.id])
        resp = self.client.delete(url, follow=True)

        self.assertIn(
            'Please note that this booking is not eligible for refunds or '
            'transfer credit as the allowed cancellation period has passed.',
            resp.rendered_content
        )
        booking.refresh_from_db()
        self.assertTrue(booking.no_show)
        self.assertEqual(booking.status, 'OPEN')
        self.assertTrue(booking.paid)
        self.assertEqual(booking.block, block)

    @patch("booking.views.booking_views.timezone")
    def test_cancelling_rebooked_block_paid_after_cancellation_period(self, mock_tz):
        """
        Test cancellation after cancellation period for block paid is allowed for
        15 mins after booking time
        """
        mock_tz.now.return_value = datetime(2015, 2, 1, 10, 0, tzinfo=timezone.utc)
        event = mommy.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 2, tzinfo=timezone.utc),
            cancellation_period=48
        )
        block = mommy.make_recipe('booking.block_5', user=self.user, paid=True)
        # booking made 60 mins ago, rebooked 10 mins ago
        booking = mommy.make_recipe(
            'booking.booking', event=event, user=self.user, block=block, paid=True,
            date_booked=datetime(2015, 2, 1, 9, 0, tzinfo=timezone.utc),
            date_rebooked=datetime(2015, 2, 1, 9, 50, tzinfo=timezone.utc)
        )

        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        resp = self.client.delete(url, follow=True)
        self.assertNotIn(
            'Please note that this booking is not eligible for refunds or '
            'transfer credit as the allowed cancellation period has passed.',
            resp.rendered_content
        )
        booking.refresh_from_db()
        self.assertFalse(booking.no_show)
        self.assertEqual(booking.status, 'CANCELLED')
        self.assertFalse(booking.paid)
        self.assertIsNone(booking.block)

    def test_cancelling_free_class(self):
        """
        Cancelling a free class changes paid, payment_confirmed and free_class
        to False
        """
        event_with_cost = mommy.make_recipe('booking.future_EV', cost=10)
        booking = mommy.make_recipe('booking.booking', user=self.user,
                                    event=event_with_cost)
        booking.free_class = True
        booking.save()
        booking.confirm_space()
        self.assertTrue(booking.payment_confirmed)
        self.assertTrue(booking.free_class)
        self._delete_response(self.user, booking)

        booking = Booking.objects.get(user=self.user,
                                      event=event_with_cost)
        self.assertEqual('CANCELLED', booking.status)
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)
        self.assertFalse(booking.free_class)

    def test_cannot_cancel_twice(self):
        event = mommy.make_recipe('booking.future_EV')
        booking = mommy.make_recipe('booking.booking', event=event,
                                    user=self.user, paid=True)
        self.assertEqual(Booking.objects.all().count(), 1)
        self._delete_response(self.user, booking)
        booking.refresh_from_db()
        self.assertEqual('CANCELLED', booking.status)

        # try deleting again, should redirect
        resp = self._delete_response(self.user, booking)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(
            resp.url, reverse('booking:already_cancelled', args=[booking.id])
        )

    def test_event_with_cancellation_not_allowed(self):
        """
        Can still be cancelled but not refundable
        Paid booking stays OPEN but is set to no_show
        Unpaid booking is deleted
        """
        event = mommy.make_recipe(
            'booking.future_PC', allow_booking_cancellation=False
        )
        paid_booking = mommy.make_recipe('booking.booking', event=event,
                                    user=self.user, paid=True)
        self._delete_response(self.user, paid_booking)
        paid_booking.refresh_from_db()
        # still open, but no_show
        self.assertEqual('OPEN', paid_booking.status)
        self.assertTrue(paid_booking.no_show)

        event1 = mommy.make_recipe(
            'booking.future_PC', allow_booking_cancellation=False
        )
        unpaid_booking = mommy.make_recipe(
            'booking.booking', event=event1, user=self.user
        )
        self._delete_response(self.user, unpaid_booking)
        self.assertFalse(Booking.objects.filter(id=unpaid_booking.id).exists())

        # no transfer blocks made
        self.assertFalse(Block.objects.filter(user=self.user).exists())

    def test_cancelling_sends_email_to_user_and_studio_if_applicable(self):
        """ emails are always sent to user; only sent to studio if previously
        direct paid and not eligible for transfer
        """
        event_with_cost = mommy.make_recipe('booking.future_EV', cost=10)
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event_with_cost, paid=True
        )
        self._delete_response(self.user, booking)
        # 2 emails sent for cancelled paid booking
        self.assertEqual(len(mail.outbox), 2)
        user_mail = mail.outbox[0]
        self.assertEqual(user_mail.to, [self.user.email])

        booking.status = 'OPEN'
        # make a block that isn't expired
        booking.block = mommy.make_recipe(
            'booking.block_5', start_date=timezone.now()
        )
        booking.save()
        self._delete_response(self.user, booking)
        # only 1 email sent for cancelled booking paid with block
        self.assertEqual(len(mail.outbox), 3)
        user_mail = mail.outbox[2]
        self.assertEqual(user_mail.to, [self.user.email])

        booking.refresh_from_db()
        booking.status = 'OPEN'
        booking.confirm_space()
        booking.save()
        self._delete_response(self.user, booking)
        # 2 emails sent this time for direct paid booking
        self.assertEqual(len(mail.outbox), 5)
        user_mail = mail.outbox[3]
        studio_mail = mail.outbox[4]
        self.assertEqual(user_mail.to, [self.user.email])
        self.assertEqual(studio_mail.to, [settings.DEFAULT_STUDIO_EMAIL])

    @patch('booking.views.booking_views.send_mail')
    def test_errors_sending_emails(self, mock_send_emails):
        mock_send_emails.side_effect = Exception('Error sending mail')
        event = mommy.make_recipe(
            'booking.future_PC', cost=10, max_participants=3
        )
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True
        )

        self._delete_response(self.user, booking)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [settings.SUPPORT_EMAIL])
        self.assertEqual(
            mail.outbox[0].subject,
            '{} An error occurred! '
            '(DeleteBookingView - cancelled email)'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
            )
        )
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'CANCELLED')

    def test_cancelling_full_event_sends_waiting_list_emails(self):
        event = mommy.make_recipe(
            'booking.future_EV', cost=10, max_participants=3
        )
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event
        )
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        wluser = mommy.make(
            WaitingListUser, event=event, user__email='wl@test.com'
        )

        self._delete_response(self.user, booking)
        # unpaid booking deleted, only waiting list emails sent
        self.assertEqual(len(mail.outbox), 1)
        waiting_list_mail = mail.outbox[0]
        self.assertEqual(waiting_list_mail.bcc, [wluser.user.email])

    @patch('booking.views.booking_views.send_mail')
    @patch('booking.views.booking_views.send_waiting_list_email')
    def test_errors_sending_waiting_list_emails(
            self, mock_send_wl_emails, mock_send_emails):
        mock_send_emails.side_effect = Exception('Error sending mail')
        mock_send_wl_emails.side_effect = Exception('Error sending mail')
        event = mommy.make_recipe(
            'booking.future_EV', cost=10, max_participants=3
        )
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event
        )
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        mommy.make(
            WaitingListUser, event=event, user__email='wl@test.com'
        )

        self._delete_response(self.user, booking)
        self.assertEqual(len(mail.outbox), 1)

        self.assertEqual(mail.outbox[0].to, [settings.SUPPORT_EMAIL])
        self.assertEqual(
            mail.outbox[0].subject,
            '{} An error occurred! '
            '(DeleteBookingView - waiting list email)'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
            )
        )

    @patch('booking.views.booking_views.send_mail')
    @patch('booking.views.booking_views.send_waiting_list_email')
    @patch('booking.email_helpers.send_mail')
    def test_errors_sending_all_emails(
            self, mock_send, mock_send_wl_emails, mock_send_emails):
        mock_send.side_effect = Exception('Error sending mail')
        mock_send_emails.side_effect = Exception('Error sending mail')
        mock_send_wl_emails.side_effect = Exception('Error sending mail')
        event = mommy.make_recipe(
            'booking.future_PC', cost=10, max_participants=3
        )
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True
        )
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        mommy.make(
            WaitingListUser, event=event, user__email='wl@test.com'
        )

        self._delete_response(self.user, booking)
        self.assertEqual(len(mail.outbox), 0)

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'CANCELLED')

    def test_cancel_direct_paid_CL_creates_transfer_blocktype(self):
        event = mommy.make_recipe(
            'booking.future_PC', cost=10, max_participants=3
        )
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True,
            payment_confirmed=True
        )

        self.assertFalse(BlockType.objects.exists())
        self._delete_response(self.user, booking)

        self.assertEqual(BlockType.objects.count(), 1)
        self.assertEqual(BlockType.objects.first().identifier, 'transferred')
        self.assertFalse(BlockType.objects.first().active)
        self.assertEqual(BlockType.objects.first().size, 1)
        self.assertEqual(BlockType.objects.first().event_type, event.event_type)
        self.assertEqual(BlockType.objects.first().duration, 1)

    def test_cancel_free_non_block_CL_creates_transfer_blocktype(self):
        event = mommy.make_recipe(
            'booking.future_PC', cost=10, max_participants=3
        )
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event, free_class=True,
            paid=True, payment_confirmed=True
        )

        self.assertFalse(BlockType.objects.exists())
        self._delete_response(self.user, booking)

        self.assertEqual(BlockType.objects.count(), 1)
        self.assertEqual(BlockType.objects.first().identifier, 'transferred')
        self.assertFalse(BlockType.objects.first().active)
        self.assertEqual(BlockType.objects.first().size, 1)
        self.assertEqual(BlockType.objects.first().event_type, event.event_type)
        self.assertEqual(BlockType.objects.first().duration, 1)

    def test_cancel_direct_paid_RH_creates_transfer_blocktype(self):
        event = mommy.make_recipe(
            'booking.future_RH', cost=10, max_participants=3
        )
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True,
            payment_confirmed=True
        )

        self.assertFalse(BlockType.objects.exists())
        self._delete_response(self.user, booking)

        self.assertEqual(BlockType.objects.count(), 1)
        self.assertEqual(BlockType.objects.first().identifier, 'transferred')
        self.assertFalse(BlockType.objects.first().active)
        self.assertEqual(BlockType.objects.first().size, 1)
        self.assertEqual(BlockType.objects.first().event_type, event.event_type)
        self.assertEqual(BlockType.objects.first().duration, 1)

    def test_free_non_block_RH_creates_transfer_blocktype(self):
        event = mommy.make_recipe(
            'booking.future_RH', cost=10, max_participants=3
        )
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True,
            payment_confirmed=True, free_class=True
        )

        self.assertFalse(BlockType.objects.exists())
        self._delete_response(self.user, booking)

        self.assertEqual(BlockType.objects.count(), 1)
        self.assertEqual(BlockType.objects.first().identifier, 'transferred')
        self.assertFalse(BlockType.objects.first().active)
        self.assertEqual(BlockType.objects.first().size, 1)
        self.assertEqual(BlockType.objects.first().event_type, event.event_type)
        self.assertEqual(BlockType.objects.first().duration, 1)

    def test_cancel_direct_paid_EV_does_not_creates_transfer_blocktype(self):
        event = mommy.make_recipe(
            'booking.future_EV', cost=10, max_participants=3
        )
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True,
            payment_confirmed=True
        )

        self.assertFalse(BlockType.objects.exists())
        self._delete_response(self.user, booking)

        self.assertFalse(BlockType.objects.exists())

    def test_cancel_free_non_block_EV_does_not_creates_transfer_blocktype(self):
        event = mommy.make_recipe(
            'booking.future_EV', cost=10, max_participants=3
        )
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True,
            payment_confirmed=True, free_class=True
        )

        self.assertFalse(BlockType.objects.exists())
        self._delete_response(self.user, booking)

        self.assertFalse(BlockType.objects.exists())

    def test_cancel_direct_paid_CL_creates_transfer_block(self):
        """
        transfer block created with transferred booking id set, booking set
        to unpaid, email not sent to studio
        """
        event = mommy.make_recipe(
            'booking.future_PC', cost=10, max_participants=3
        )
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True,
            payment_confirmed=True
        )

        self.assertFalse(Block.objects.exists())
        self._delete_response(self.user, booking)

        booking.refresh_from_db()
        self.assertEqual(Block.objects.count(), 1)
        transfer_block = Block.objects.first()
        self.assertEqual(transfer_block.block_type.identifier, 'transferred')
        self.assertEqual(transfer_block.transferred_booking_id, booking.id)
        self.assertEqual(transfer_block.user,self.user)

        self.assertEqual(booking.status, 'CANCELLED')
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)

        # email set to user only
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_cancel_free_non_block_CL_creates_transfer_block(self):
        """
        transfer block created with transferred booking id set, booking set
        to unpaid, email not sent to studio
        """
        event = mommy.make_recipe(
            'booking.future_PC', cost=10, max_participants=3
        )
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True,
            payment_confirmed=True, free_class=True
        )

        self.assertFalse(Block.objects.exists())
        self._delete_response(self.user, booking)

        booking.refresh_from_db()
        self.assertEqual(Block.objects.count(), 1)
        transfer_block = Block.objects.first()
        self.assertEqual(transfer_block.block_type.identifier, 'transferred')
        self.assertEqual(transfer_block.transferred_booking_id, booking.id)
        self.assertEqual(transfer_block.user,self.user)

        self.assertEqual(booking.status, 'CANCELLED')
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)

        # email set to user only
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_cancel_direct_paid_RH_creates_transfer_block(self):
        event = mommy.make_recipe(
            'booking.future_RH', cost=10, max_participants=3
        )
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True,
            payment_confirmed=True
        )

        self.assertFalse(Block.objects.exists())
        self._delete_response(self.user, booking)

        booking.refresh_from_db()
        self.assertEqual(Block.objects.count(), 1)
        transfer_block = Block.objects.first()
        self.assertEqual(transfer_block.block_type.identifier, 'transferred')
        self.assertEqual(transfer_block.transferred_booking_id, booking.id)
        self.assertEqual(transfer_block.user,self.user)

        self.assertEqual(booking.status, 'CANCELLED')
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)

        # email set to user only
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_cancel_free_non_block_RH_creates_transfer_block(self):
        event = mommy.make_recipe(
            'booking.future_RH', cost=10, max_participants=3
        )
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True,
            payment_confirmed=True, free_class=True
        )

        self.assertFalse(Block.objects.exists())
        self._delete_response(self.user, booking)

        booking.refresh_from_db()
        self.assertEqual(Block.objects.count(), 1)
        transfer_block = Block.objects.first()
        self.assertEqual(transfer_block.block_type.identifier, 'transferred')
        self.assertEqual(transfer_block.transferred_booking_id, booking.id)
        self.assertEqual(transfer_block.user,self.user)

        self.assertEqual(booking.status, 'CANCELLED')
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)

        # email set to user only
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_cancel_direct_paid_EV_does_not_creates_transfer_block(self):
        event = mommy.make_recipe(
            'booking.future_EV', cost=10, max_participants=3
        )
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True,
            payment_confirmed=True
        )

        self.assertFalse(Block.objects.exists())
        self._delete_response(self.user, booking)

        booking.refresh_from_db()
        self.assertFalse(Block.objects.exists())

        # booking is cancelled but not set to unpaid, pending manual refund.
        # Payment confirmed changed to False
        self.assertEqual(booking.status, 'CANCELLED')
        self.assertTrue(booking.paid)
        self.assertFalse(booking.payment_confirmed)

        # email set to user and studio
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertEqual(mail.outbox[1].to, [settings.DEFAULT_STUDIO_EMAIL])

    def test_cancel_free_non_block_EV_does_not_creates_transfer_block(self):
        event = mommy.make_recipe(
            'booking.future_EV', cost=10, max_participants=3
        )
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True,
            payment_confirmed=True, free_class=True
        )

        self.assertFalse(Block.objects.exists())
        self._delete_response(self.user, booking)

        booking.refresh_from_db()
        self.assertFalse(Block.objects.exists())

        # booking is cancelled, set to unpaid
        self.assertEqual(booking.status, 'CANCELLED')
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)

        # email set to user and studio
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertEqual(mail.outbox[1].to, [settings.DEFAULT_STUDIO_EMAIL])

    def test_cancel_non_direct_paid_does_not_create_transfer_block(self):
        """
        unpaid, block paid, free (with block), deposit only paid do not
        create transfers
        """
        self.assertFalse(Block.objects.exists())

        event = mommy.make_recipe('booking.future_PC', cost=10)

        # unpaid
        user = mommy.make_recipe('booking.user')
        make_data_privacy_agreement(user)
        mommy.make_recipe('booking.online_disclaimer', user=user)
        unpaid_booking = mommy.make_recipe(
            'booking.booking', user=user, event=event, paid=False,
        )

        self._delete_response(user, unpaid_booking)

        self.assertFalse(Booking.objects.filter(id=unpaid_booking.id).exists())
        self.assertFalse(
            Block.objects.filter(block_type__identifier='transferred').exists()
        )
        # block paid
        user1 = mommy.make_recipe('booking.user')
        make_data_privacy_agreement(user1)
        mommy.make_recipe('booking.online_disclaimer', user=user1)
        block = mommy.make_recipe(
            'booking.block', block_type__event_type=event.event_type,
            user=user1
        )
        block_booking = mommy.make_recipe(
            'booking.booking', user=user1, event=event, block=block,
        )
        self.assertTrue(block_booking.paid)
        self.assertTrue(block_booking.payment_confirmed)

        self._delete_response(user1, block_booking)

        block_booking.refresh_from_db()
        self.assertFalse(
            Block.objects.filter(block_type__identifier='transferred').exists()
        )

        # free (with block)
        user3 = mommy.make_recipe('booking.user')
        make_data_privacy_agreement(user3)
        mommy.make_recipe('booking.online_disclaimer', user=user3)
        free_block = mommy.make_recipe(
            'booking.block', block_type__event_type=event.event_type,
            block_type__identifier='free class', user=user3
        )
        free_block_booking = mommy.make_recipe(
            'booking.booking', user=user3, event=event, free_class=True,
            block=free_block
        )
        self.assertTrue(free_block_booking.paid)
        self.assertTrue(free_block_booking.payment_confirmed)

        self._delete_response(user3, free_block_booking)

        free_block_booking.refresh_from_db()
        self.assertFalse(
            Block.objects.filter(block_type__identifier='transferred').exists()
        )

        # deposit only paid
        user4 = mommy.make_recipe('booking.user')
        make_data_privacy_agreement(user4)
        mommy.make_recipe('booking.online_disclaimer', user=user4)
        dep_paid_booking = mommy.make_recipe(
            'booking.booking', user=user4, event=event, paid=False,
            payment_confirmed=False, deposit_paid=True
        )

        self._delete_response(user4, dep_paid_booking)

        dep_paid_booking.refresh_from_db()
        self.assertFalse(
            Block.objects.filter(block_type__identifier='transferred').exists()
        )

        # free (without block) DOES create transfer
        user2 = mommy.make_recipe('booking.user')
        make_data_privacy_agreement(user2)
        mommy.make_recipe('booking.online_disclaimer', user=user2)
        free_booking = mommy.make_recipe(
            'booking.booking', user=user2, event=event, free_class=True,
        )
        free_booking.free_class = True
        self.assertTrue(free_booking.paid)
        self.assertTrue(free_booking.payment_confirmed)

        self._delete_response(user2, free_booking)

        free_booking.refresh_from_db()
        self.assertTrue(
            Block.objects.filter(block_type__identifier='transferred').exists()
        )
        block = Block.objects.get(block_type__identifier='transferred')
        self.assertEqual(block.user, user2)
        self.assertEqual(block.transferred_booking_id, free_booking.id)

        # and finally, direct paid
        user5 = mommy.make_recipe('booking.user')
        make_data_privacy_agreement(user5)
        mommy.make_recipe('booking.online_disclaimer', user=user5)
        direct_paid_booking = mommy.make_recipe(
            'booking.booking', user=user5, event=event, paid=True,
            payment_confirmed=True
        )

        self._delete_response(user5, direct_paid_booking)
        direct_paid_booking.refresh_from_db()
        self.assertEquals(
            Block.objects.filter(block_type__identifier='transferred').count(),
            2
        )
        block = Block.objects.latest('id')
        self.assertEqual(block.user, user5)
        self.assertEqual(block.transferred_booking_id, direct_paid_booking.id)

    def test_cancel_expired_block_paid_creates_transfer_block(self):
        """
        block paid, but block now expired, does create transfers for PC and RH
        """
        self.assertFalse(Block.objects.exists())

        pc = mommy.make_recipe('booking.future_PC', cost=10)
        ev = mommy.make_recipe('booking.future_EV', cost=10)
        rh = mommy.make_recipe('booking.future_RH', cost=10)

        # PC expired block paid
        user1 = mommy.make_recipe('booking.user')
        make_data_privacy_agreement(user1)
        mommy.make_recipe('booking.online_disclaimer', user=user1)
        block_pc = mommy.make_recipe(
            'booking.block', block_type__event_type=pc.event_type,
            block_type__duration=2,
            user=user1, start_date=timezone.now() - timedelta(days=100)
        )
        pc_block_booking = mommy.make_recipe(
            'booking.booking', user=user1, event=pc, block=block_pc,
        )
        self.assertTrue(pc_block_booking.paid)
        self.assertTrue(pc_block_booking.payment_confirmed)
        self.assertTrue(block_pc.expired)

        self._delete_response(user1, pc_block_booking)

        pc_block_booking.refresh_from_db()
        self.assertTrue(
            Block.objects.filter(
                block_type__identifier='transferred',
                transferred_booking_id=pc_block_booking.id
            ).exists()
        )

        # RH expired block paid
        block_rh = mommy.make_recipe(
            'booking.block', block_type__event_type=rh.event_type,
            block_type__duration=2,
            user=user1, start_date=timezone.now() - timedelta(days=100)
        )
        rh_block_booking = mommy.make_recipe(
            'booking.booking', user=user1, event=rh, block=block_rh,
        )
        self.assertTrue(rh_block_booking.paid)
        self.assertTrue(rh_block_booking.payment_confirmed)
        self.assertTrue(block_rh.expired)

        self._delete_response(user1, rh_block_booking)

        rh_block_booking.refresh_from_db()
        self.assertTrue(
            Block.objects.filter(
                block_type__identifier='transferred',
                transferred_booking_id=rh_block_booking.id
            ).exists()
        )

        # EV expired block paid
        block_ev = mommy.make_recipe(
            'booking.block', block_type__event_type=ev.event_type,
            block_type__duration=2,
            user=user1, start_date=timezone.now() - timedelta(days=100)
        )
        ev_block_booking = mommy.make_recipe(
            'booking.booking', user=user1, event=ev, block=block_ev,
        )
        self.assertTrue(ev_block_booking.paid)
        self.assertTrue(ev_block_booking.payment_confirmed)
        self.assertTrue(block_ev.expired)

        self._delete_response(user1, ev_block_booking)

        ev_block_booking.refresh_from_db()
        self.assertFalse(
            Block.objects.filter(
                block_type__identifier='transferred',
                transferred_booking_id=ev_block_booking.id
            ).exists()
        )

    def test_cancel_booking_from_shopping_basket_non_ajax(self):
        """
        Test deleting a booking from basket returns to basket
        """
        event = mommy.make_recipe('booking.future_EV')
        booking = mommy.make_recipe('booking.booking', event=event,
                                    user=self.user, paid=True)
        self.assertEqual(Booking.objects.all().count(), 1)

        self.client.login(username=self.user.username, password='test')
        url = reverse('booking:delete_booking', args=[booking.id]) \
              + '?next=shopping_basket'
        resp = self.client.post(url)
        # after cancelling, the booking is still there, but status has changed
        self.assertEqual(Booking.objects.all().count(), 1)
        booking.refresh_from_db()
        self.assertEqual('CANCELLED', booking.status)

        # redirects back to shopping basket
        self.assertIn(resp.url, reverse('booking:shopping_basket'))

    def test_cancel_booking_from_shopping_basket_with_booking_voucher_code(self):
        """
        Test deleting a booking from basket with code returns with code in get
        """
        event = mommy.make_recipe('booking.future_EV')
        booking = mommy.make_recipe('booking.booking', event=event,
                                    user=self.user, paid=True)
        self.assertEqual(Booking.objects.all().count(), 1)

        self.client.login(username=self.user.username, password='test')
        url = reverse('booking:delete_booking', args=[booking.id]) \
              + '?next=shopping_basket&booking_code=foo'
        resp = self.client.post(url)
        # after cancelling, the booking is still there, but status has changed
        self.assertEqual(Booking.objects.all().count(), 1)
        booking.refresh_from_db()
        self.assertEqual('CANCELLED', booking.status)

        # redirects back to shopping basket with code
        self.assertIn(
            resp.url, reverse('booking:shopping_basket') + '?booking_code=foo'
        )

    def test_cancel_booking_from_shopping_basket_with_block_voucher_code(self):
        """
        Test deleting a booking from basket with code returns with code in get
        """
        event = mommy.make_recipe('booking.future_EV')
        booking = mommy.make_recipe('booking.booking', event=event,
                                    user=self.user, paid=True)
        self.assertEqual(Booking.objects.all().count(), 1)

        self.client.login(username=self.user.username, password='test')
        url = reverse('booking:delete_booking', args=[booking.id]) \
              + '?next=shopping_basket&block_code=foo'
        resp = self.client.post(url)
        # after cancelling, the booking is still there, but status has changed
        self.assertEqual(Booking.objects.all().count(), 1)
        booking.refresh_from_db()
        self.assertEqual('CANCELLED', booking.status)

        # redirects back to shopping basket with code
        self.assertIn(
            resp.url, reverse('booking:shopping_basket') + '?block_code=foo'
        )

    def test_cancel_booking_with_filter_and_tab_and_page(self):
        """
        Test deleting a booking from events with filter, tab and page returns with
        params
        """
        event = mommy.make_recipe('booking.future_EV')
        booking = mommy.make_recipe('booking.booking', event=event,
                                    user=self.user, paid=True)
        self.assertEqual(Booking.objects.all().count(), 1)

        self.client.login(username=self.user.username, password='test')
        url = reverse('booking:delete_booking', args=[booking.id]) + \
              '?next=events&filter=foo&tab=1&page=1'
        resp = self.client.post(url)
        # after cancelling, the booking is still there, but status has changed
        self.assertEqual(Booking.objects.all().count(), 1)
        booking.refresh_from_db()
        self.assertEqual('CANCELLED', booking.status)

        split_redirect_url = urlsplit(resp.url)
        self.assertEqual(split_redirect_url.path, reverse('booking:events'))
        self.assertIn('name=foo', split_redirect_url.query)
        self.assertIn('tab=1', split_redirect_url.query)
        self.assertIn('page=1', split_redirect_url.query)


class BookingUpdateViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(BookingUpdateViewTests, cls).setUpTestData()
        cls.pole_class_event_type = mommy.make(
            EventType, event_type='CL', subtype='Pole level class'
        )
        cls.free_blocktype = mommy.make_recipe(
            'booking.blocktype', size=1, cost=0,
            event_type=cls.pole_class_event_type, identifier='free class'
        )

    def setUp(self):
        super(BookingUpdateViewTests, self).setUp()
        self.user_no_disclaimer = mommy.make_recipe('booking.user')
        make_data_privacy_agreement(self.user_no_disclaimer)

    def _get_response(self, user, booking):
        url = reverse('booking:update_booking', args=[booking.id])
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

        view = BookingUpdateView.as_view()
        return view(request, pk=booking.id)

    def _post_response(self, user, booking, form_data):
        url = reverse('booking:update_booking', args=[booking.id])
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

        view = BookingUpdateView.as_view()
        return view(request, pk=booking.id)

    def test_can_get_page_for_open_booking(self):
        event = mommy.make_recipe('booking.future_EV', cost=10)
        booking = mommy.make_recipe(
            'booking.booking',
            user=self.user, event=event, paid=False
        )
        resp = self._get_response(self.user, booking)
        self.assertEqual(resp.status_code, 200)

    def test_cannot_get_page_for_paid_booking(self):
        event = mommy.make_recipe('booking.future_EV', cost=10)
        booking = mommy.make_recipe(
            'booking.booking',
            user=self.user, event=event, paid=True
        )
        resp = self._get_response(self.user, booking)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(
            resp.url, reverse('booking:already_paid', args=[booking.pk])
        )

    def test_cannot_post_for_paid_booking(self):
        """
        Make sure we can't post to a paid booking to change it to block paid
        when already direct paid
        """
        event = mommy.make_recipe('booking.future_EV', cost=10)
        booking = mommy.make_recipe(
            'booking.booking',
            user=self.user, event=event, paid=True
        )
        resp = self._post_response(self.user, booking, {'block_book': 'yes'})
        self.assertEqual(resp.status_code, 302)
        self.assertIn(
            resp.url, reverse('booking:already_paid', args=[booking.pk])
        )

    def test_pay_with_block_uses_last_of_free_class_allowed_blocks(self):
        # block of 10 for 'CL' blocktype creates free block
        block = mommy.make_recipe(
            'booking.block_10', user=self.user,
            block_type__event_type=self.pole_class_event_type,
            block_type__assign_free_class_on_completion=True,
            paid=True, start_date=timezone.now()
        )
        event = mommy.make_recipe(
            'booking.future_CL', cost=10, event_type=self.pole_class_event_type
        )

        booking = mommy.make_recipe(
            'booking.booking',
            user=self.user, event=event, paid=False
        )

        mommy.make_recipe(
            'booking.booking', block=block, user=self.user, _quantity=9
        )

        self.assertEqual(Block.objects.count(), 1)
        self._post_response(self.user, booking, {'block_book': 'yes'})

        self.assertEqual(block.bookings.count(), 10)
        self.assertEqual(Block.objects.count(), 2)
        self.assertEqual(Block.objects.latest('id').block_type, self.free_blocktype)

    def test_pay_with_block_uses_last_and_no_free_block_created(self):
        # block of 5 for 'CL' blocktype does not create free block
        block = mommy.make_recipe(
            'booking.block_5', user=self.user,
            block_type__event_type=self.pole_class_event_type,
            paid=True, start_date=timezone.now()
        )
        event = mommy.make_recipe(
            'booking.future_CL', cost=10, event_type=self.pole_class_event_type
        )

        booking = mommy.make_recipe(
            'booking.booking',
            user=self.user, event=event, paid=False
        )

        mommy.make_recipe(
            'booking.booking', block=block, user=self.user, _quantity=4
        )

        self.assertEqual(Block.objects.count(), 1)
        resp = self._post_response(self.user, booking, {'block_book': 'yes'})

        self.assertEqual(block.bookings.count(), 5)
        self.assertEqual(Block.objects.count(), 1)
        self.assertEqual(Block.objects.latest('id'), block)

    def test_pay_with_block_uses_last_of_free_class_allowed_blocks_free_block_already_exists(self):
        block = mommy.make_recipe(
            'booking.block_10', user=self.user,
            block_type__event_type=self.pole_class_event_type,
            block_type__assign_free_class_on_completion=True,
            paid=True, start_date=timezone.now()
        )
        event = mommy.make_recipe(
            'booking.future_EV', cost=10, event_type=self.pole_class_event_type
        )

        booking = mommy.make_recipe(
            'booking.booking',
            user=self.user, event=event, paid=False
        )

        mommy.make_recipe(
            'booking.block', user=self.user, block_type=self.free_blocktype,
            paid=True, parent=block
        )

        mommy.make_recipe(
            'booking.booking', block=block, user=self.user, _quantity=9
        )
        self.assertEqual(Block.objects.count(), 2)
        self._post_response(self.user, booking, {'block_book': 'yes'})

        self.assertEqual(block.bookings.count(), 10)
        self.assertEqual(Block.objects.count(), 2)

    def test_cannot_access_if_no_disclaimer(self):
        event = mommy.make_recipe('booking.future_EV', cost=10)
        booking = mommy.make_recipe(
            'booking.booking', user=self.user_no_disclaimer, event=event, paid=False)
        resp = self._get_response(self.user_no_disclaimer, booking)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:disclaimer_required'))

        form_data = {'block_book': 'yes'}
        resp = self._post_response(self.user_no_disclaimer, booking, form_data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:disclaimer_required'))

    def test_update_event_booking_to_paid(self):
        """
        Test updating a booking to paid with block
        """
        event = mommy.make_recipe('booking.future_EV', cost=10)
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event, paid=False)
        mommy.make_recipe('booking.block',
                                  block_type__event_type=event.event_type,
                                  user=self.user, paid=True)
        form_data = {'block_book': 'yes'}
        self._post_response(self.user, booking, form_data)
        updated_booking = Booking.objects.get(id=booking.id)
        self.assertTrue(updated_booking.paid)

    def test_update_class_booking_to_paid(self):
        """
        Test updating a booking to paid with block
        """
        poleclass = mommy.make_recipe('booking.future_PC', cost=10)
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=poleclass, paid=False)
        mommy.make_recipe('booking.block',
                                  block_type__event_type=poleclass.event_type,
                                  user=self.user, paid=True)
        form_data = {'block_book': 'yes'}
        self._post_response(self.user, booking, form_data)
        updated_booking = Booking.objects.get(id=booking.id)
        self.assertTrue(updated_booking.paid)

    def test_update_roomhire_booking_to_paid(self):
        """
        Test updating a booking to paid with block
        """
        roomhire = mommy.make_recipe('booking.future_RH', cost=10)
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=roomhire, paid=False)
        mommy.make_recipe('booking.block',
                                  block_type__event_type=roomhire.event_type,
                                  user=self.user, paid=True)
        form_data = {'block_book': 'yes'}
        self._post_response(self.user, booking, form_data)
        updated_booking = Booking.objects.get(id=booking.id)
        self.assertTrue(updated_booking.paid)

    def test_requesting_free_class(self):
        """
        Test that requesting a free class emails the studio but does not
        update the booking
        """
        event = mommy.make_recipe('booking.future_EV', cost=10)
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event, paid=False)

        bookings = Booking.objects.filter(user=self.user)
        self.assertEqual(bookings.count(), 1)

        form_data = {'claim_free': True}
        self._post_response(self.user, booking, form_data)
        bookings = Booking.objects.filter(user=self.user)
        self.assertEqual(bookings.count(), 1)

        booking_after_post = bookings[0]
        self.assertEqual(booking.id, booking_after_post.id)
        self.assertEqual(booking.paid, booking_after_post.paid)
        self.assertEqual(booking.payment_confirmed, booking_after_post.payment_confirmed)
        self.assertEqual(booking.block, booking_after_post.block)
        self.assertEqual(booking.free_class, booking_after_post.free_class)

        self.assertEqual(len(mail.outbox), 1)

    def test_cannot_update_for_cancelled_event(self):
        """
        Test trying to update a booking for a cancelled event redirects
        """
        event = mommy.make_recipe('booking.future_EV', cancelled=True)
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event
        )

        resp = self._get_response(self.user, booking)
        # test redirect to permission denied page
        self.assertEqual(
            resp.url,
            reverse(
                'booking:permission_denied',
            )
        )

    @patch('booking.models.timezone')
    def test_update_with_block_if_multiple_blocks_available(self, mock_tz):
        """
        Usually there should be only one block of each type available, but in
        case an admin has added additional blocks, ensure that the one with the
        earlier expiry date is used
        """
        mock_tz.now.return_value = datetime(2015, 1, 10, tzinfo=timezone.utc)
        event_type = mommy.make_recipe('booking.event_type_PC')

        event = mommy.make_recipe('booking.future_PC', event_type=event_type)
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event, paid=False
        )

        blocktype = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type, duration=2
        )
        block1 = mommy.make_recipe(
            'booking.block', block_type=blocktype, user=self.user, paid=True,
            start_date=datetime(2015, 1, 2, tzinfo=timezone.utc)
        )
        block2 = mommy.make_recipe(
            'booking.block', block_type=blocktype, user=self.user, paid=True,
            start_date=datetime(2015, 1, 1, tzinfo=timezone.utc)
        )
        # block1 was created first, but block2 has earlier expiry date so
        # should be used first
        self.assertGreater(block1.expiry_date, block2.expiry_date)

        form_data = {'block_book': True}
        self._post_response(self.user, booking, form_data)

        booking.refresh_from_db()
        self.assertEqual(booking.block, block2)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)

        # change start dates so block1 now has the earlier expiry date
        booking.block = None
        booking.paid = False
        booking.payment_confirmed = False
        booking.save()
        block2.start_date = datetime(2015, 1, 3, tzinfo=timezone.utc)
        block2.save()

        self._post_response(self.user, booking, form_data)
        booking.refresh_from_db()
        self.assertEqual(booking.block, block1)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)

    @patch('booking.models.timezone')
    def test_trying_to_update_block_with_no_available_block(self, mock_tz):
        """
        The template should prevent attempts to block book if no block is
        available; however, if this is submitted, make the booking without
        the block
        """
        mock_tz.now.return_value = datetime(2015, 1, 10, tzinfo=timezone.utc)
        event_type = mommy.make_recipe('booking.event_type_PC')
        event_type1 = mommy.make_recipe('booking.event_type_PC')

        event = mommy.make_recipe('booking.future_PC', event_type=event_type)
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event, paid=False
        )
        # make block with different event type to the event we're trying to
        # book
        blocktype = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type1, duration=2
        )
        block = mommy.make_recipe(
            'booking.block', block_type=blocktype, user=self.user, paid=True,
            start_date=datetime(2015, 1, 2, tzinfo=timezone.utc)
        )

        self.assertTrue(block.active_block())
        self.assertNotEqual(block.block_type.event_type, event.event_type)

        # try to block book
        form_data = {'block_book': True}
        self._post_response(self.user, booking, form_data)

        # booking has not changed, no block assigned
        booking.refresh_from_db()
        self.assertIsNone(booking.block)
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)

    def test_submitting_voucher_code(self):
        voucher = mommy.make(EventVoucher, code='test', discount=10)
        voucher.event_types.add(self.pole_class_event_type)
        booking = mommy.make(
            'booking.booking', event__event_type=self.pole_class_event_type,
            event__cost=10, user=self.user
        )
        resp = self._get_response(self.user, booking)
        self.assertIn('Cost: £ 10.00', resp.rendered_content)
        paypal_form = resp.context_data['paypalform']
        self.assertEqual(paypal_form.initial['amount'], 10.00)
        self.assertEqual(
            paypal_form.initial['custom'],
            'booking {} {}'.format(booking.id, booking.user.email)
        )
        self.assertNotIn('voucher', resp.context_data)

        form_data = {'apply_voucher': 'Apply', 'code': 'test'}
        resp = self._post_response(self.user, booking, form_data)
        self.assertIn('Cost: £ 9.00', resp.rendered_content)
        paypal_form = resp.context_data['paypalform']
        self.assertEqual(paypal_form.initial['amount'], 9.00)
        self.assertEqual(
            paypal_form.initial['custom'], 'booking {} {} {}'.format(
                booking.id, booking.user.email, voucher.code
            )
        )
        self.assertEqual(resp.context_data['voucher'], voucher)

    def test_no_voucher_code(self):
        booking = mommy.make(
            'booking.booking', event__event_type=self.pole_class_event_type,
            event__cost=10, user=self.user
        )
        form_data = {'apply_voucher': 'Apply', 'code': ''}
        resp = self._post_response(self.user, booking, form_data)
        self.assertEqual(resp.context_data['voucher_error'], 'No code provided')

    def test_invalid_voucher_code(self):
        voucher = mommy.make(EventVoucher, code='test', discount=10)
        voucher.event_types.add(self.pole_class_event_type)
        booking = mommy.make(
            'booking.booking', event__event_type=self.pole_class_event_type,
            event__cost=10, user=self.user
        )
        form_data = {'apply_voucher': 'Apply', 'code': 'foo'}
        resp = self._post_response(self.user, booking, form_data)
        self.assertEqual(resp.context_data['voucher_error'], 'Invalid code')

    def test_voucher_code_not_started_yet(self):
        voucher = mommy.make(
            EventVoucher, code='test', discount=10,
            start_date=timezone.now() + timedelta(2)
        )
        voucher.event_types.add(self.pole_class_event_type)
        booking = mommy.make(
            'booking.booking', event__event_type=self.pole_class_event_type,
            event__cost=10, user=self.user
        )
        form_data = {'apply_voucher': 'Apply', 'code': 'test'}
        resp = self._post_response(self.user, booking, form_data)
        self.assertEqual(
            resp.context_data['voucher_error'],
            'Voucher code is not valid until {}'.format(
                voucher.start_date.strftime("%d %b %y")
            )
        )

    def test_expired_voucher(self):
        voucher = mommy.make(
            EventVoucher, code='test', discount=10,
            start_date=timezone.now() - timedelta(4),
            expiry_date=timezone.now() - timedelta(2)
        )
        voucher.event_types.add(self.pole_class_event_type)
        booking = mommy.make(
            'booking.booking', event__event_type=self.pole_class_event_type,
            event__cost=10, user=self.user
        )
        form_data = {'apply_voucher': 'Apply', 'code': 'test'}
        resp = self._post_response(self.user, booking, form_data)
        self.assertEqual(
            resp.context_data['voucher_error'], 'Voucher code has expired'
        )

    def test_voucher_used_max_times(self):
        voucher = mommy.make(
            EventVoucher, code='test', discount=10,
            max_vouchers=2
        )
        voucher.event_types.add(self.pole_class_event_type)
        users = mommy.make_recipe('booking.user', _quantity=2)
        for user in users:
            UsedEventVoucher.objects.create(voucher=voucher, user=user)
        booking = mommy.make(
            'booking.booking', event__event_type=self.pole_class_event_type,
            event__cost=10, user=self.user
        )
        form_data = {'apply_voucher': 'Apply', 'code': 'test'}
        resp = self._post_response(self.user, booking, form_data)
        self.assertEqual(
            resp.context_data['voucher_error'],
            'Voucher has limited number of total uses and has now expired'
        )

    def test_voucher_used_max_times_by_user(self):
        voucher = mommy.make(
            EventVoucher, code='test', discount=10,
            max_vouchers=6, max_per_user=2
        )
        voucher.event_types.add(self.pole_class_event_type)
        users = mommy.make_recipe('booking.user', _quantity=2)
        for user in users:
            UsedEventVoucher.objects.create(voucher=voucher, user=user)
        for i in range(2):
            UsedEventVoucher.objects.create(voucher=voucher, user=self.user)
        booking = mommy.make(
            'booking.booking', event__event_type=self.pole_class_event_type,
            event__cost=10, user=self.user
        )
        form_data = {'apply_voucher': 'Apply', 'code': 'test'}
        resp = self._post_response(self.user, booking, form_data)

        # Used vouchers is < 6, but this user has used their max (2)
        self.assertLess(
            UsedEventVoucher.objects.filter(voucher=voucher).count(),
            voucher.max_vouchers,
        )
        self.assertEqual(
            resp.context_data['voucher_error'],
            'Voucher code has already been used the maximum number of '
            'times (2)'
        )

    def test_cannot_use_voucher_twice(self):
        voucher = mommy.make(EventVoucher, code='test', discount=10)
        voucher.event_types.add(self.pole_class_event_type)
        UsedEventVoucher.objects.create(voucher=voucher, user=self.user)
        booking = mommy.make(
            'booking.booking', event__event_type=self.pole_class_event_type,
            event__cost=10, user=self.user
        )
        form_data = {'apply_voucher': 'Apply', 'code': 'test'}
        resp = self._post_response(self.user, booking, form_data)
        self.assertEqual(
            resp.context_data['voucher_error'],
            'Voucher code has already been used the maximum number of times (1)'
        )

    def test_voucher_for_wrong_event_type(self):
        voucher = mommy.make(EventVoucher, code='test', discount=10)
        voucher.event_types.add(self.pole_class_event_type)
        booking = mommy.make(
            'booking.booking', event__cost=10, user=self.user
        )
        form_data = {'apply_voucher': 'Apply', 'code': 'test'}
        resp = self._post_response(self.user, booking, form_data)
        self.assertEqual(
            resp.context_data['voucher_error'],
            'Voucher code is not valid for this event/class type'
        )

    def test_remove_extra_spaces_from_voucher_code(self):
        """
        Test that extra leading and/or trailing spaces in code are ignored
        :return:
        """
        voucher = mommy.make(EventVoucher, code='test', discount=10)
        voucher.event_types.add(self.pole_class_event_type)
        booking = mommy.make(
            'booking.booking', event__event_type=self.pole_class_event_type,
            event__cost=10, user=self.user
        )

        form_data = {'apply_voucher': 'Apply', 'code': '  test '}
        resp = self._post_response(self.user, booking, form_data)
        self.assertIn('Cost: £ 9.00', resp.rendered_content)
        paypal_form = resp.context_data['paypalform']
        self.assertEqual(paypal_form.initial['amount'], 9.00)
        self.assertEqual(
            paypal_form.initial['custom'], 'booking {} {} {}'.format(
                booking.id, booking.user.email, voucher.code
            )
        )

    def test_update_with_block_from_shopping_basket(self):
        """
        Test updating a booking from basket returns to basket
        """
        block = mommy.make_recipe(
            'booking.block_10', user=self.user,
            block_type__event_type=self.pole_class_event_type,
            paid=True, start_date=timezone.now()
        )
        event = mommy.make_recipe(
            'booking.future_CL', cost=10, event_type=self.pole_class_event_type
        )

        booking = mommy.make_recipe(
            'booking.booking',
            user=self.user, event=event, paid=False
        )

        self.assertEqual(Booking.objects.all().count(), 1)

        self.client.login(username=self.user.username, password='test')

        url = reverse('booking:update_booking', args=[booking.id]) \
              + '?next=shopping_basket'
        resp = self.client.post(
            url, data={'block_book': True, 'shopping_basket': True}
        )

        booking.refresh_from_db()
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)
        self.assertEqual(booking.block, block)

        # redirects back to shopping basket
        self.assertIn(resp.url, reverse('booking:shopping_basket'))

    def test_update_with_block_from_shopping_basket_with_voucher_code(self):
        """
        Test updating a booking from basket with code returns with code in get
        """
        block = mommy.make_recipe(
            'booking.block_10', user=self.user,
            block_type__event_type=self.pole_class_event_type,
            paid=True, start_date=timezone.now()
        )
        event = mommy.make_recipe(
            'booking.future_CL', cost=10, event_type=self.pole_class_event_type
        )

        booking = mommy.make_recipe(
            'booking.booking',
            user=self.user, event=event, paid=False
        )

        self.assertEqual(Booking.objects.all().count(), 1)

        self.client.login(username=self.user.username, password='test')
        url = reverse('booking:update_booking', args=[booking.id])
        resp = self.client.post(
            url,
            data={
                'block_book': True,
                'shopping_basket': True,
                'booking_code': 'foo',
                'block_code': 'bar'
            }
        )

        booking.refresh_from_db()
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)
        self.assertEqual(booking.block, block)

        # redirects back to shopping basket with code
        split = urlsplit(resp.url)
        self.assertEqual(split.path, reverse('booking:shopping_basket'))
        self.assertIn('booking_code=foo', split.query)
        self.assertIn('block_code=bar', split.query)

    def test_cart_items_added_to_session(self):
        mommy.make_recipe(
            'booking.block_10', user=self.user,
            block_type__event_type=self.pole_class_event_type,
            paid=True, start_date=timezone.now()
        )
        event = mommy.make_recipe(
            'booking.future_CL', cost=10, event_type=self.pole_class_event_type
        )

        booking = mommy.make_recipe(
            'booking.booking',
            user=self.user, event=event, paid=False
        )

        self.client.login(username=self.user.username, password='test')

        url = reverse('booking:update_booking', args=[booking.id])

        self.client.get(url)

        # booking added to cart_items on get
        self.assertEqual(
            self.client.session['cart_items'],
            'booking {} {}'.format(str(booking.id), booking.user.email)
        )

        # posting means submitting for block payment, so cart_items deleted
        self.client.post(url, data={'block_book': True})
        self.assertNotIn('cart_items', self.client.session)


class BookingMultiCreateViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.pc = mommy.make_recipe('booking.future_PC')
        cls.ev = mommy.make_recipe('booking.future_EV')
        cls.rh = mommy.make_recipe('booking.future_RH')

    def setUp(self):
        super().setUp()
        self.client.login(username=self.user.username, password='test')

    def test_create_returns_to_correct_events_page(self):
        url = reverse('booking:create_booking', args=[self.pc.slug])
        self.assertFalse(Booking.objects.exists())

        resp = self.client.post(url, data={'event': self.pc.id})
        self.assertTrue(
            Booking.objects.filter(user=self.user, event=self.pc).exists()
        )
        split_redirect_url = urlsplit(resp.url)
        self.assertEqual(split_redirect_url.path, reverse('booking:lessons'))

        url = reverse('booking:create_booking', args=[self.ev.slug])
        resp = self.client.post(url, data={'event': self.ev.id})

        self.assertTrue(
            Booking.objects.filter(user=self.user, event=self.ev).exists()
        )
        split_redirect_url = urlsplit(resp.url)
        self.assertEqual(split_redirect_url.path, reverse('booking:events'))

        url = reverse('booking:create_booking', args=[self.rh.slug])
        resp = self.client.post(url, data={'event': self.rh.id})
        self.assertTrue(
            Booking.objects.filter(user=self.user, event=self.rh).exists()
        )
        split_redirect_url = urlsplit(resp.url)
        self.assertEqual(split_redirect_url.path, reverse('booking:room_hires'))

    def test_create_returns_to_requested_next_page(self):
        url = reverse('booking:create_booking', args=[self.pc.slug])
        self.assertFalse(Booking.objects.exists())

        resp = self.client.post(
            url, data={'event': self.pc.id, 'next': 'bookings'}
        )
        self.assertTrue(
            Booking.objects.filter(user=self.user, event=self.pc).exists()
        )
        split_redirect_url = urlsplit(resp.url)
        self.assertEqual(split_redirect_url.path, reverse('booking:bookings'))

    def test_create_returns_to_events_page_with_filter(self):
        self.pc.name = 'Level 1'
        url = reverse('booking:create_booking', args=[self.pc.slug])
        self.assertFalse(Booking.objects.exists())

        resp = self.client.post(
            url, data={'event': self.pc.id, 'filter': 'Level 1'}
        )
        self.assertTrue(
            Booking.objects.filter(user=self.user, event=self.pc).exists()
        )
        split_redirect_url = urlsplit(resp.url)
        self.assertEqual(split_redirect_url.path, reverse('booking:lessons'))
        self.assertIn('page=', split_redirect_url.query)
        self.assertIn('tab=0', split_redirect_url.query)
        self.assertIn('name=Level+1', split_redirect_url.query)

    def test_create_returns_to_events_page_with_tab(self):
        self.pc.name = 'Level 1'
        url = reverse('booking:create_booking', args=[self.pc.slug])
        self.assertFalse(Booking.objects.exists())

        resp = self.client.post(
            url, data={'event': self.pc.id, 'tab': '0'}
        )
        self.assertTrue(
            Booking.objects.filter(user=self.user, event=self.pc).exists()
        )
        split_redirect_url = urlsplit(resp.url)
        self.assertEqual(split_redirect_url.path, reverse('booking:lessons'))
        self.assertIn('page=', split_redirect_url.query)
        self.assertIn('tab=0', split_redirect_url.query)
        self.assertIn('name=', split_redirect_url.query)

    def test_create_returns_to_events_page_with_filter_and_tab(self):
        self.pc.name = 'Level 1'
        url = reverse('booking:create_booking', args=[self.pc.slug])
        self.assertFalse(Booking.objects.exists())

        resp = self.client.post(
            url, data={'event': self.pc.id, 'filter': 'Level 2', 'tab': '1'}
        )
        self.assertTrue(
            Booking.objects.filter(user=self.user, event=self.pc).exists()
        )
        split_redirect_url = urlsplit(resp.url)
        self.assertEqual(reverse('booking:lessons'), split_redirect_url.path)
        self.assertIn('name=Level+2', split_redirect_url.query)
        self.assertIn('tab=1', split_redirect_url.query)
