from django.core.urlresolvers import reverse
from django.test import TestCase, RequestFactory
from django.test.client import Client
from mock import patch
from model_mommy import mommy
from booking.models import Event, Booking, Block
from booking.views import EventListView, EventDetailView, \
    LessonDetailView, BookingListView, BookingHistoryListView, \
    BookingDetailView, BookingCreateView, BookingDeleteView, BookingUpdateView
from booking.tests.helpers import set_up_fb


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
        mommy.make_recipe('booking.future_EV', _quantity=1)
        mommy.make_recipe('booking.future_PC', _quantity=3)
        mommy.make_recipe('booking.future_CL', _quantity=3)
        mommy.make_recipe('booking.future_WS', _quantity=1)
        self.user = mommy.make_recipe('booking.user')

    def test_event_list(self):
        """
        Test that only classes are listed (pole classes and other classes)
        """
        url = reverse('booking:lessons')
        resp = self.client.get(url)

        self.assertEquals(Event.objects.all().count(), 8)
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context['events'].count(), 6)
        self.assertEquals(resp.context['type'], 'lessons')


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
        self.events = mommy.make_recipe('booking.future_EV', _quantity=3)
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
        Test that only booking for this user are listed
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

        # event listing should still only show this user's future bookings
        self.assertEquals(resp.context_data['bookings'].count(), 1)


class BookingDetailViewTests(TestCase):

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

    def _get_response(self, user, booking):
        url = reverse('booking:booking_detail', args=[booking.id])
        request = self.factory.get(url)
        request.user = user
        view = BookingDetailView.as_view()
        return view(request, pk=booking.id)

    def test_login_required(self):
        """
        test that page redirects if there is no user logged in
        """
        url = reverse('booking:booking_detail', args=[self.booking.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

    def test_with_logged_in_user(self):
        """
        test that page loads if there is a user available
        """
        resp = self._get_response(self.user, self.booking)
        self.assertEqual(resp.status_code, 200)

    def test_past_booking(self):
        """
        test that past booking does not show buttons
        """
        resp = self._get_response(self.user, self.past_booking)
        self.assertEqual(resp.status_code, 200)

        resp.render()
        self.assertFalse("Confirm payment made" in str(resp.content))
        self.assertFalse("Delete booking" in str(resp.content))


class BookingCreateViewTests(TestCase):
    def setUp(self):
        set_up_fb()
        self.factory = RequestFactory()
        self.user = mommy.make_recipe('booking.user')
        self.event = mommy.make_recipe('booking.future_EV', max_participants=3)

    def _get_response(self, user, event):
        url = reverse('booking:book_event', kwargs={'event_slug': event.slug})
        request = self.factory.post(url, {'event': event.id})
        request.user = user
        view = BookingCreateView.as_view()
        return view(request, event_slug=event.slug)

    def test_create_booking(self):
        """
        Test creating a booking
        """
        self.assertEqual(Booking.objects.all().count(), 0)
        self._get_response(self.user, self.event)
        self.assertEqual(Booking.objects.all().count(), 1)

    def test_cannot_create_duplicate_booking(self):
        """
        Test trying to create a duplicate booking redirects
        """
        resp = self._get_response(self.user, self.event)
        booking_id = Booking.objects.all()[0].id
        booking_url = reverse('booking:booking_detail', args=[booking_id])
        self.assertEqual(resp.url, booking_url)

        resp1 = self._get_response(self.user, self.event)
        # test redirect to duplicate booking url
        self.assertEqual(
            resp1.url,
            reverse(
                'booking:duplicate_booking',
                kwargs={'event_slug': self.event.slug}
            )
        )

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


class BookingDeleteViewTests(TestCase):

    def setUp(self):
        set_up_fb()
        self.factory = RequestFactory()
        self.user = mommy.make_recipe('booking.user')

    def _get_response(self, user, booking):
        url = reverse('booking:delete_booking', args=[booking.id])
        request = self.factory.delete(url)
        request.user = user
        view = BookingDeleteView.as_view()
        return view(request, pk=booking.id)

    def test_create_booking(self):
        """
        Test deleting a booking
        """
        booking = mommy.make_recipe('booking.booking', user=self.user)
        self.assertEqual(Booking.objects.all().count(), 1)
        self._get_response(self.user, booking)
        self.assertEqual(Booking.objects.all().count(), 0)

    def test_deleting_only_this_booking(self):
        """
        Test deleting a booking when user has more than one
        """
        mommy.make_recipe(
            'booking.booking', user=self.user, _quantity=3
        )
        self.assertEqual(Booking.objects.all().count(), 3)
        booking = Booking.objects.all()[0]
        self._get_response(self.user, booking)
        self.assertEqual(Booking.objects.all().count(), 2)


class BookingUpdateViewTests(TestCase):

    def setUp(self):
        set_up_fb()
        self.factory = RequestFactory()
        self.user = mommy.make_recipe('booking.user')

    def _get_response(self, user, booking, form_data):
        url = reverse('booking:update_booking', args=[booking.id])
        request = self.factory.post(url, form_data)
        request.user = user
        view = BookingUpdateView.as_view()
        return view(request, pk=booking.id)

    def test_update_booking_to_paid(self):
        """
        Test updating a booking to paid (as confirmed by user)
        """
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, paid=False)
        form_data = {'paid': True}
        resp = self._get_response(self.user, booking, form_data)
        updated_booking = Booking.objects.get(id=booking.id)
        self.assertTrue(updated_booking.paid)


class BlockCreateViewTests(TestCase):
    pass

#TODO Block Create view
# TODO Block tests (for forms/views?)
# TODO If a block has 5 or 10 bookings, no more bookings can be made
# TODO If a user has an active block, they can't buy a new block
# TODO Can user book against a block before block payment confirmed?  Maybe allow
# TODO booking for 1 week after block start date, then prevent it if payment not
# TODO received

# TODO Test trying to book with a block for an event that is not a pole class
