from datetime import datetime, timedelta
from mock import Mock, patch
from model_mommy import mommy

from django.core import mail
from django.core.urlresolvers import reverse
from django.test import TestCase, RequestFactory
from django.test.client import Client
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone
from django.contrib.auth.models import Permission

from booking.models import Event, Booking, Block, WaitingListUser
from booking.views import BookingListView, BookingCreateView, \
    BookingDeleteView, BookingUpdateView, update_booking_cancelled, \
    EventListView, EventDetailView, \
    duplicate_booking, fully_booked, cancellation_period_past
from booking.tests.helpers import set_up_fb, _create_session

from studioadmin.tests.test_views import TestPermissionMixin
from studioadmin.views import user_bookings_view


class WaitingListTests(TestCase):

    def setUp(self):
        set_up_fb()
        self.client = Client()
        self.factory = RequestFactory()
        self.user = mommy.make_recipe('booking.user')

    def _get_event_list(self, user, ev_type):
        url = reverse('booking:events')
        request = self.factory.get(url)
        request.user = user
        view = EventListView.as_view()
        return view(request, ev_type=ev_type)

    def _get_event_detail(self, user, event, ev_type):
        url = reverse('booking:event_detail', args=[event.slug])
        request = self.factory.get(url)
        request.user = user
        view = EventDetailView.as_view()
        return view(request, slug=event.slug, ev_type=ev_type)

    def _get_booking_list(self, user):
        url = reverse('booking:bookings')
        request = self.factory.get(url)
        request.user = user
        view = BookingListView.as_view()
        return view(request)

    def _get_booking_update(self, user, booking):
        url = reverse('booking:update_booking', args=[booking.id])
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

        view = BookingUpdateView.as_view()
        return view(request, pk=booking.id)

    def _get_booking_update_cancelled(self, user, booking):
        url = reverse('booking:update_booking_cancelled', args=[booking.id])
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

        return update_booking_cancelled(request, pk=booking.id)

    def _get_booking_create(self, user, event, extra_data={}):
        url = reverse('booking:book_event', kwargs={'event_slug': event.slug})
        store = _create_session()
        data = {'event': event.id}
        data.update(extra_data)
        request = self.factory.get(url, data)
        request.session = store
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        view = BookingCreateView.as_view()
        return view(request, event_slug=event.slug)

    def _post_booking_create(self, user, event, form_data={}):
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

    def _booking_delete(self, user, booking):
        url = reverse('booking:delete_booking', args=[booking.id])
        session = _create_session()
        request = self.factory.delete(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        view = BookingDeleteView.as_view()
        return view(request, pk=booking.id)

    def test_waiting_list_button_on_events_list(self):
        """
        Test that a full event displays the 'Join Waiting List' button on the
        events list page
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        resp = self._get_event_list(self.user, "lessons")
        resp.render()
        self.assertIn('book_button', str(resp.content))
        self.assertNotIn('join_waiting_list_button', str(resp.content))

        mommy.make_recipe('booking.booking', event=event)
        resp = self._get_event_list(self.user, "lessons")
        resp.render()
        self.assertIn('join_waiting_list_button', str(resp.content))
        self.assertNotIn('book_button', str(resp.content))

    def test_event_list_for_booked_full_event(self):
        """
        Test that a full event that the user is already booked for does not
        display 'Join waiting list'
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        mommy.make_recipe('booking.booking', event=event, user=self.user)
        resp = self._get_event_list(self.user, "lessons")
        self.assertEquals(resp.context_data['booked_events'], [event])
        resp.render()
        self.assertNotIn('book_button', str(resp.content))
        self.assertNotIn('join_waiting_list_button', str(resp.content))

    def test_event_list_already_on_waiting_list_full_event(self):
        """
        Test that a full event that the user is already on the waiting list for
        displays 'On waiting list'
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=3)
        mommy.make_recipe(
            'booking.waiting_list_user', event=event, user=self.user
        )
        resp = self._get_event_list(self.user, "lessons")
        self.assertEquals(resp.context_data['waiting_list_events'], [event])

        resp.render()
        self.assertNotIn('book_button', str(resp.content))
        self.assertNotIn('join_waiting_list_button', str(resp.content))
        self.assertIn('leave_waiting_list_button', str(resp.content))

    def test_waiting_list_events_context(self):
        wlevent = mommy.make_recipe('booking.future_PC', max_participants=2)
        events = mommy.make_recipe('booking.future_PC', _quantity=5)
        event = events[0]
        mommy.make_recipe('booking.booking', event=wlevent, _quantity=2)
        mommy.make_recipe(
            'booking.waiting_list_user', event=wlevent, user=self.user
        )
        mommy.make_recipe('booking.booking', event=event, user=self.user)

        resp = self._get_event_list(self.user, "lessons")
        self.assertEquals(resp.context_data['waiting_list_events'], [wlevent])
        self.assertEquals(resp.context_data['booked_events'], [event])

    def test_event_list_already_on_waiting_list_not_full_event(self):
        """
        Test that a not full event that the user is already on the waiting list
        for displays 'Book' button
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        mommy.make_recipe(
            'booking.waiting_list_user', event=event, user=self.user
        )
        resp = self._get_event_list(self.user, "lessons")
        self.assertEquals(resp.context_data['waiting_list_events'], [event])

        resp.render()
        self.assertIn('book_button', str(resp.content))
        self.assertNotIn('join_waiting_list_button', str(resp.content))
        self.assertNotIn('leave_waiting_list_button', str(resp.content))

    def test_waiting_list_button_on_event_detail_list(self):
        """
        Test that a full event displays the 'Join Waiting List' button on the
        event detail page
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        resp = self._get_event_detail(self.user, event, "lesson")
        resp.render()
        self.assertIn('book_button', str(resp.content))
        self.assertNotIn('join_waiting_list_button', str(resp.content))

        mommy.make_recipe('booking.booking', event=event)
        resp = self._get_event_detail(self.user, event, "lesson")
        resp.render()
        self.assertIn('join_waiting_list_button', str(resp.content))
        self.assertNotIn('book_button', str(resp.content))

    def test_event_detail_for_booked_full_event(self):
        """
        Test that a full event that the user is already booked for does not
        display 'Join waiting list'
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        mommy.make_recipe('booking.booking', event=event, user=self.user)
        resp = self._get_event_detail(self.user, event, "lessons")
        self.assertTrue(resp.context_data['booked'])
        self.assertNotIn('waiting_list', resp.context_data)
        resp.render()
        self.assertNotIn('book_button', str(resp.content))
        self.assertNotIn('join_waiting_list_button', str(resp.content))

    def test_event_detail_already_on_waiting_list_full_event(self):
        """
        Test that a full event that the user is already on the waiting list for
        displays 'On waiting list'
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=3)
        mommy.make_recipe(
            'booking.waiting_list_user', event=event, user=self.user
        )
        resp = self._get_event_detail(self.user, event,  "lessons")
        self.assertTrue(resp.context_data['waiting_list'])
        resp.render()
        self.assertNotIn('book_button', str(resp.content))
        self.assertNotIn('join_waiting_list_button', str(resp.content))
        self.assertIn('leave_waiting_list_button', str(resp.content))

    def test_event_detail_already_on_waiting_list_not_full_event(self):
        """
        Test that a not full event that the user is already on the waiting list
        for displays 'book_button' button
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        mommy.make_recipe(
            'booking.waiting_list_user', event=event, user=self.user
        )
        resp = self._get_event_detail(self.user, event, "lessons")
        self.assertTrue(resp.context_data['waiting_list'])
        resp.render()
        self.assertIn('book_button', str(resp.content))
        self.assertNotIn('join_waiting_list_button', str(resp.content))
        self.assertNotIn('leave_waiting_list_button', str(resp.content))

    def test_booking_list_cancelled_booking(self):
        """
        Test that a cancelled booking shows 'join waiting list' button if
        event is full
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        mommy.make_recipe(
            'booking.booking', event=event, user=self.user, status='CANCELLED'
        )
        resp = self._get_booking_list(self.user)
        resp.render()
        self.assertIn('rebook_button', str(resp.content))

        mommy.make_recipe('booking.booking', event=event)
        resp = self._get_booking_list(self.user)
        resp.render()
        self.assertNotIn('rebook_button', str(resp.content))
        self.assertNotIn('leave_waiting_list_button', str(resp.content))
        self.assertIn('join_waiting_list_button', str(resp.content))

    def test_booking_list_cancelled_booking_already_on_waiting_list(self):
        """
        Test that a cancelled booking shows 'on waiting list' button if
        event is full and user already on the waiting list
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        mommy.make_recipe(
            'booking.booking', event=event, user=self.user, status='CANCELLED'
        )
        mommy.make_recipe(
            'booking.waiting_list_user', user=self.user, event=event
        )
        resp = self._get_booking_list(self.user)
        resp.render()
        # user is on waiting list, but event not full; show "Rebook"
        self.assertIn('rebook', str(resp.content))

        mommy.make_recipe('booking.booking', event=event)
        resp = self._get_booking_list(self.user)
        resp.render()
        # user is on waiting list, event is full; show "On waiting list"
        self.assertIn('leave_waiting_list_button', str(resp.content))
        self.assertNotIn('rebook_button', str(resp.content))
        self.assertNotIn('join_waiting_list_button', str(resp.content))

    def test_join_waiting_list(self):
        """
        Test that joining waiting list add WaitingListUser to event and
        redirects to events list
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=3)

        self.assertEqual(WaitingListUser.objects.count(), 0)
        resp = self._get_booking_create(
            self.user, event, {'join waiting list': ['Join waiting list']}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:lessons'))

        waiting_list = WaitingListUser.objects.filter(event=event)
        self.assertEqual(len(waiting_list), 1)
        self.assertEqual(waiting_list[0].user, self.user)

    def test_already_on_waiting_list(self):
        """
        Test that trying to join waiting list when already on it does add
        another WaitingListUser and redirects to events list
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=3)
        # create waiting list user for this user and event
        mommy.make_recipe(
            'booking.waiting_list_user', user=self.user, event=event
        )
        self.assertEqual(WaitingListUser.objects.count(), 1)
        resp = self._get_booking_create(
            self.user, event, {'join waiting list': ['Join waiting list']}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:lessons'))
        waiting_list = WaitingListUser.objects.filter(event=event)
        # still only one waiting list user
        self.assertEqual(len(waiting_list), 1)

    def test_booking_when_already_on_waiting_list(self):
        """
        Test that when booking, a user is removed from the waiting list
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        # create waiting list user for this user and event
        mommy.make_recipe(
            'booking.waiting_list_user', user=self.user, event=event
        )
        self.assertEqual(WaitingListUser.objects.count(), 1)
        self.assertEqual(Booking.objects.filter(event=event).count(), 2)
        resp = self._post_booking_create(self.user, event)
        waiting_list = WaitingListUser.objects.filter(event=event)
        # user now removed from waiting list
        self.assertEqual(len(waiting_list), 0)
        self.assertEqual(Booking.objects.filter(event=event).count(), 3)
        booking = Booking.objects.filter(event=event).last()
        self.assertEqual(booking.user, self.user)

    def test_booking_only_removes_current_user_from_waiting_list(self):
        """
        Test that when booking, a user is removed from the waiting list but
        other users remain on the waiting list
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        # create waiting list user for this user and event
        mommy.make_recipe(
            'booking.waiting_list_user', user=self.user, event=event
        )
        mommy.make_recipe(
            'booking.waiting_list_user', event=event, _quantity=5
        )
        waiting_list = WaitingListUser.objects.filter(event=event)
        self.assertEqual(waiting_list.count(), 6)
        self.assertEqual(Booking.objects.filter(event=event).count(), 2)
        resp = self._post_booking_create(self.user, event)

        # user now removed from waiting list
        waiting_list = WaitingListUser.objects.filter(event=event)
        self.assertEqual(waiting_list.count(), 5)
        self.assertEqual(Booking.objects.filter(event=event).count(), 3)
        booking = Booking.objects.filter(event=event).last()
        self.assertEqual(booking.user, self.user)

        waiting_list_users = [wluser.user for wluser in waiting_list]
        self.assertNotIn(self.user, waiting_list_users)

    def test_update_cancelled_booking(self):
        """
        If booking is cancelled and we try to go to update page, we
        redirect to update_booking_cancelled, which shows rebook
        button
        """
        event = mommy.make_recipe('booking.future_PC')
        booking = mommy.make_recipe(
            'booking.booking',
            user=self.user, event=event, status='CANCELLED'
        )

        resp = self._get_booking_update(self.user, booking)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url,
            reverse(
                'booking:update_booking_cancelled', args=[booking.id]
            )
        )

        resp = self._get_booking_update_cancelled(self.user, booking)
        self.assertIn('rebook_button', str(resp.content))

    def test_update_cancelled_booking_full_event(self):
        """
        If booking is cancelled and we try to go to update page, we
        redirect to update_booking_cancelled, which shows join waiting
        list button if the event is full
        """
        event = mommy.make_recipe(
            'booking.future_PC',
            max_participants=3
        )
        mommy.make_recipe(
            'booking.booking', event=event, _quantity=3
        )
        booking = mommy.make_recipe(
            'booking.booking',
            user=self.user, event=event, status='CANCELLED'
        )

        resp = self._get_booking_update(self.user, booking)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url,
            reverse(
                'booking:update_booking_cancelled', args=[booking.id]
            )
        )

        resp = self._get_booking_update_cancelled(self.user, booking)
        self.assertIn('join_waiting_list_button', str(resp.content))

    def test_deleting_booking_emails_waiting_list(self):
        """
        Test that when a user cancels from a full booking, any
        users on the waiting list are emailed by bcc
        """
        event = mommy.make_recipe(
            'booking.future_PC',
            max_participants=3
        )
        mommy.make_recipe(
            'booking.booking', event=event, _quantity=2
        )
        booking = mommy.make_recipe(
            'booking.booking',
            user=self.user, event=event
        )
        for i in range(3):
            mommy.make_recipe(
                'booking.waiting_list_user', event=event,
                user__email='test{}@test.com'.format(i)
            )

        self.assertEqual(
            Booking.objects.filter(event=event, status='OPEN').count(),
            3
        )
        resp = self._booking_delete(self.user, booking)
        self.assertEqual(
            Booking.objects.filter(event=event, status='OPEN').count(),
            2
        )
        # 2 emails are sent on cancelling; cancel email to user and
        # a single email with bcc to waiting list users
        self.assertEqual(len(mail.outbox), 2)
        wl_email = mail.outbox[1]
        self.assertEqual(
            sorted(wl_email.bcc),
            ['test0@test.com', 'test1@test.com', 'test2@test.com']
        )


