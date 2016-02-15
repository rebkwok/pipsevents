from datetime import datetime, timedelta
from mock import Mock, patch
from model_mommy import mommy

from django.conf import settings
from django.core import mail
from django.core.urlresolvers import reverse
from django.test import TestCase, RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone
from django.contrib.auth.models import Permission, User

from activitylog.models import ActivityLog
from accounts.models import PrintDisclaimer

from booking.models import Event, EventType, Booking, Block, WaitingListUser
from booking.views import BookingListView, BookingHistoryListView, \
    BookingCreateView, BookingDeleteView, BookingUpdateView, \
    duplicate_booking, fully_booked, cancellation_period_past, \
    update_booking_cancelled
from booking.tests.helpers import _create_session, TestSetupMixin, \
    format_content

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
        [mommy.make_recipe(
            'booking.booking', user=cls.user,
            event=event) for event in cls.events]
        mommy.make_recipe('booking.past_booking', user=cls.user)

    def _get_response(self, user):
        url = reverse('booking:bookings')
        request = self.factory.get(url)
        request.user = user
        view = BookingListView.as_view()
        return view(request)

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
        resp = self._get_response(self.user)

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
        resp = self._get_response(self.user)

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
        resp = self._get_response(self.user)

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
        resp = self._get_response(self.user)

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
        resp = self._get_response(self.user)

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
        resp = self._get_response(self.user)

        self.assertEquals(len(resp.context_data['bookingformlist']), 1)
        bookingform = resp.context_data['bookingformlist'][0]
        self.assertEqual(
            bookingform['due_date_time'],
            datetime(2015, 1, 18, 6, 0, tzinfo=timezone.utc)
        )

        booking.date_rebooked = datetime(2015, 2, 1, tzinfo=timezone.utc)
        booking.save()
        resp = self._get_response(self.user)

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
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event
        )
        resp = self._get_response(self.user)

        self.assertEquals(len(resp.context_data['bookingformlist']), 1)
        bookingform = resp.context_data['bookingformlist'][0]
        self.assertEqual(
            bookingform['due_date_time'],
            datetime(2015, 2, 13, 18, 0, tzinfo=timezone.utc)
        )


class BookingHistoryListViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(BookingHistoryListViewTests, cls).setUpTestData()
        event = mommy.make_recipe('booking.future_EV')
        cls.booking = mommy.make_recipe(
            'booking.booking', user=cls.user, event=event
        )
        cls.past_booking = mommy.make_recipe(
            'booking.past_booking', user=cls.user
        )

    def _get_response(self, user):
        url = reverse('booking:booking_history')
        request = self.factory.get(url)
        request.user = user
        view = BookingHistoryListView.as_view()
        return view(request)

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
        resp = self._get_response(self.user)

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
        resp = self._get_response(self.user)

        #  listing should still only show this user's past bookings
        self.assertEquals(resp.context_data['bookings'].count(), 1)

    def test_cancelled_booking_shown_in_booking_history(self):
        """
        Test that cancelled bookings are listed in booking history
        """
        ev = mommy.make_recipe('booking.future_EV')
        mommy.make_recipe(
            'booking.booking',
            user=self.user,
            event=ev,
            status='CANCELLED'
        )
        # check there are now 3 bookings
        self.assertEquals(Booking.objects.all().count(), 3)
        resp = self._get_response(self.user)

        # listing should show show all 3 bookings (1 past, 1 cancelled)
        self.assertEquals(resp.context_data['bookings'].count(), 2)


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
        cls.user_no_disclaimer = mommy.make_recipe('booking.user')

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
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

        resp = self._post_response(self.user_no_disclaimer, event)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

        resp = self._get_response(self.user, event)
        self.assertEqual(resp.status_code, 200)

    def test_get_create_booking_page(self):
        """
        Get the booking page with the event context
        """
        event = mommy.make_recipe('booking.future_EV', max_participants=3)
        resp = self._get_response(self.user, event)
        self.assertEqual(resp.context_data['event'], event)

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
        # event has cancellation period
        self.assertIn(
            'Please make your payment as soon as possible. Note that if '
            'payment has not been received by the cancellation period, your '
            'booking will be automatically cancelled.',
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
            'Please make your payment as soon as possible. Note that if '
            'payment has not been received by the payment due date, your '
            'booking will be automatically cancelled.',
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
            'Please make your payment as soon as possible. Note that if '
            'payment has not been received by the payment due date, your '
            'booking will be automatically cancelled.',
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
            'Please make your payment as soon as possible. Note that if '
            'payment has not been received within 8 hours, your '
            'booking will be automatically cancelled.',
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

    @patch('booking.views.booking_views.send_mail')
    def test_create_booking_with_email_error(self, mock_send_emails):
        """
        Test creating a booking sends email to support if there is an email
        error but still creates booking
        """
        mock_send_emails.side_effect = Exception('Error sending mail')

        event = mommy.make_recipe('booking.future_EV', max_participants=3)
        self.assertEqual(Booking.objects.all().count(), 0)
        self._post_response(self.user, event)
        self.assertEqual(Booking.objects.all().count(), 1)
        # email to support only
        self.assertEqual(len(mail.outbox), 1)
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

        event = mommy.make_recipe('booking.future_EV', max_participants=3)
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
        Test trying to get the create page for exisiting redirects
        """
        event = mommy.make_recipe('booking.future_EV', max_participants=3)

        resp = self._post_response(self.user, event)
        booking_id = Booking.objects.all()[0].id
        booking_url = reverse('booking:bookings')
        self.assertEqual(resp.url, booking_url)

        resp1 = self._get_response(self.user, event)
        duplicate_url = reverse('booking:duplicate_booking',
                                kwargs={'event_slug': event.slug}
                                )
        # test redirect to duplicate booking url
        self.assertEqual(resp1.url, duplicate_url)

    def test_cannot_create_duplicate_booking(self):
        """
        Test trying to create a duplicate booking redirects
        """
        event = mommy.make_recipe('booking.future_EV', max_participants=3)

        resp = self._post_response(self.user, event)
        booking_id = Booking.objects.all()[0].id
        booking_url = reverse('booking:bookings')
        self.assertEqual(resp.url, booking_url)

        resp1 = self._post_response(self.user, event)
        duplicate_url = reverse('booking:duplicate_booking',
                                kwargs={'event_slug': event.slug}
                                )
        # test redirect to duplicate booking url
        self.assertEqual(resp1.url, duplicate_url)

    def test_cannot_get_create_booking_page_for_full_event(self):
        """
        Test trying to get create booking page for a full event redirects
        """
        event = mommy.make_recipe('booking.future_EV', max_participants=3)
        users = mommy.make_recipe('booking.user', _quantity=3)
        for user in users:
            mommy.make_recipe('booking.booking', event=event, user=user)
        # check event is full
        self.assertEqual(event.spaces_left(), 0)

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
        # check event is full
        self.assertEqual(event.spaces_left(), 0)

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
        mommy.make(PrintDisclaimer, user=user)
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

    def test_create_booking_uses_last_of_10_class_blocks(self):
        block = mommy.make_recipe(
            'booking.block_10', user=self.user,
            block_type__event_type=self.pole_class_event_type,
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
        self.assertEqual(Block.objects.last().block_type, self.free_blocktype)

    def test_booking_uses_last_of_10_blocks_free_block_already_exists(self):
        block = mommy.make_recipe(
            'booking.block_10', user=self.user,
            block_type__event_type=self.pole_class_event_type,
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
            'booking.block_5', user=self.user,
            block_type__event_type=self.pole_class_event_type,
            paid=True, start_date=timezone.now()
        )
        event = mommy.make_recipe(
            'booking.future_CL', cost=10, event_type=self.pole_class_event_type
        )

        mommy.make_recipe(
            'booking.booking', block=block, user=self.user, _quantity=4
        )

        self.assertEqual(Block.objects.count(), 1)
        self._post_response(self.user, event, {'block_book': 'yes'})

        self.assertEqual(block.bookings.count(), 5)
        self.assertTrue(block.full)
        # 5 class blocks do not qualify for free classes, no free class block
        # created
        self.assertEqual(Block.objects.count(), 1)


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
        self.assertEqual(event.spaces_left(), 0)
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
                                    user=self.user)
        self.assertEqual(Booking.objects.all().count(), 1)
        self._delete_response(self.user, booking)
        # after cancelling, the booking is still there, but status has changed
        self.assertEqual(Booking.objects.all().count(), 1)
        booking = Booking.objects.get(id=booking.id)
        self.assertEqual('CANCELLED', booking.status)

    def test_cancelling_only_this_booking(self):
        """
        Test cancelling a booking when user has more than one
        """
        events = mommy.make_recipe('booking.future_EV', _quantity=3)

        for event in events:
            mommy.make_recipe('booking.booking', user=self.user, event=event)

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
    def test_cannot_cancel_after_cancellation_period(self, mock_tz):
        """
        Test trying to cancel after cancellation period
        """
        mock_tz.now.return_value = datetime(2015, 2, 1, tzinfo=timezone.utc)
        event = mommy.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 2, tzinfo=timezone.utc),
            cancellation_period=48
        )
        booking = mommy.make_recipe(
            'booking.booking', event=event, user=self.user
        )

        url = reverse('booking:delete_booking', args=[booking.id])
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = self.user
        messages = FallbackStorage(request)
        request._messages = messages
        view = BookingDeleteView.as_view()
        resp = view(request, pk=booking.id)

        cannot_cancel_url = reverse('booking:cancellation_period_past',
                                kwargs={'event_slug': event.slug}
        )
        # test redirect to cannot cancel url
        self.assertEqual(302, resp.status_code)
        self.assertEqual(resp.url, cannot_cancel_url)

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
                                    user=self.user)
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

    def test_redirects_if_cancellation_not_allowed(self):
        event = mommy.make_recipe(
            'booking.future_EV', allow_booking_cancellation=False
        )
        booking = mommy.make_recipe('booking.booking', event=event,
                                    user=self.user)
        self.assertEqual(Booking.objects.all().count(), 1)
        resp = self._delete_response(self.user, booking)
        booking.refresh_from_db()
        # still open
        self.assertEqual('OPEN', booking.status)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(resp.url, reverse('booking:permission_denied'))

    def test_cancelling_sends_email_to_user_and_studio_if_applicable(self):
        """ emails are always sent to user; only sent to studio if previously
        direct paid
        """
        event_with_cost = mommy.make_recipe('booking.future_EV', cost=10)
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event_with_cost,
        )
        self._delete_response(self.user, booking)
        # only 1 email sent for cancelled unpaid booking
        self.assertEqual(len(mail.outbox), 1)
        user_mail = mail.outbox[0]
        self.assertEqual(user_mail.to, [self.user.email])

        booking.status = 'OPEN'
        booking.block = mommy.make_recipe('booking.block_5')
        booking.save()
        self._delete_response(self.user, booking)
        # only 1 email sent for cancelled booking paid with block
        self.assertEqual(len(mail.outbox), 2)
        user_mail = mail.outbox[1]
        self.assertEqual(user_mail.to, [self.user.email])

        booking.refresh_from_db()
        booking.status = 'OPEN'
        booking.confirm_space()
        booking.save()
        self._delete_response(self.user, booking)
        # 2 emails sent this time for direct paid booking
        self.assertEqual(len(mail.outbox), 4)
        user_mail = mail.outbox[2]
        studio_mail = mail.outbox[3]
        self.assertEqual(user_mail.to, [self.user.email])
        self.assertEqual(studio_mail.to, [settings.DEFAULT_STUDIO_EMAIL])

    @patch('booking.views.booking_views.send_mail')
    def test_errors_sending_emails(self, mock_send_emails):
        mock_send_emails.side_effect = Exception('Error sending mail')
        event = mommy.make_recipe(
            'booking.future_EV', cost=10, max_participants=3
        )
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event,
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
            'booking.booking', user=self.user, event=event,
        )
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        wluser = mommy.make(
            WaitingListUser, event=event, user__email='wl@test.com'
        )

        self._delete_response(self.user, booking)
        self.assertEqual(len(mail.outbox), 2)
        user_mail = mail.outbox[0]
        waiting_list_mail = mail.outbox[1]
        self.assertEqual(user_mail.to, [self.user.email])
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
            'booking.booking', user=self.user, event=event,
        )
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        mommy.make(
            WaitingListUser, event=event, user__email='wl@test.com'
        )

        self._delete_response(self.user, booking)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, [settings.SUPPORT_EMAIL])
        self.assertEqual(
            mail.outbox[0].subject,
            '{} An error occurred! '
            '(DeleteBookingView - cancelled email)'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
            )
        )
        self.assertEqual(mail.outbox[1].to, [settings.SUPPORT_EMAIL])
        self.assertEqual(
            mail.outbox[1].subject,
            '{} An error occurred! '
            '(DeleteBookingView - waiting list email)'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
            )
        )
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'CANCELLED')

    @patch('booking.views.booking_views.send_mail')
    @patch('booking.views.booking_views.send_waiting_list_email')
    @patch('booking.email_helpers.send_mail')
    def test_errors_sending_all_emails(
            self, mock_send, mock_send_wl_emails, mock_send_emails):
        mock_send.side_effect = Exception('Error sending mail')
        mock_send_emails.side_effect = Exception('Error sending mail')
        mock_send_wl_emails.side_effect = Exception('Error sending mail')
        event = mommy.make_recipe(
            'booking.future_EV', cost=10, max_participants=3
        )
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event,
        )
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        mommy.make(
            WaitingListUser, event=event, user__email='wl@test.com'
        )

        self._delete_response(self.user, booking)
        self.assertEqual(len(mail.outbox), 0)

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'CANCELLED')


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
        cls.user_no_disclaimer = mommy.make_recipe('booking.user')

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

    def test_pay_with_block_uses_last_of_10(self):
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

        mommy.make_recipe(
            'booking.booking', block=block, user=self.user, _quantity=9
        )

        self.assertEqual(Block.objects.count(), 1)
        resp = self._post_response(self.user, booking, {'block_book': 'yes'})

        self.assertEqual(block.bookings.count(), 10)
        self.assertEqual(Block.objects.count(), 2)
        self.assertEqual(Block.objects.last().block_type, self.free_blocktype)

    def test_pay_with_block_uses_last_of_10_free_block_already_exists(self):
        block = mommy.make_recipe(
            'booking.block_10', user=self.user,
            block_type__event_type=self.pole_class_event_type,
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
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

        form_data = {'block_book': 'yes'}
        resp = self._post_response(self.user_no_disclaimer, booking, form_data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

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
