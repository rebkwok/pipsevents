from model_mommy import mommy

from django.core.urlresolvers import reverse
from django.test import TestCase, RequestFactory
from django.test.client import Client

from booking.models import TicketedEvent, TicketBooking, Ticket
from booking.views import TicketedEventListView
from booking.tests.helpers import set_up_fb


class EventListViewTests(TestCase):

    def setUp(self):
        set_up_fb()
        self.client = Client()
        self.factory = RequestFactory()
        mommy.make_recipe('booking.ticketed_event_max10', _quantity=3)
        self.user = mommy.make_recipe('booking.user')

    def _get_response(self, user):
        url = reverse('booking:ticketed_events')
        request = self.factory.get(url)
        request.user = user
        view = TicketedEventListView.as_view()
        return view(request)

    def test_ticketed_event_list(self):
        """
        Test that only ticketed_events are listed
        """
        url = reverse('booking:ticketed_events')
        resp = self.client.get(url)

        self.assertEquals(TicketedEvent.objects.all().count(), 3)
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context['ticketed_events'].count(), 3)

    def test_event_list_past_event(self):
        """
        Test that past event is not listed
        """
        mommy.make_recipe('booking.ticketed_event_past_max10')
        # check there are now 4 events
        self.assertEquals(TicketedEvent.objects.all().count(), 4)
        url = reverse('booking:ticketed_events')
        resp = self.client.get(url)

        # event listing should still only show future events
        self.assertEquals(resp.context['ticketed_events'].count(), 3)

    def test_event_list_with_anonymous_user(self):
        """
        Test that no booked_events in context
        """
        url = reverse('booking:ticketed_events')
        resp = self.client.get(url)

        self.assertFalse('tickets_booked_events' in resp.context)

    def test_event_list_with_logged_in_user(self):
        """
        Test that booked_events in context
        """
        resp = self._get_response(self.user)
        self.assertTrue('tickets_booked_events' in resp.context_data)

    def test_event_list_with_ticket_booking_without_tickets(self):
        """
        test that booked events are shown on listing
        """
        resp = self._get_response(self.user)
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['tickets_booked_events']]
        self.assertEquals(len(resp.context_data['tickets_booked_events']), 0)

        # create a booking for this user with no tickets
        booked_event = TicketedEvent.objects.all()[0]
        mommy.make(
            TicketBooking, user=self.user,
            ticketed_event=booked_event
        )
        resp = self._get_response(self.user)
        booked_events = [event for event in resp.context_data['tickets_booked_events']]
        # ticket bookings without attached tickets are ignored
        self.assertEquals(len(booked_events), 0)

    def test_event_list_with_booked_events(self):
        """
        test that booked events are shown on listing
        """
        resp = self._get_response(self.user)
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['tickets_booked_events']]
        self.assertEquals(len(resp.context_data['tickets_booked_events']), 0)

        # create a booking for this user
        booked_event = TicketedEvent.objects.all()[0]
        mommy.make(
            Ticket, ticket_booking__user=self.user,
            ticket_booking__ticketed_event=booked_event
        )
        resp = self._get_response(self.user)
        booked_events = [event for event in resp.context_data['tickets_booked_events']]
        self.assertEquals(len(booked_events), 1)
        self.assertTrue(booked_event in booked_events)

    def test_event_list_shows_only_current_user_bookings(self):
        """
        Test that only user's booked events are shown as booked
        """
        events = TicketedEvent.objects.all()
        event1 = events[0]
        event2 = events[1]

        resp = self._get_response(self.user)
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['tickets_booked_events']]
        self.assertEquals(len(resp.context_data['tickets_booked_events']), 0)

        # create booking for this user
        mommy.make(
            Ticket, ticket_booking__user=self.user,
            ticket_booking__ticketed_event=event1
        )
        # create booking for another user
        user1 = mommy.make_recipe('booking.user')
        mommy.make(
            Ticket, ticket_booking__user=user1,
            ticket_booking__ticketed_event=event2
        )

        # check only event1 shows in the booked events
        resp = self._get_response(self.user)
        booked_events = [event for event in resp.context_data['tickets_booked_events']]
        self.assertEquals(TicketBooking.objects.all().count(), 2)
        self.assertEquals(len(booked_events), 1)
        self.assertTrue(event1 in booked_events)

    def test_events_not_listed_if_show_on_site_false(self):
        mommy.make_recipe(
            'booking.ticketed_event_max10', show_on_site=False
        )
        # check there are now 4 events
        self.assertEquals(TicketedEvent.objects.all().count(), 4)
        url = reverse('booking:ticketed_events')
        resp = self.client.get(url)

        # event listing should only show events ticked as show on site
        self.assertEquals(resp.context['ticketed_events'].count(), 3)