class WaitingListStudioadminUserBookingListTests(TestPermissionMixin, TestCase):

    def _post_response(
        self, user, user_id, form_data, booking_status='future'
        ):
        url = reverse(
            'studioadmin:user_bookings_list',
            kwargs={'user_id': user_id, 'booking_status': booking_status}
        )
        form_data['booking_status'] = [booking_status]
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return user_bookings_view(
            request, user_id, booking_status=booking_status
        )

    def test_cancel_booking_for_full_event(self):
        """
        Cancelling a booking for a full event emails users on the
        waiting list
        """

        # make full event
        event = mommy.make_recipe(
            'booking.future_PC', max_participants=3)
        bookings = mommy.make_recipe(
            'booking.booking', event=event, _quantity=3
        )
        booking_to_cancel = bookings[0]

        # make some waiting list users
        for i in range(3):
            mommy.make_recipe(
                'booking.waiting_list_user', event=event,
                user__email='test{}@test.com'.format(i)
            )

        data = {
            'bookings-TOTAL_FORMS': 1,
            'bookings-INITIAL_FORMS': 1,
            'bookings-0-id': booking_to_cancel.id,
            'bookings-0-event': booking_to_cancel.event.id,
            'bookings-0-status': 'CANCELLED',
            'bookings-0-paid': booking_to_cancel.paid,
            }

        self.assertEqual(booking_to_cancel.status, 'OPEN')

        self._post_response(
            self.staff_user, booking_to_cancel.user.id,
            form_data=data
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            sorted(mail.outbox[0].bcc),
            ['test0@test.com', 'test1@test.com', 'test2@test.com']
        )

        booking_to_cancel.refresh_from_db()
        self.assertEqual(booking_to_cancel.status, 'CANCELLED')

    def test_cancel_booking_for_non_full_event(self):
        """
        Cancelling a booking for a not full event does not email
        users on the waiting list
        """

        # make not full event
        event = mommy.make_recipe(
            'booking.future_PC', max_participants=3)
        bookings = mommy.make_recipe(
            'booking.booking', event=event, _quantity=2
        )
        booking_to_cancel = bookings[0]

        # make some waiting list users
        mommy.make_recipe(
            'booking.waiting_list_user', event=event, _quantity=3
        )

        data = {
            'bookings-TOTAL_FORMS': 1,
            'bookings-INITIAL_FORMS': 1,
            'bookings-0-id': booking_to_cancel.id,
            'bookings-0-event': booking_to_cancel.event.id,
            'bookings-0-status': 'CANCELLED',
            'bookings-0-paid': booking_to_cancel.paid,
            }

        self.assertEqual(booking_to_cancel.status, 'OPEN')

        self._post_response(
            self.staff_user, booking_to_cancel.user.id,
            form_data=data
        )
        self.assertEqual(len(mail.outbox), 0)

        booking_to_cancel.refresh_from_db()
        self.assertEqual(booking_to_cancel.status, 'CANCELLED')

    def test_create_booking_for_user_on_waiting_list(self):
        """
        Creating a booking for a user on the waiting list for an
        event removes the user from the waiting list
        """

        # make full event
        event = mommy.make_recipe(
            'booking.future_PC', max_participants=3)

        # add self.user to waiting list users
        mommy.make_recipe(
            'booking.waiting_list_user', event=event,
            user=self.user
        )

        data = {
            'bookings-TOTAL_FORMS': 1,
            'bookings-INITIAL_FORMS': 0,
            'bookings-0-event': event.id,
            'bookings-0-status': 'OPEN',
            'bookings-0-paid': 'on',
            }

        self.assertEqual(Booking.objects.count(), 0)
        self.assertEqual(WaitingListUser.objects.count(), 1)
        self._post_response(
            self.staff_user, self.user.id, form_data=data
        )
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(WaitingListUser.objects.count(), 0)
