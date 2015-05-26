from datetime import datetime, timedelta
from mock import Mock, patch
from model_mommy import mommy

from django.core.urlresolvers import reverse
from django.test import TestCase, RequestFactory
from django.test.client import Client
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone

from booking.forms import BlockCreateForm
from booking.models import Event, Booking, Block
from booking.views import EventListView, EventDetailView, LessonDetailView, \
    BookingListView, BookingHistoryListView, BookingCreateView, \
    BookingDeleteView, BookingUpdateView, BlockCreateView, BlockListView, \
    LessonListView, duplicate_booking, fully_booked, cancellation_period_past
from booking.tests.helpers import set_up_fb, _create_session, setup_view


class EventListViewTests(TestCase):

    def setUp(self):
        set_up_fb()
        self.client = Client()
        self.factory = RequestFactory()
        mommy.make_recipe('booking.future_EV', _quantity=3)
        mommy.make_recipe('booking.future_PC', _quantity=3)
        mommy.make_recipe('booking.future_CL', _quantity=3)
        self.user = mommy.make_recipe('booking.user')

    def _get_response(self, user):
        url = reverse('booking:events')
        request = self.factory.get(url)
        request.user = user
        view = EventListView.as_view()
        return view(request)

    def test_event_list(self):
        """
        Test that only events are listed (workshops and other events)
        """
        url = reverse('booking:events')
        resp = self.client.get(url)

        self.assertEquals(Event.objects.all().count(), 9)
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context['events'].count(), 3)

    def test_event_list_past_event(self):
        """
        Test that past events is not listed
        """
        mommy.make_recipe('booking.past_event')
        # check there are now 4 events
        self.assertEquals(Event.objects.all().count(), 10)
        url = reverse('booking:events')
        resp = self.client.get(url)

        # event listing should still only show future events
        self.assertEquals(resp.context['events'].count(), 3)

    def test_event_list_with_anonymous_user(self):
        """
        Test that no booked_events in context
        """
        url = reverse('booking:events')
        resp = self.client.get(url)

        # event listing should still only show future events
        self.assertFalse('booked_events' in resp.context)

    def test_event_list_with_logged_in_user(self):
        """
        Test that booked_events in context
        """
        resp = self._get_response(self.user)
        self.assertTrue('booked_events' in resp.context_data)

    def test_event_list_with_booked_events(self):
        """
        test that booked events are shown on listing
        """
        resp = self._get_response(self.user)
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(len(resp.context_data['booked_events']), 0)

        # create a booking for this user
        booked_event = Event.objects.all()[0]
        mommy.make_recipe('booking.booking', user=self.user, event=booked_event)
        resp = self._get_response(self.user)
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(len(booked_events), 1)
        self.assertTrue(booked_event in booked_events)

    def test_event_list_shows_only_current_user_bookings(self):
        """
        Test that only user's booked events are shown as booked
        """
        events = Event.objects.all()
        event1 = events[0]
        event2 = events[1]

        resp = self._get_response(self.user)
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(len(resp.context_data['booked_events']), 0)

        # create booking for this user
        mommy.make_recipe('booking.booking', user=self.user, event=event1)
        # create booking for another user
        user1 = mommy.make_recipe('booking.user')
        mommy.make_recipe('booking.booking', user=user1, event=event2)

        # check only event1 shows in the booked events
        resp = self._get_response(self.user)
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(Booking.objects.all().count(), 2)
        self.assertEquals(len(booked_events), 1)
        self.assertTrue(event1 in booked_events)

    def test_filter_events(self):
        """
        Test that we can filter the classes by name
        """
        mommy.make_recipe('booking.future_EV', name='test_name', _quantity=3)
        mommy.make_recipe('booking.future_EV', name='test_name1', _quantity=4)

        url = reverse('booking:events')
        resp = self.client.get(url, {'name': 'test_name'})
        self.assertEquals(resp.context['events'].count(), 3)


