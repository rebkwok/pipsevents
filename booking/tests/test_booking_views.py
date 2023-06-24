# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from unittest.mock import patch
from model_bakery import baker

from urllib.parse import urlsplit

from django.conf import settings
from django.core import mail
from django.urls import reverse
from django.test import TestCase
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone

from booking.models import BlockType, Event, EventType, Booking, \
    Block, EventVoucher,UsedEventVoucher,  WaitingListUser
from booking.views import BookingUpdateView, \
    duplicate_booking, fully_booked, cancellation_period_past, \
    update_booking_cancelled
from common.tests.helpers import _create_session, \
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
            baker.make_recipe('booking.future_EV',  name="First Event"),
            baker.make_recipe('booking.future_PC',  name="Scnd Event"),
            baker.make_recipe('booking.future_RH',  name="Third Event")
        ]
        cls.url = reverse('booking:bookings')

    def setUp(self):
        super(BookingListViewTests, self).setUp()
        [baker.make_recipe(
            'booking.booking', user=self.user,
            event=event) for event in self.events]
        baker.make_recipe('booking.past_booking', user=self.user)

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

        self.assertEqual(Booking.objects.all().count(), 4)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context_data['bookings'].count(), 3)

    def test_booking_list_by_user(self):
        """
        Test that only bookings for this user are listed
        """
        another_user = baker.make_recipe('booking.user')
        baker.make_recipe(
            'booking.booking', user=another_user, event=self.events[0]
        )
        # check there are now 5 bookings
        self.assertEqual(Booking.objects.all().count(), 5)
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)

        # event listing should still only show this user's future bookings
        self.assertEqual(resp.context_data['bookings'].count(), 3)

    def test_cancelled_booking_shown_in_booking_list(self):
        """
        Test that all future bookings for this user are listed
        """
        ev = baker.make_recipe('booking.future_EV', name="future event")
        baker.make_recipe(
            'booking.booking', user=self.user, event=ev,
            status='CANCELLED'
        )
        # check there are now 5 bookings (3 future, 1 past, 1 cancelled)
        self.assertEqual(Booking.objects.all().count(), 5)
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)

        # booking listing should show this user's future bookings,
        # including the cancelled one
        self.assertEqual(resp.context_data['bookings'].count(), 4)

    def test_cancelled_events_shown_in_booking_list(self):
        """
        Test that all future bookings for cancelled events for this user are
        listed
        """
        Booking.objects.all().delete()
        ev = baker.make_recipe(
            'booking.future_EV', name="future event", cancelled=True
        )
        baker.make_recipe(
            'booking.booking', user=self.user, event=ev,
            status='CANCELLED'
        )
        # check there are now 5 bookings (3 future, 1 past, 1 cancelled)
        self.assertEqual(Booking.objects.all().count(), 1)
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)

        # booking listing should show this user's future bookings,
        # including the cancelled one
        self.assertEqual(resp.context_data['bookings'].count(), 1)
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

        mock_tz.now.return_value = datetime(2015, 2, 1, tzinfo=dt_timezone.utc)

        Event.objects.all().delete()
        Booking.objects.all().delete()
        event = baker.make_recipe(
            'booking.future_PC', advance_payment_required=True, cost=10,
            date=datetime(2015, 2, 14, 18, 0, tzinfo=dt_timezone.utc),
            payment_due_date=datetime(2015, 2, 12, 16, 0, tzinfo=dt_timezone.utc),
        )
        baker.make_recipe('booking.booking', user=self.user, event=event)

        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)

        self.assertEqual(len(resp.context_data['bookingformlist']), 1)
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

        mock_tz.now.return_value = datetime(2015, 2, 1, tzinfo=dt_timezone.utc)

        Event.objects.all().delete()
        Booking.objects.all().delete()
        event = baker.make_recipe(
            'booking.future_PC', advance_payment_required=True,
            date=datetime(2015, 2, 14, 18, 0, tzinfo=dt_timezone.utc),
            payment_time_allowed=6, cost=10
        )
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event
        )
        booking.date_booked = datetime(2015, 1, 18, tzinfo=dt_timezone.utc)
        booking.save()
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)

        self.assertEqual(len(resp.context_data['bookingformlist']), 1)
        bookingform = resp.context_data['bookingformlist'][0]
        self.assertEqual(
            bookingform['due_date_time'],
            datetime(2015, 1, 18, 6, 0, tzinfo=dt_timezone.utc)
        )

        booking.date_rebooked = datetime(2015, 2, 1, tzinfo=dt_timezone.utc)
        booking.save()
        resp = self.client.get(self.url)

        self.assertEqual(len(resp.context_data['bookingformlist']), 1)
        bookingform = resp.context_data['bookingformlist'][0]
        self.assertEqual(
            bookingform['due_date_time'],
            datetime(2015, 2, 1, 6, 0, tzinfo=dt_timezone.utc)
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

        mock_tz.now.return_value = datetime(2015, 2, 1, tzinfo=dt_timezone.utc)

        Event.objects.all().delete()
        Booking.objects.all().delete()
        event = baker.make_recipe(
            'booking.future_PC', advance_payment_required=True,
            date=datetime(2015, 2, 14, 18, 0, tzinfo=dt_timezone.utc),
            cancellation_period=24, cost=10
        )
        baker.make_recipe(
            'booking.booking', user=self.user, event=event
        )
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)

        self.assertEqual(len(resp.context_data['bookingformlist']), 1)
        bookingform = resp.context_data['bookingformlist'][0]
        self.assertEqual(
            bookingform['due_date_time'],
            datetime(2015, 2, 13, 18, 0, tzinfo=dt_timezone.utc)
        )

    def test_paid_status_display(self):
        Event.objects.all().delete()
        Booking.objects.all().delete()
        event_with_cost = baker.make_recipe('booking.future_PC', cost=10)
        event_without_cost = baker.make_recipe('booking.future_PC', cost=0)

        booking = baker.make_recipe(
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

        block = baker.make_recipe(
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
        baker.make_recipe(
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
        ev = baker.make_recipe('booking.future_EV', name="future event")
        baker.make_recipe(
            'booking.booking', user=self.user, event=ev,
            status='CANCELLED', auto_cancelled=True
        )
        # check there are now 5 bookings (3 future, 1 past, 1 cancelled)
        self.assertEqual(Booking.objects.all().count(), 5)
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)

        # booking listing should show this user's future bookings,
        # including the cancelled one
        self.assertEqual(resp.context_data['bookings'].count(), 4)
        self.assertIn(
            'rebook_button_auto_cancelled_disabled', resp.rendered_content
        )


class BookingHistoryListViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(BookingHistoryListViewTests, cls).setUpTestData()
        cls.event = baker.make_recipe('booking.future_EV')
        cls.url = reverse('booking:booking_history')

    def setUp(self):
        super(BookingHistoryListViewTests, self).setUp()
        self.booking = baker.make_recipe(
            'booking.booking', user=self.user, event=self.event
        )
        self.past_booking = baker.make_recipe(
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

        self.assertEqual(Booking.objects.all().count(), 2)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context_data['bookings'].count(), 1)

    def test_booking_history_list_by_user(self):
        """
        Test that only past booking for this user are listed
        """
        another_user = baker.make_recipe('booking.user')
        baker.make_recipe(
            'booking.booking', user=another_user, event=self.past_booking.event
        )
        # check there are now 3 bookings
        self.assertEqual(Booking.objects.all().count(), 3)
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)

        #  listing should still only show this user's past bookings
        self.assertEqual(resp.context_data['bookings'].count(), 1)


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
        event = baker.make_recipe('booking.future_EV')
        resp = self._get_duplicate_booking(self.user, event)
        self.assertIn(event.name, str(resp.content))

        poleclass = baker.make_recipe('booking.future_PC')
        resp = self._get_duplicate_booking(self.user, poleclass)
        self.assertIn(poleclass.name, str(resp.content))

        roomhire = baker.make_recipe('booking.future_RH')
        resp = self._get_duplicate_booking(self.user, roomhire)
        self.assertIn(roomhire.name, str(resp.content))

    def test_fully_booked(self):
        """
        Get the fully booked page with the event context
        """
        event = baker.make_recipe('booking.future_EV')
        resp = self._get_fully_booked(self.user, event)
        self.assertIn(event.name, str(resp.content))

        poleclass = baker.make_recipe('booking.future_PC')
        resp = self._get_fully_booked(self.user, poleclass)
        self.assertIn(poleclass.name, str(resp.content))

        roomhire = baker.make_recipe('booking.future_RH')
        resp = self._get_fully_booked(self.user, roomhire)
        self.assertIn(roomhire.name, str(resp.content))

    def test_update_booking_cancelled(self):
        """
        Get the redirected page when trying to update a cancelled booking
        with the event context
        """
        event = baker.make_recipe('booking.future_EV')
        booking = baker.make_recipe(
            'booking.booking', status='CANCELLED', event=event
        )
        resp = self._get_update_booking_cancelled(self.user, booking)
        self.assertIn(event.name, str(resp.content))

        poleclass = baker.make_recipe('booking.future_PC')
        booking = baker.make_recipe(
            'booking.booking', status='CANCELLED', event=poleclass
        )
        resp = self._get_update_booking_cancelled(self.user, booking)
        self.assertIn(poleclass.name, str(resp.content))

        roomhire = baker.make_recipe('booking.future_RH')
        booking = baker.make_recipe(
            'booking.booking', status='CANCELLED', event=roomhire
        )
        resp = self._get_update_booking_cancelled(self.user, booking)
        self.assertIn(roomhire.name, str(resp.content))

    def test_update_booking_cancelled_for_full_event(self):
        """
        Get the redirected page when trying to update a cancelled booking
        for an event that's now full
        """
        event = baker.make_recipe('booking.future_EV', max_participants=3)
        booking = baker.make_recipe(
            'booking.booking', status='CANCELLED', event=event
        )
        baker.make_recipe(
            'booking.booking', status='OPEN', event=event, _quantity=3
        )
        # check event is full; we need to get the event again as spaces_left is
        # cached property
        event = Event.objects.get(id=event.id)
        self.assertEqual(event.spaces_left, 0)
        resp = self._get_update_booking_cancelled(self.user, booking)
        self.assertIn(event.name, str(resp.content))
        self.assertIn("This workshop/event is now full", str(resp.content))

    def test_already_cancelled(self):
        """
        Get the redirected page when trying to cancel a cancelled booking
        for an event that's now full
        """
        booking = baker.make_recipe('booking.booking', status='CANCELLED')
        resp = self.client.get(
            reverse('booking:already_cancelled', args=[booking.id])
        )
        self.assertIn(booking.event.name, str(resp.content))

    def test_cannot_cancel_after_cancellation_period(self):
        """
        Get the cannot cancel page with the event context
        """
        event = baker.make_recipe('booking.future_EV')
        url = reverse(
            'booking:cancellation_period_past',
            kwargs={'event_slug': event.slug}
        )
        self.client.login(username=self.user, password="test")
        resp = self.client.get(url)
        assert resp.context["event"] == event
        assert "Bookings cannot be cancelled for this event because the cancellation period has now passed" in str(resp.content)

    def test_has_active_block(self):
        response = self.client.get(reverse('booking:has_active_block'))
        self.assertEqual(response.status_code, 200)

    def test_already_paid(self):
        booking = baker.make_recipe('booking.booking', paid=True)
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

    def test_get_delete_booking_page(self):
        """
        Get the delete booking page with the event context
        """
        event = baker.make_recipe('booking.future_EV')
        booking = baker.make_recipe('booking.booking', event=event, user=self.user)
        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password="test")
        resp = self.client.get(url)
        self.assertEqual(resp.context_data['event'], event)

    def test_cancel_booking(self):
        """
        Test deleting a booking
        """
        event = baker.make_recipe('booking.future_EV')
        booking = baker.make_recipe('booking.booking', event=event,
                                    user=self.user, paid=True)
        self.assertEqual(Booking.objects.all().count(), 1)

        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password="test")
        self.client.post(url)
        # after cancelling, the booking is still there, but status has changed
        self.assertEqual(Booking.objects.all().count(), 1)
        booking = Booking.objects.get(id=booking.id)
        self.assertEqual('CANCELLED', booking.status)

    def test_cancel_booking_from_shopping_basket_ajax(self):
        """
        Test deleting a booking from shopping basket (ajax)
        """
        event = baker.make_recipe('booking.future_PC')
        booking = baker.make_recipe('booking.booking', event=event,
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
        event = baker.make_recipe('booking.future_PC')
        booking = baker.make_recipe('booking.booking', event=event, user=self.user, paid=False)
        self.assertEqual(Booking.objects.all().count(), 1)

        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

        # booking not deleted
        booking.refresh_from_db()
        assert booking.status == "CANCELLED"
        # no emails sent
        self.assertEqual(len(mail.outbox), 1)

    def test_cancel_unpaid_rebooking(self):
        """
        Test deleting a rebooking; unpaid, set to cancelled
        """
        event = baker.make_recipe('booking.future_PC')
        booking = baker.make_recipe(
            'booking.booking', event=event, user=self.user, paid=False,
            date_rebooked=datetime(2018, 1, 1, tzinfo=dt_timezone.utc)
        )
        self.assertEqual(Booking.objects.all().count(), 1)

        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)
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
        event = baker.make_recipe('booking.future_PC')
        booking = baker.make_recipe(
            'booking.booking', event=event, user=self.user, paid=False
        )
        ppt = create_booking_paypal_transaction(self.user, booking)
        ppt.transaction_id = 'test'
        ppt.save()

        self.assertEqual(Booking.objects.all().count(), 1)

        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

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
        events = baker.make_recipe('booking.future_EV', _quantity=3)

        for event in events:
            baker.make_recipe('booking.booking', user=self.user, event=event, paid=True)

        self.assertEqual(Booking.objects.all().count(), 3)
        booking = Booking.objects.all()[0]

        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

        self.assertEqual(Booking.objects.all().count(), 3)
        cancelled_bookings = Booking.objects.filter(status='CANCELLED')
        self.assertEqual([cancelled.id for cancelled in cancelled_bookings],
                         [booking.id])

    def test_cancelling_booking_sets_payment_confirmed_to_False(self):
        event_with_cost = baker.make_recipe('booking.future_EV', cost=10)
        booking = baker.make_recipe('booking.booking', user=self.user,
                                    event=event_with_cost)
        booking.confirm_space()
        self.assertTrue(booking.payment_confirmed)

        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

        booking = Booking.objects.get(user=self.user,
                                      event=event_with_cost)
        self.assertEqual('CANCELLED', booking.status)
        self.assertFalse(booking.payment_confirmed)

    def test_cancelling_booking_with_block(self):
        """
        Test that cancelling a booking bought with a block removes the
        booking and updates the block
        """
        event_type = baker.make_recipe('booking.event_type_PC')

        event = baker.make_recipe('booking.future_PC', event_type=event_type)
        blocktype = baker.make_recipe(
            'booking.blocktype5', event_type=event_type
        )
        block = baker.make_recipe(
            'booking.block', block_type=blocktype, user=self.user
        )
        booking = baker.make_recipe(
            'booking.booking', event=event, user=self.user, block=block
        )
        booking.confirm_space()
        block = Block.objects.get(user=self.user)
        self.assertEqual(block.bookings_made(), 1)

        # cancel booking
        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

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
        mock_tz.now.return_value = datetime(2015, 2, 1, tzinfo=dt_timezone.utc)
        event = baker.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 2, tzinfo=dt_timezone.utc),
            cancellation_period=48
        )
        booking = baker.make_recipe(
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
        mock_tz.now.return_value = datetime(2015, 2, 1, tzinfo=dt_timezone.utc)
        event = baker.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 2, tzinfo=dt_timezone.utc),
            cancellation_period=48
        )
        booking = baker.make_recipe(
            'booking.booking', event=event, user=self.user, paid=True
        )

        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(url, follow=True)
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
        mock_tz.now.return_value = datetime(2015, 2, 1, 10, 0, tzinfo=dt_timezone.utc)
        event = baker.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 2, tzinfo=dt_timezone.utc),
            cancellation_period=48
        )
        block = baker.make_recipe('booking.block_5', user=self.user, paid=True)
        # booking made 10 mins ago
        booking = baker.make_recipe(
            'booking.booking', event=event, user=self.user, block=block, paid=True,
            date_booked=datetime(2015, 2, 1, 9, 50, tzinfo=dt_timezone.utc)
        )

        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(url, follow=True)
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
        booking = baker.make_recipe(
            'booking.booking', event=event, user=self.user, block=block, paid=True,
            date_booked=datetime(2015, 2, 1, 9, 40, tzinfo=dt_timezone.utc)
        )
        url = reverse('booking:delete_booking', args=[booking.id])
        resp = self.client.post(url, follow=True)

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
        mock_tz.now.return_value = datetime(2015, 2, 1, 10, 0, tzinfo=dt_timezone.utc)
        event = baker.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 2, tzinfo=dt_timezone.utc),
            cancellation_period=48
        )
        block = baker.make_recipe('booking.block_5', user=self.user, paid=True)
        # booking made 60 mins ago, rebooked 10 mins ago
        booking = baker.make_recipe(
            'booking.booking', event=event, user=self.user, block=block, paid=True,
            date_booked=datetime(2015, 2, 1, 9, 0, tzinfo=dt_timezone.utc),
            date_rebooked=datetime(2015, 2, 1, 9, 50, tzinfo=dt_timezone.utc)
        )

        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(url, follow=True)
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
        event_with_cost = baker.make_recipe('booking.future_EV', cost=10)
        booking = baker.make_recipe('booking.booking', user=self.user,
                                    event=event_with_cost)
        booking.free_class = True
        booking.save()
        booking.confirm_space()
        self.assertTrue(booking.payment_confirmed)
        self.assertTrue(booking.free_class)

        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

        booking = Booking.objects.get(user=self.user,
                                      event=event_with_cost)
        self.assertEqual('CANCELLED', booking.status)
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)
        self.assertFalse(booking.free_class)

    def test_cannot_cancel_twice(self):
        event = baker.make_recipe('booking.future_EV')
        booking = baker.make_recipe('booking.booking', event=event,
                                    user=self.user, paid=True)
        self.assertEqual(Booking.objects.all().count(), 1)

        self.client.login(username=self.user.username, password='test')
        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.post(url)

        booking.refresh_from_db()
        self.assertEqual('CANCELLED', booking.status)

        # try deleting again, should redirect
        resp = self.client.post(url)

        self.assertEqual(resp.status_code, 302)
        self.assertIn(
            resp.url, reverse('booking:already_cancelled', args=[booking.id])
        )

    def test_event_with_cancellation_not_allowed(self):
        """
        Can still be cancelled but not refundable
        Paid booking stays OPEN but is set to no_show
        Unpaid booking is set to cancelled
        """
        event = baker.make_recipe(
            'booking.future_PC', allow_booking_cancellation=False
        )
        paid_booking = baker.make_recipe('booking.booking', event=event,
                                    user=self.user, paid=True)

        url = reverse('booking:delete_booking', args=[paid_booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)
        paid_booking.refresh_from_db()
        # still open, but no_show
        self.assertEqual('OPEN', paid_booking.status)
        self.assertTrue(paid_booking.no_show)

        event1 = baker.make_recipe(
            'booking.future_PC', allow_booking_cancellation=False
        )
        unpaid_booking = baker.make_recipe(
            'booking.booking', event=event1, user=self.user
        )

        url = reverse('booking:delete_booking', args=[unpaid_booking.id])
        self.client.post(url)

        unpaid_booking.refresh_from_db()
        assert unpaid_booking.status == "CANCELLED"
        assert unpaid_booking.no_show is False

        # no transfer blocks made
        self.assertFalse(Block.objects.filter(user=self.user).exists())

    def test_cancelling_sends_email_to_user_and_studio_if_applicable(self):
        """ emails are always sent to user; only sent to studio if previously
        direct paid and not eligible for transfer
        """
        event_with_cost = baker.make_recipe('booking.future_EV', cost=10)
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event_with_cost, paid=True
        )
        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

        # 2 emails sent for cancelled paid booking
        self.assertEqual(len(mail.outbox), 2)
        user_mail = mail.outbox[0]
        self.assertEqual(user_mail.to, [self.user.email])

        booking.status = 'OPEN'
        # make a block that isn't expired
        booking.block = baker.make_recipe(
            'booking.block_5', start_date=timezone.now()
        )
        booking.save()

        self.client.post(url)
        # only 1 email sent for cancelled booking paid with block
        self.assertEqual(len(mail.outbox), 3)
        user_mail = mail.outbox[2]
        self.assertEqual(user_mail.to, [self.user.email])

        booking.refresh_from_db()
        booking.status = 'OPEN'
        booking.confirm_space()
        booking.save()

        self.client.post(url)
        # 2 emails sent this time for direct paid booking
        self.assertEqual(len(mail.outbox), 5)
        user_mail = mail.outbox[3]
        studio_mail = mail.outbox[4]
        self.assertEqual(user_mail.to, [self.user.email])
        self.assertEqual(studio_mail.to, [settings.DEFAULT_STUDIO_EMAIL])

    @patch('booking.views.booking_views.send_mail')
    def test_errors_sending_emails(self, mock_send_emails):
        mock_send_emails.side_effect = Exception('Error sending mail')
        event = baker.make_recipe(
            'booking.future_PC', cost=10, max_participants=3
        )
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True
        )

        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

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
        event = baker.make_recipe(
            'booking.future_EV', cost=10, max_participants=3
        )
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event
        )
        baker.make_recipe('booking.booking', event=event, _quantity=2)
        wluser = baker.make(
            WaitingListUser, event=event, user__email='wl@test.com'
        )

        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)
        # unpaid booking deleted, cancel and  waiting list emails sent
        self.assertEqual(len(mail.outbox), 2)
        waiting_list_mail = mail.outbox[1]
        self.assertEqual(waiting_list_mail.bcc, [wluser.user.email])

    @patch('booking.views.booking_views.send_mail')
    @patch('booking.views.booking_views.send_waiting_list_email')
    def test_errors_sending_waiting_list_emails(
            self, mock_send_wl_emails, mock_send_emails):
        mock_send_emails.side_effect = Exception('Error sending mail')
        mock_send_wl_emails.side_effect = Exception('Error sending mail')
        event = baker.make_recipe(
            'booking.future_EV', cost=10, max_participants=3
        )
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event
        )
        baker.make_recipe('booking.booking', event=event, _quantity=2)
        baker.make(
            WaitingListUser, event=event, user__email='wl@test.com'
        )

        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

        # Error emails for both cancellation and waiting list
        self.assertEqual(len(mail.outbox), 2)

        for email in mail.outbox:
            self.assertEqual(email.to, [settings.SUPPORT_EMAIL])
            self.assertTrue(
                email.subject.startswith(
                    f'{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} An error occurred! (DeleteBookingView - '
                )
            )

    @patch('booking.views.booking_views.send_mail')
    @patch('booking.views.booking_views.send_waiting_list_email')
    @patch('booking.email_helpers.send_mail')
    def test_errors_sending_all_emails(self, mock_send, mock_send_wl_emails, mock_send_emails):
        mock_send.side_effect = Exception('Error sending mail')
        mock_send_emails.side_effect = Exception('Error sending mail')
        mock_send_wl_emails.side_effect = Exception('Error sending mail')
        event = baker.make_recipe(
            'booking.future_PC', cost=10, max_participants=3
        )
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True
        )
        baker.make_recipe('booking.booking', event=event, _quantity=2)
        baker.make(
            WaitingListUser, event=event, user__email='wl@test.com'
        )

        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)
        self.assertEqual(len(mail.outbox), 0)

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'CANCELLED')

    def test_cancel_direct_paid_CL_creates_transfer_blocktype(self):
        event = baker.make_recipe(
            'booking.future_PC', cost=10, max_participants=3
        )
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True,
            payment_confirmed=True
        )

        self.assertFalse(BlockType.objects.exists())
        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

        assert BlockType.objects.count() == 1
        block_type = BlockType.objects.first()
        assert block_type.identifier == 'transferred'
        assert block_type.active is False
        assert block_type.size == 1
        assert block_type.event_type == event.event_type
        assert block_type.duration is None
        assert block_type.duration_weeks == 2
        assert BlockType.get_transfer_block_type(event.event_type) == block_type

    def test_cancel_free_non_block_CL_creates_transfer_blocktype(self):
        event = baker.make_recipe(
            'booking.future_PC', cost=10, max_participants=3
        )
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event, free_class=True,
            paid=True, payment_confirmed=True
        )

        self.assertFalse(BlockType.objects.exists())
        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

        assert BlockType.objects.count() == 1
        block_type = BlockType.objects.first()
        assert block_type.identifier == 'transferred'
        assert block_type.active is False
        assert block_type.size == 1
        assert block_type.event_type == event.event_type
        assert block_type.duration is None
        assert block_type.duration_weeks == 2
        assert BlockType.get_transfer_block_type(event.event_type) == block_type

    def test_cancel_direct_paid_RH_creates_transfer_blocktype(self):
        event = baker.make_recipe(
            'booking.future_RH', cost=10, max_participants=3
        )
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True,
            payment_confirmed=True
        )

        self.assertFalse(BlockType.objects.exists())
        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

        assert BlockType.objects.count() == 1
        block_type = BlockType.objects.first()
        assert block_type.identifier == 'transferred'
        assert block_type.active is False
        assert block_type.size == 1
        assert block_type.event_type == event.event_type
        assert block_type.duration is None
        assert block_type.duration_weeks == 2
        assert BlockType.get_transfer_block_type(event.event_type) == block_type

    def test_free_non_block_RH_creates_transfer_blocktype(self):
        event = baker.make_recipe(
            'booking.future_RH', cost=10, max_participants=3
        )
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True,
            payment_confirmed=True, free_class=True
        )

        self.assertFalse(BlockType.objects.exists())
        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

        assert BlockType.objects.count() == 1
        block_type = BlockType.objects.first()
        assert block_type.identifier == 'transferred'
        assert block_type.active is False
        assert block_type.size == 1
        assert block_type.event_type == event.event_type
        assert block_type.duration is None
        assert block_type.duration_weeks == 2
        assert BlockType.get_transfer_block_type(event.event_type) == block_type

    def test_cancel_direct_paid_EV_does_not_creates_transfer_blocktype(self):
        event = baker.make_recipe(
            'booking.future_EV', cost=10, max_participants=3
        )
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True,
            payment_confirmed=True
        )

        self.assertFalse(BlockType.objects.exists())
        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

        self.assertFalse(BlockType.objects.exists())

    def test_cancel_free_non_block_EV_does_not_creates_transfer_blocktype(self):
        event = baker.make_recipe(
            'booking.future_EV', cost=10, max_participants=3
        )
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True,
            payment_confirmed=True, free_class=True
        )

        self.assertFalse(BlockType.objects.exists())
        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

        self.assertFalse(BlockType.objects.exists())

    def test_cancel_direct_paid_CL_creates_transfer_block(self):
        """
        transfer block created with transferred booking id set, booking set
        to unpaid, email not sent to studio
        """
        event = baker.make_recipe(
            'booking.future_PC', cost=10, max_participants=3
        )
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True,
            payment_confirmed=True
        )

        self.assertFalse(Block.objects.exists())
        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

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
        event = baker.make_recipe(
            'booking.future_PC', cost=10, max_participants=3
        )
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True,
            payment_confirmed=True, free_class=True
        )

        self.assertFalse(Block.objects.exists())
        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

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
        event = baker.make_recipe(
            'booking.future_RH', cost=10, max_participants=3
        )
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True,
            payment_confirmed=True
        )

        self.assertFalse(Block.objects.exists())
        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

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
        event = baker.make_recipe(
            'booking.future_RH', cost=10, max_participants=3
        )
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True,
            payment_confirmed=True, free_class=True
        )

        self.assertFalse(Block.objects.exists())
        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

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
        event = baker.make_recipe(
            'booking.future_EV', cost=10, max_participants=3
        )
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True,
            payment_confirmed=True
        )

        self.assertFalse(Block.objects.exists())
        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

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
        event = baker.make_recipe(
            'booking.future_EV', cost=10, max_participants=3
        )
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True,
            payment_confirmed=True, free_class=True
        )

        self.assertFalse(Block.objects.exists())
        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

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

    def test_cancel_unpaid_does_not_create_transfer_block(self):
        """
        unpaid, block paid, free (with block), deposit only paid do not
        create transfers
        """
        self.assertFalse(Block.objects.exists())
        event = baker.make_recipe('booking.future_PC', cost=10)

        # unpaid
        unpaid_booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event, paid=False,
        )
        url = reverse('booking:delete_booking', args=[unpaid_booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

        self.assertTrue(Booking.objects.filter(id=unpaid_booking.id).exists())
        self.assertFalse(
            Block.objects.filter(block_type__identifier='transferred').exists()
        )

    def test_cancel_block_paid_does_not_create_transfer_block(self):
        """
        unpaid, block paid, free (with block), deposit only paid do not
        create transfers
        """
        self.assertFalse(Block.objects.exists())
        event = baker.make_recipe('booking.future_PC', cost=10)

        # block paidtest_cancel_unpaid_booking
        block = baker.make_recipe(
            'booking.block', block_type__event_type=event.event_type,
            user=self.user
        )
        block_booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event, block=block,
        )
        self.assertTrue(block_booking.paid)
        self.assertTrue(block_booking.payment_confirmed)

        url = reverse('booking:delete_booking', args=[block_booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

        block_booking.refresh_from_db()
        self.assertFalse(
            Block.objects.filter(block_type__identifier='transferred').exists()
        )

    def test_cancel_free_with_block_does_not_create_transfer_block(self):
        """
        unpaid, block paid, free (with block), deposit only paid do not
        create transfers
        """
        self.assertFalse(Block.objects.exists())
        event = baker.make_recipe('booking.future_PC', cost=10)

        # free (with block)
        user3 = baker.make_recipe('booking.user')
        make_data_privacy_agreement(user3)
        baker.make_recipe('booking.online_disclaimer', user=user3)
        free_block = baker.make_recipe(
            'booking.block', block_type__event_type=event.event_type,
            block_type__identifier='free class', user=self.user
        )
        free_block_booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event, free_class=True,
            block=free_block
        )
        self.assertTrue(free_block_booking.paid)
        self.assertTrue(free_block_booking.payment_confirmed)

        url = reverse('booking:delete_booking', args=[free_block_booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

        free_block_booking.refresh_from_db()
        self.assertFalse(
            Block.objects.filter(block_type__identifier='transferred').exists()
        )

    def test_cancel_deposit_only_paid_does_not_create_transfer_block(self):
        """
        unpaid, block paid, free (with block), deposit only paid do not
        create transfers
        """
        self.assertFalse(Block.objects.exists())
        event = baker.make_recipe('booking.future_PC', cost=10)

        # deposit only paid
        dep_paid_booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event, paid=False,
            payment_confirmed=False, deposit_paid=True
        )

        url = reverse('booking:delete_booking', args=[dep_paid_booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

        dep_paid_booking.refresh_from_db()
        self.assertFalse(
            Block.objects.filter(block_type__identifier='transferred').exists()
        )

    def test_cancel_free_without_block_does_create_transfer_block(self):
        """
        unpaid, block paid, free (with block), deposit only paid do not
        create transfers
        """
        self.assertFalse(Block.objects.exists())
        event = baker.make_recipe('booking.future_PC', cost=10)

        # free (without block) DOES create transfer
        free_booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event, free_class=True,
        )
        free_booking.free_class = True
        self.assertTrue(free_booking.paid)
        self.assertTrue(free_booking.payment_confirmed)

        url = reverse('booking:delete_booking', args=[free_booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

        free_booking.refresh_from_db()
        self.assertTrue(
            Block.objects.filter(block_type__identifier='transferred').exists()
        )
        block = Block.objects.get(block_type__identifier='transferred')
        self.assertEqual(block.user, self.user)
        self.assertEqual(block.transferred_booking_id, free_booking.id)

    def test_cancel_direct_paid_does_create_transfer_block(self):
        """
        unpaid, block paid, free (with block), deposit only paid do not
        create transfers
        """
        self.assertFalse(Block.objects.exists())
        event = baker.make_recipe('booking.future_PC', cost=10)

        direct_paid_booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event, paid=True,
            payment_confirmed=True
        )

        url = reverse('booking:delete_booking', args=[direct_paid_booking.id])
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)
        direct_paid_booking.refresh_from_db()

        self.assertEqual(
            Block.objects.filter(block_type__identifier='transferred').count(),
            1
        )
        block = Block.objects.latest('id')
        self.assertEqual(block.user, self.user)
        self.assertEqual(block.transferred_booking_id, direct_paid_booking.id)

    def test_cancel_expired_block_paid_creates_transfer_block(self):
        """
        block paid, but block now expired, does create transfers for PC and RH
        """
        self.assertFalse(Block.objects.exists())
        self.client.login(username=self.user.username, password='test')

        pc = baker.make_recipe('booking.future_PC', cost=10)
        ev = baker.make_recipe('booking.future_EV', cost=10)
        rh = baker.make_recipe('booking.future_RH', cost=10)

        # PC expired block paid
        # user1 = baker.make_recipe('booking.user')
        # make_data_privacy_agreement(user1)
        # baker.make_recipe('booking.online_disclaimer', user=user1)
        block_pc = baker.make_recipe(
            'booking.block', block_type__event_type=pc.event_type,
            block_type__duration=2,
            user=self.user, start_date=timezone.now() - timedelta(days=100)
        )
        pc_block_booking = baker.make_recipe(
            'booking.booking', user=self.user, event=pc, block=block_pc,
        )
        self.assertTrue(pc_block_booking.paid)
        self.assertTrue(pc_block_booking.payment_confirmed)
        self.assertTrue(block_pc.expired)

        url = reverse('booking:delete_booking', args=[pc_block_booking.id])
        self.client.post(url)

        pc_block_booking.refresh_from_db()
        self.assertTrue(
            Block.objects.filter(
                block_type__identifier='transferred',
                transferred_booking_id=pc_block_booking.id
            ).exists()
        )

        # RH expired block paid
        block_rh = baker.make_recipe(
            'booking.block', block_type__event_type=rh.event_type,
            block_type__duration=2,
            user=self.user, start_date=timezone.now() - timedelta(days=100)
        )
        rh_block_booking = baker.make_recipe(
            'booking.booking', user=self.user, event=rh, block=block_rh,
        )
        self.assertTrue(rh_block_booking.paid)
        self.assertTrue(rh_block_booking.payment_confirmed)
        self.assertTrue(block_rh.expired)

        url = reverse('booking:delete_booking', args=[rh_block_booking.id])
        self.client.post(url)

        rh_block_booking.refresh_from_db()
        self.assertTrue(
            Block.objects.filter(
                block_type__identifier='transferred',
                transferred_booking_id=rh_block_booking.id
            ).exists()
        )

        # EV expired block paid
        block_ev = baker.make_recipe(
            'booking.block', block_type__event_type=ev.event_type,
            block_type__duration=2,
            user=self.user, start_date=timezone.now() - timedelta(days=100)
        )
        ev_block_booking = baker.make_recipe(
            'booking.booking', user=self.user, event=ev, block=block_ev,
        )
        self.assertTrue(ev_block_booking.paid)
        self.assertTrue(ev_block_booking.payment_confirmed)
        self.assertTrue(block_ev.expired)

        url = reverse('booking:delete_booking', args=[ev_block_booking.id])
        self.client.post(url)

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
        event = baker.make_recipe('booking.future_EV')
        booking = baker.make_recipe('booking.booking', event=event,
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
        event = baker.make_recipe('booking.future_EV')
        booking = baker.make_recipe('booking.booking', event=event,
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
        event = baker.make_recipe('booking.future_EV')
        booking = baker.make_recipe('booking.booking', event=event,
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
        event = baker.make_recipe('booking.future_EV')
        booking = baker.make_recipe('booking.booking', event=event,
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
        cls.pole_class_event_type = baker.make(
            EventType, event_type='CL', subtype='Pole level class'
        )
        cls.free_blocktype = baker.make_recipe(
            'booking.blocktype', size=1, cost=0,
            event_type=cls.pole_class_event_type, identifier='free class'
        )

    def setUp(self):
        super(BookingUpdateViewTests, self).setUp()
        self.user_no_disclaimer = baker.make_recipe('booking.user')
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
        workshop = baker.make_recipe('booking.future_EV', cost=10)
        tutorial = baker.make_recipe('booking.future_OT', cost=10)
        room_hire = baker.make_recipe('booking.future_RH', cost=10)
        pc = baker.make_recipe('booking.future_PC', cost=10)
        
        self.client.login(username=self.user.username, password="test")

        for event in [workshop, tutorial, room_hire, pc]:
            booking = baker.make_recipe(
                'booking.booking',
                user=self.user, event=event, paid=False
            )
            url = reverse('booking:update_booking', args=[booking.id])
            resp = self.client.get(url)
            assert resp.status_code == 200

    def test_cannot_get_page_for_paid_booking(self):
        event = baker.make_recipe('booking.future_EV', cost=10)
        booking = baker.make_recipe(
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
        event = baker.make_recipe('booking.future_EV', cost=10)
        booking = baker.make_recipe(
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
        block = baker.make_recipe(
            'booking.block_10', user=self.user,
            block_type__event_type=self.pole_class_event_type,
            block_type__assign_free_class_on_completion=True,
            paid=True, start_date=timezone.now()
        )
        event = baker.make_recipe(
            'booking.future_CL', cost=10, event_type=self.pole_class_event_type
        )

        booking = baker.make_recipe(
            'booking.booking',
            user=self.user, event=event, paid=False
        )

        baker.make_recipe(
            'booking.booking', block=block, user=self.user, _quantity=9
        )

        self.assertEqual(Block.objects.count(), 1)
        self._post_response(self.user, booking, {'block_book': 'yes'})

        self.assertEqual(block.bookings.count(), 10)
        self.assertEqual(Block.objects.count(), 2)
        self.assertEqual(Block.objects.latest('id').block_type, self.free_blocktype)

    def test_pay_with_block_uses_last_and_no_free_block_created(self):
        # block of 5 for 'CL' blocktype does not create free block
        block = baker.make_recipe(
            'booking.block_5', user=self.user,
            block_type__event_type=self.pole_class_event_type,
            paid=True, start_date=timezone.now()
        )
        event = baker.make_recipe(
            'booking.future_CL', cost=10, event_type=self.pole_class_event_type
        )

        booking = baker.make_recipe(
            'booking.booking',
            user=self.user, event=event, paid=False
        )

        baker.make_recipe(
            'booking.booking', block=block, user=self.user, _quantity=4
        )

        self.assertEqual(Block.objects.count(), 1)
        resp = self._post_response(self.user, booking, {'block_book': 'yes'})

        self.assertEqual(block.bookings.count(), 5)
        self.assertEqual(Block.objects.count(), 1)
        self.assertEqual(Block.objects.latest('id'), block)

    def test_pay_with_block_uses_last_of_free_class_allowed_blocks_free_block_already_exists(self):
        block = baker.make_recipe(
            'booking.block_10', user=self.user,
            block_type__event_type=self.pole_class_event_type,
            block_type__assign_free_class_on_completion=True,
            paid=True, start_date=timezone.now()
        )
        event = baker.make_recipe(
            'booking.future_EV', cost=10, event_type=self.pole_class_event_type
        )

        booking = baker.make_recipe(
            'booking.booking',
            user=self.user, event=event, paid=False
        )

        baker.make_recipe(
            'booking.block', user=self.user, block_type=self.free_blocktype,
            paid=True, parent=block
        )

        baker.make_recipe(
            'booking.booking', block=block, user=self.user, _quantity=9
        )
        self.assertEqual(Block.objects.count(), 2)
        self._post_response(self.user, booking, {'block_book': 'yes'})

        self.assertEqual(block.bookings.count(), 10)
        self.assertEqual(Block.objects.count(), 2)

    def test_cannot_access_if_no_disclaimer(self):
        event = baker.make_recipe('booking.future_EV', cost=10)
        booking = baker.make_recipe(
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
        event = baker.make_recipe('booking.future_EV', cost=10)
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event, paid=False)
        baker.make_recipe('booking.block',
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
        poleclass = baker.make_recipe('booking.future_PC', cost=10)
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=poleclass, paid=False)
        baker.make_recipe('booking.block',
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
        roomhire = baker.make_recipe('booking.future_RH', cost=10)
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=roomhire, paid=False)
        baker.make_recipe('booking.block',
                                  block_type__event_type=roomhire.event_type,
                                  user=self.user, paid=True)
        form_data = {'block_book': 'yes'}
        self._post_response(self.user, booking, form_data)
        updated_booking = Booking.objects.get(id=booking.id)
        self.assertTrue(updated_booking.paid)

    def test_update_online_tutorial_booking_to_paid(self):
        """
        Test updating a booking to paid with block
        """
        tutorial = baker.make_recipe('booking.future_OT', cost=10)
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=tutorial, paid=False)
        baker.make_recipe(
            'booking.block', block_type__event_type=tutorial.event_type, 
            user=self.user, paid=True
        )
        url = reverse('booking:update_booking', args=[booking.id])
        form_data = {'block_book': 'yes'}
        self.client.login(username=self.user.username, password="test")
        self.client.post(url, form_data)
        booking.refresh_from_db()
        self.assertTrue(booking.paid)

    def test_requesting_free_class(self):
        """
        Test that requesting a free class emails the studio but does not
        update the booking
        """
        event = baker.make_recipe('booking.future_EV', cost=10)
        booking = baker.make_recipe(
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
        event = baker.make_recipe('booking.future_EV', cancelled=True)
        booking = baker.make_recipe(
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
    @patch('booking.views.views_utils.timezone')
    def test_update_with_block_if_multiple_blocks_available(self, mock_tz, mock_tz1):
        """
        Usually there should be only one block of each type available, but in
        case an admin has added additional blocks, ensure that the one with the
        earlier expiry date is used
        """
        mock_now = datetime(2015, 1, 10, tzinfo=dt_timezone.utc)
        mock_tz.now.return_value = mock_now
        mock_tz1.now.return_value = mock_now

        event_type = baker.make_recipe('booking.event_type_PC')

        event = baker.make_recipe('booking.future_PC', event_type=event_type)
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event, paid=False
        )

        blocktype = baker.make_recipe(
            'booking.blocktype5', event_type=event_type, duration=2
        )
        block1 = baker.make_recipe(
            'booking.block', block_type=blocktype, user=self.user, paid=True,
            start_date=datetime(2015, 1, 2, tzinfo=dt_timezone.utc)
        )
        block2 = baker.make_recipe(
            'booking.block', block_type=blocktype, user=self.user, paid=True,
            start_date=datetime(2015, 1, 1, tzinfo=dt_timezone.utc)
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
        block2.start_date = datetime(2015, 1, 3, tzinfo=dt_timezone.utc)
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
        mock_tz.now.return_value = datetime(2015, 1, 10, tzinfo=dt_timezone.utc)
        event_type = baker.make_recipe('booking.event_type_PC')
        event_type1 = baker.make_recipe('booking.event_type_PC')

        event = baker.make_recipe('booking.future_PC', event_type=event_type)
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event, paid=False
        )
        # make block with different event type to the event we're trying to
        # book
        blocktype = baker.make_recipe(
            'booking.blocktype5', event_type=event_type1, duration=2
        )
        block = baker.make_recipe(
            'booking.block', block_type=blocktype, user=self.user, paid=True,
            start_date=datetime(2015, 1, 2, tzinfo=dt_timezone.utc)
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
        voucher = baker.make(EventVoucher, code='test', discount=10)
        voucher.event_types.add(self.pole_class_event_type)
        booking = baker.make(
            'booking.booking', event__event_type=self.pole_class_event_type,
            event__cost=10, user=self.user
        )
        resp = self._get_response(self.user, booking)
        self.assertIn('Cost: £ 10.00', resp.rendered_content)
        paypal_form = resp.context_data['paypalform']
        self.assertEqual(paypal_form.initial['amount'], 10.00)
        self.assertEqual(
            paypal_form.initial['custom'],
            'obj=booking ids={} usr={}'.format(booking.id, booking.user.email)
        )
        self.assertNotIn('voucher', resp.context_data)

        form_data = {'apply_voucher': 'Apply', 'code': 'test'}
        resp = self._post_response(self.user, booking, form_data)
        self.assertIn('Cost: £ 9.00', resp.rendered_content)
        paypal_form = resp.context_data['paypalform']
        self.assertEqual(paypal_form.initial['amount'], 9.00)
        self.assertEqual(
            paypal_form.initial['custom'],
            f'obj=booking ids={booking.id} usr={booking.user.email} cde={voucher.code} apd={booking.id}'
        )
        self.assertEqual(resp.context_data['voucher'], voucher)

    def test_no_voucher_code(self):
        booking = baker.make(
            'booking.booking', event__event_type=self.pole_class_event_type,
            event__cost=10, user=self.user
        )
        form_data = {'apply_voucher': 'Apply', 'code': ''}
        resp = self._post_response(self.user, booking, form_data)
        self.assertEqual(resp.context_data['voucher_error'], 'No code provided')

    def test_invalid_voucher_code(self):
        voucher = baker.make(EventVoucher, code='test', discount=10)
        voucher.event_types.add(self.pole_class_event_type)
        booking = baker.make(
            'booking.booking', event__event_type=self.pole_class_event_type,
            event__cost=10, user=self.user
        )
        form_data = {'apply_voucher': 'Apply', 'code': 'foo'}
        resp = self._post_response(self.user, booking, form_data)
        self.assertEqual(resp.context_data['voucher_error'], 'Invalid code')

    def test_voucher_code_not_started_yet(self):
        voucher = baker.make(
            EventVoucher, code='test', discount=10,
            start_date=timezone.now() + timedelta(2)
        )
        voucher.event_types.add(self.pole_class_event_type)
        booking = baker.make(
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
        voucher = baker.make(
            EventVoucher, code='test', discount=10,
            start_date=timezone.now() - timedelta(4),
            expiry_date=timezone.now() - timedelta(2)
        )
        voucher.event_types.add(self.pole_class_event_type)
        booking = baker.make(
            'booking.booking', event__event_type=self.pole_class_event_type,
            event__cost=10, user=self.user
        )
        form_data = {'apply_voucher': 'Apply', 'code': 'test'}
        resp = self._post_response(self.user, booking, form_data)
        self.assertEqual(
            resp.context_data['voucher_error'], 'Voucher code has expired'
        )

    def test_voucher_used_max_times(self):
        voucher = baker.make(
            EventVoucher, code='test', discount=10,
            max_vouchers=2
        )
        voucher.event_types.add(self.pole_class_event_type)
        users = baker.make_recipe('booking.user', _quantity=2)
        for user in users:
            UsedEventVoucher.objects.create(voucher=voucher, user=user)
        booking = baker.make(
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
        voucher = baker.make(
            EventVoucher, code='test', discount=10,
            max_vouchers=6, max_per_user=2
        )
        voucher.event_types.add(self.pole_class_event_type)
        users = baker.make_recipe('booking.user', _quantity=2)
        for user in users:
            UsedEventVoucher.objects.create(voucher=voucher, user=user)
        for i in range(2):
            UsedEventVoucher.objects.create(voucher=voucher, user=self.user)
        booking = baker.make(
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
        voucher = baker.make(EventVoucher, code='test', discount=10)
        voucher.event_types.add(self.pole_class_event_type)
        UsedEventVoucher.objects.create(voucher=voucher, user=self.user)
        booking = baker.make(
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
        voucher = baker.make(EventVoucher, code='test', discount=10)
        voucher.event_types.add(self.pole_class_event_type)
        booking = baker.make(
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
        voucher = baker.make(EventVoucher, code='test', discount=10)
        voucher.event_types.add(self.pole_class_event_type)
        booking = baker.make(
            'booking.booking', event__event_type=self.pole_class_event_type,
            event__cost=10, user=self.user
        )

        form_data = {'apply_voucher': 'Apply', 'code': '  test '}
        resp = self._post_response(self.user, booking, form_data)
        self.assertIn('Cost: £ 9.00', resp.rendered_content)
        paypal_form = resp.context_data['paypalform']
        self.assertEqual(paypal_form.initial['amount'], 9.00)
        self.assertEqual(
            paypal_form.initial['custom'],
            f'obj=booking ids={booking.id} usr={booking.user.email} cde={voucher.code} apd={booking.id}'
        )

    def test_update_with_block_from_shopping_basket(self):
        """
        Test updating a booking from basket returns to basket
        """
        block = baker.make_recipe(
            'booking.block_10', user=self.user,
            block_type__event_type=self.pole_class_event_type,
            paid=True, start_date=timezone.now()
        )
        event = baker.make_recipe(
            'booking.future_CL', cost=10, event_type=self.pole_class_event_type
        )

        booking = baker.make_recipe(
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
        block = baker.make_recipe(
            'booking.block_10', user=self.user,
            block_type__event_type=self.pole_class_event_type,
            paid=True, start_date=timezone.now()
        )
        event = baker.make_recipe(
            'booking.future_CL', cost=10, event_type=self.pole_class_event_type
        )

        booking = baker.make_recipe(
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
        baker.make_recipe(
            'booking.block_10', user=self.user,
            block_type__event_type=self.pole_class_event_type,
            paid=True, start_date=timezone.now()
        )
        event = baker.make_recipe(
            'booking.future_CL', cost=10, event_type=self.pole_class_event_type
        )

        booking = baker.make_recipe(
            'booking.booking',
            user=self.user, event=event, paid=False
        )

        self.client.login(username=self.user.username, password='test')

        url = reverse('booking:update_booking', args=[booking.id])

        self.client.get(url)

        # booking added to cart_items on get
        self.assertEqual(
            self.client.session['cart_items'],
            'obj=booking ids={} usr={}'.format(str(booking.id), booking.user.email)
        )

        # posting means submitting for block payment, so cart_items deleted
        self.client.post(url, data={'block_book': True})
        self.assertNotIn('cart_items', self.client.session)