class EventDetailViewTests(TestCase):

    def setUp(self):
        set_up_fb()
        self.client = Client()
        self.factory = RequestFactory()
        self.event = mommy.make_recipe('booking.future_EV')
        mommy.make_recipe('booking.future_PC', _quantity=3)
        mommy.make_recipe('booking.future_CL', _quantity=3)
        self.user = mommy.make_recipe('booking.user')

    def _get_response(self, user, event):
        url = reverse('booking:event_detail', args=[event.slug])
        request = self.factory.get(url)
        request.user = user
        view = EventDetailView.as_view()
        return view(request, slug=event.slug)

    def test_login_required(self):
        """
        test that page redirects if there is no user logged in
        """
        url = reverse('booking:event_detail', kwargs={'slug': self.event.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

    def test_with_logged_in_user(self):
        """
        test that page loads if there user is available
        """
        resp = self._get_response(self.user, self.event)
        self.assertEqual(resp.status_code, 200)
        self.assertEquals(resp.context_data['type'], 'event')

    def test_with_booked_event(self):
        """
        Test that booked event is shown as booked
        """
        #create a booking for this event and user
        mommy.make_recipe('booking.booking', user=self.user, event=self.event)
        resp = self._get_response(self.user, self.event)
        self.assertTrue(resp.context_data['booked'])
        self.assertEquals(resp.context_data['booking_info_text'],
                          'You have booked for this event.')

    def test_with_booked_event_for_different_user(self):
        """
        Test that the event is not shown as booked if the current user has
        not booked it
        """
        user1 = mommy.make_recipe('booking.user')
        #create a booking for this event and a different user
        mommy.make_recipe('booking.booking', user=user1, event=self.event)

        resp = self._get_response(self.user, self.event)
        self.assertFalse('booked' in resp.context_data)
        self.assertEquals(resp.context_data['booking_info_text'], '')


class LessonListViewTests(TestCase):
    """
    LessonListView reuses the event templates and context data helpers
    so only basic functionality is retested
    """
    def setUp(self):
        set_up_fb()
        self.client = Client()
        self.factory = RequestFactory()
        mommy.make_recipe('booking.future_EV', _quantity=1)
        mommy.make_recipe('booking.future_PC', _quantity=3)
        mommy.make_recipe('booking.future_CL', _quantity=3)
        mommy.make_recipe('booking.future_WS', _quantity=1)
        self.user = mommy.make_recipe('booking.user')

    def _get_response(self, user):
        url = reverse('booking:lessons')
        request = self.factory.get(url)
        request.user = user
        view = LessonListView.as_view()
        return view(request)

    def test_with_logged_in_user(self):
        """
        test that page loads if there is a user is available
        """
        resp = self._get_response(self.user)
        self.assertEqual(resp.status_code, 200)
        self.assertEquals(resp.context_data['type'], 'lessons')
        self.assertTrue('booked_events' in resp.context_data)

    def test_lesson_list_with_anonymous_user(self):
        """
        Test that no booked_events in context
        """
        url = reverse('booking:lessons')
        resp = self.client.get(url)

        # event listing should still only show future events
        self.assertFalse('booked_events' in resp.context)

    def test_lesson_list(self):
        """
        Test that only classes are listed (pole classes and other classes)
        """
        url = reverse('booking:lessons')
        resp = self.client.get(url)

        self.assertEquals(Event.objects.all().count(), 8)
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context['events'].count(), 6)
        self.assertEquals(resp.context['type'], 'lessons')

    def test_filter_lessons(self):
        """
        Test that we can filter the classes by name
        """
        mommy.make_recipe('booking.future_PC', name='test_name', _quantity=3)
        mommy.make_recipe('booking.future_PC', name='test_name1', _quantity=4)

        url = reverse('booking:lessons')
        resp = self.client.get(url, {'name': 'test_name'})
        self.assertEquals(resp.context['events'].count(), 3)
        resp = self.client.get(url, {'name': 'test_name1'})
        self.assertEquals(resp.context['events'].count(), 4)

    def test_lesson_list_shows_only_current_user_bookings(self):
        """
        Test that only user's booked events are shown as booked
        """
        events = Event.objects.filter(event_type__event_type="CL")
        event1 = events[0]
        event2 = events[1]

        resp = self._get_response(self.user)
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(len(resp.context_data['booked_events']), 0)

        # create booking for this user
        mommy.make_recipe('booking.booking', user=self.user, event=event1)
        # create booking for another user
        user1 = mommy.make_recipe('booking.user')
        mommy.make_recipe('booking.booking', user=user1, event=event2)

        # check only event1 shows in the booked events
        resp = self._get_response(self.user)
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(Booking.objects.all().count(), 2)
        self.assertEquals(len(booked_events), 1)
        self.assertTrue(event1 in booked_events)

    def test_lesson_list_only_shows_open_bookings(self):
        events = Event.objects.filter(event_type__event_type="CL")
        event1 = events[0]
        event2 = events[1]

        resp = self._get_response(self.user)
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(len(resp.context_data['booked_events']), 0)

        # create open and cancelled booking for this user
        mommy.make_recipe('booking.booking', user=self.user, event=event1)
        mommy.make_recipe(
            'booking.booking', user=self.user, event=event2, status='CANCELLED'
        )

        # check only event1 shows in the booked events
        resp = self._get_response(self.user)
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(Booking.objects.all().count(), 2)
        self.assertEquals(len(booked_events), 1)
        self.assertTrue(event1 in booked_events)


class LessonDetailViewTests(TestCase):
    """
    LessonDetailView reuses the event templates and context data helpers
    so only basic functionality is retested
    """
    def setUp(self):
        self.factory = RequestFactory()
        self.lesson = mommy.make_recipe('booking.future_PC')
        mommy.make_recipe('booking.future_EV', _quantity=3)
        mommy.make_recipe('booking.future_PC', _quantity=3)
        set_up_fb()
        self.user = mommy.make_recipe('booking.user')

    def test_with_logged_in_user(self):
        """
        test that page loads if there user is available
        """
        url = reverse('booking:lesson_detail', args=[self.lesson.slug])
        request = self.factory.get(url)
        # Set the user on the request
        request.user = self.user
        view = LessonDetailView.as_view()
        resp = view(request, slug=self.lesson.slug)

        self.assertEqual(resp.status_code, 200)
        self.assertEquals(resp.context_data['type'], 'lesson')


class BookingListViewTests(TestCase):

    def setUp(self):
        set_up_fb()
        self.client = Client()
        self.factory = RequestFactory()
        self.user = mommy.make_recipe('booking.user')
        # name events explicitly to avoid invoice id conflicts in tests
        # (should never happen in reality since the invoice id is built from
        # (event name initials and datetime)
        self.events = [
            mommy.make_recipe('booking.future_EV',  name="First Event"),
            mommy.make_recipe('booking.future_EV',  name="Scnd Event"),
            mommy.make_recipe('booking.future_EV',  name="Third Event")
        ]
        future_bookings = [mommy.make_recipe(
            'booking.booking', user=self.user,
            event=event) for event in self.events]
        mommy.make_recipe('booking.past_booking', user=self.user)

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

    def test_cancelled_booking_not_showing_in_booking_list(self):
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


class BookingHistoryListViewTests(TestCase):

    def setUp(self):
        set_up_fb()
        self.client = Client()
        self.factory = RequestFactory()
        self.user = mommy.make_recipe('booking.user')
        event = mommy.make_recipe('booking.future_EV')
        self.booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event
        )
        self.past_booking = mommy.make_recipe(
            'booking.past_booking', user=self.user
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


class BookingCreateViewTests(TestCase):
    def setUp(self):
        set_up_fb()
        self.factory = RequestFactory()
        self.user = mommy.make_recipe('booking.user')

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

    def test_cannot_create_duplicate_booking(self):
        """
        Test trying to create a duplicate booking redirects
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

    def test_cannot_book_for_full_event(self):
        """
        Test trying to create a duplicate booking redirects
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

    def test_cancelled_booking_can_be_rebooked(self):
        """
        Test can load create booking page with a cancelled booking
        """

        event = mommy.make_recipe('booking.future_EV')
        # book for event
        resp = self._post_response(self.user, event)

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
        resp = self._post_response(self.user, event)

        booking = Booking.objects.get(user=self.user, event=event)
        # cancel booking
        booking.status = 'CANCELLED'
        booking.save()

        # try to book again
        resp = self._post_response(self.user, event)
        booking = Booking.objects.get(user=self.user, event=event)
        self.assertEqual('OPEN', booking.status)

    def test_rebook_cancelled_booking_still_paid(self):

        """
        Test rebooking a cancelled booking still marked as paid makes
        booking status open but does not confirm space
        """
        event = mommy.make_recipe('booking.future_PC')
        booking = mommy.make_recipe(
            'booking.booking', event=event, user=self.user, status='CANCELLED'
        )

        # try to book again
        resp = self._post_response(self.user, event)
        booking = Booking.objects.get(user=self.user, event=event)
        self.assertEqual('OPEN', booking.status)
        self.assertFalse(booking.payment_confirmed)

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
        block = mommy.make_recipe(
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
        resp = self._post_response(self.user, event, form_data)

        bookings = Booking.objects.filter(user=self.user)
        self.assertEqual(bookings.count(), 1)
        self.assertEqual(bookings[0].block, block)


class BookingErrorRedirectPagesTests(TestCase):

    def setUp(self):
        set_up_fb()
        self.factory = RequestFactory()
        self.user = mommy.make_recipe('booking.user')

    def test_duplicate_booking(self):
        """
        Get the duplicate booking page with the event context
        """
        event = mommy.make_recipe('booking.future_EV')
        url = reverse(
            'booking:duplicate_booking', kwargs={'event_slug': event.slug}
        )
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = self.user
        messages = FallbackStorage(request)
        request._messages = messages
        resp = duplicate_booking(request, event.slug)
        self.assertIn(event.name, str(resp.content))

    def test_fully_booked(self):
        """
        Get the fully booked page with the event context
        """
        event = mommy.make_recipe('booking.future_EV')
        url = reverse(
            'booking:fully_booked', kwargs={'event_slug': event.slug}
        )
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = self.user
        messages = FallbackStorage(request)
        request._messages = messages
        resp = fully_booked(request, event.slug)
        self.assertIn(event.name, str(resp.content))

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


class BookingDeleteViewTests(TestCase):

    def setUp(self):
        set_up_fb()
        self.factory = RequestFactory()
        self.user = mommy.make_recipe('booking.user')

    def _get_response(self, user, booking):
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
        self._get_response(self.user, booking)
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
        self._get_response(self.user, booking)
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
        self._get_response(self.user, booking)

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
        self._get_response(self.user, booking)

        booking = Booking.objects.get(user=self.user, event=event)
        self.assertEqual('CANCELLED', booking.status)
        self.assertFalse(booking.block)
        self.assertFalse(booking.paid)

        block = Block.objects.get(user=self.user)
        self.assertEqual(block.bookings_made(), 0)


    @patch("booking.views.timezone")
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


class BookingUpdateViewTests(TestCase):

    def setUp(self):
        set_up_fb()
        self.factory = RequestFactory()
        self.user = mommy.make_recipe('booking.user')

    def _get_response(self, user, booking, form_data):
        url = reverse('booking:update_booking', args=[booking.id])
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

        view = BookingUpdateView.as_view()
        return view(request, pk=booking.id)

    def test_update_booking_to_paid(self):
        """
        Test updating a booking to paid with block
        """
        event = mommy.make_recipe('booking.future_EV', cost=10)
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event, paid=False)
        block = mommy.make_recipe('booking.block',
                                  block_type__event_type=event.event_type,
                                  user=self.user, paid=True)
        form_data = {'block_book': 'yes'}
        resp = self._get_response(self.user, booking, form_data)
        updated_booking = Booking.objects.get(id=booking.id)
        self.assertTrue(updated_booking.paid)


class BlockCreateViewTests(TestCase):
    def setUp(self):
        set_up_fb()
        self.factory = RequestFactory()
        self.user = mommy.make_recipe('booking.user')

    def _set_session(self, user, request):
        request.session = _create_session()
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

    def _get_response(self, user):
        url = reverse('booking:add_block')
        request = self.factory.get(url)
        self._set_session(user, request)
        view = BlockCreateView.as_view()
        return view(request)

    def _post_response(self, user, form_data):
        url = reverse('booking:add_block')
        request = self.factory.post(url, form_data)
        self._set_session(user, request)
        view = BlockCreateView.as_view()
        return view(request)

    def test_create_block(self):
        """
        Test creating a block
        """
        block_type = mommy.make_recipe('booking.blocktype5')
        form_data={'block_type': block_type}
        resp = self._post_response(self.user, form_data)
        self.assertEqual(resp.status_code, 200)

    def test_create_block_if_no_blocktypes_available(self):
        """
        Test that the create block page redirects if there are no blocktypes
        available to book
        """
        block_type = mommy.make_recipe('booking.blocktype5')
        mommy.make_recipe(
            'booking.block', user=self.user, block_type=block_type
        )
        resp = self._get_response(self.user)
        self.assertEqual(resp.status_code, 302)

    def test_create_block_redirects_if_no_blocktypes_available(self):
        """
        Test that create block form redirects if trying to create a
        block with an event type that the user already has
        """
        event_type = mommy.make_recipe('booking.event_type_PC')
        block_type_pc5 = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type
        )
        block_type_pc10 = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type
        )
        mommy.make_recipe(
            'booking.block', user=self.user, block_type=block_type_pc5,
            paid=True
        )
        # create form with a different blocktype, but one with the same event
        # type as the user's booked block
        form_data = {'block_type': block_type_pc10}

        url = reverse('booking:add_block')
        request = self.factory.post(url, form_data)
        self._set_session(self.user, request)

        form_data = {'block_type': block_type_pc10.id}
        form = BlockCreateForm(data=form_data)
        form.full_clean()
        view = setup_view(BlockCreateView, request)
        resp = view.form_valid(view, form)

        self.assertEqual(resp.status_code, 302)

    def test_create_block_with_available_blocktypes(self):
        """
        Test that only user does not have the option to book a blocktype
        for which they already have an active block
        """
        block_type = mommy.make_recipe('booking.blocktype5')
        other_block_type = mommy.make_recipe('booking.blocktype_other')
        mommy.make_recipe(
            'booking.block', user=self.user, block_type=block_type
        )
        resp = self._get_response(self.user)
        self.assertEqual(len(resp.context_data['block_types']), 1)
        self.assertEqual(resp.context_data['block_types'][0], other_block_type)

    def test_cannot_create_block_with_same_event_type_as_active_block(self):
        """
        Test that only user does not have the option to book a blocktype
        if they already have a block for the same event type
        """
        event_type = mommy.make_recipe('booking.event_type_PC')
        block_type_pc5 = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type
        )
        block_type_pc10 = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type
        )
        other_block_type = mommy.make_recipe('booking.blocktype_other')
        mommy.make_recipe(
            'booking.block', user=self.user, block_type=block_type_pc5
        )
        resp = self._get_response(self.user)
        self.assertEqual(len(resp.context_data['block_types']), 1)
        self.assertEqual(resp.context_data['block_types'][0], other_block_type)

    def test_can_create_block_if_has_expired_block(self):
        """
        Test user has the option to create a block with the same event type as
        an expired block
        """
        event_type = mommy.make_recipe('booking.event_type_PC')
        block_type_pc5 = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type
        )
        # this user has a block of this blocktype that has expired
        mommy.make_recipe(
            'booking.block', user=self.user, block_type=block_type_pc5,
            start_date=timezone.now() - timedelta(weeks=52)
        )
        resp = self._get_response(self.user)
        self.assertEqual(len(resp.context_data['block_types']), 1)
        self.assertEqual(resp.context_data['block_types'][0], block_type_pc5)

    def test_can_create_block_if_has_full_block(self):
        """
        Test user has the option to create a block with the same event type as
        a full block
        """
        event_type = mommy.make_recipe('booking.event_type_PC')
        block_type_pc5 = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type
        )
        # this user has a block of this blocktype
        block = mommy.make_recipe(
            'booking.block', user=self.user, block_type=block_type_pc5
        )
        # fill block
        mommy.make_recipe(
            'booking.booking', user=self.user, block=block, _quantity=5
        )

        resp = self._get_response(self.user)
        self.assertEqual(len(resp.context_data['block_types']), 1)
        self.assertEqual(resp.context_data['block_types'][0], block_type_pc5)

    def test_cannot_create_block_if_has_unpaid_block_with_same_event_type(self):
        """
        Test user does not have the option to create a block with the same
        event type as an unpaid block
        """
        event_type = mommy.make_recipe('booking.event_type_PC')
        block_type_pc5 = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type
        )
        other_block_type = mommy.make_recipe('booking.blocktype_other')
        # this user has a block of this blocktype
        block = mommy.make_recipe(
            'booking.block', user=self.user, block_type=block_type_pc5,
            paid=False
        )

        resp = self._get_response(self.user)
        # only the "other" blocktype is available
        self.assertEqual(len(resp.context_data['block_types']), 1)
        self.assertEqual(resp.context_data['block_types'][0], other_block_type)


class BlockListViewTests(TestCase):
    def setUp(self):
        set_up_fb()
        self.factory = RequestFactory()

    def _set_session(self, user, request):
        request.session = _create_session()
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

    def _get_response(self, user):
        url = reverse('booking:block_list')
        request = self.factory.get(url)
        self._set_session(user, request)
        view = BlockListView.as_view()
        return view(request)

    def test_only_list_users_blocks(self):
        users = mommy.make_recipe('booking.user', _quantity=4)
        for user in users:
            mommy.make_recipe('booking.block_5', user=user)
        user = users[0]

        resp = self._get_response(user)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Block.objects.all().count(), 4)
        self.assertEqual(resp.context_data['blocks'].count(), 1)



#TODO register view
#TODO confirm payment, confirm refund plus permissions


