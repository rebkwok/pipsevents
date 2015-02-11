from django.core.urlresolvers import reverse
from django.contrib.sites.models import Site
from django.test import TestCase, RequestFactory
from django.test.client import Client
from mock import patch
from model_mommy import mommy
from booking.models import Event, Booking, Block
from booking.views import EventListView, EventDetailView


class EventViewTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()
        mommy.make_recipe('booking.future_EV', _quantity=3)
        mommy.make_recipe('booking.future_PC', _quantity=3)
        mommy.make_recipe('booking.future_CL', _quantity=3)
        fbapp = mommy.make_recipe('booking.fb_app')
        site = Site.objects.get_current()
        fbapp.sites.add(site.id)
        self.user = mommy.make_recipe('booking.user')

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
        url = reverse('booking:events')
        request = self.factory.get(url)
        # Set the user on the request
        request.user = self.user

        view = EventListView.as_view()

        resp = view(request)
        self.assertTrue('booked_events' in resp.context_data)

    def test_event_list_with_booked_events(self):
        """
        test that booked events are shown on listing
        """
        url = reverse('booking:events')
        request = self.factory.get(url)
        # Set the user on the request
        request.user = self.user
        view = EventListView.as_view()
        resp = view(request)
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(len(resp.context_data['booked_events']), 0)

        # create a booking for this user
        booked_event = Event.objects.all()[0]
        mommy.make_recipe('booking.booking', user=self.user, event=booked_event)
        resp = view(request)
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

        url = reverse('booking:events')
        request = self.factory.get(url)
        # Set the user on the request
        request.user = self.user
        view = EventListView.as_view()
        resp = view(request)
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(len(resp.context_data['booked_events']), 0)

        # create booking for this user
        mommy.make_recipe('booking.booking', user=self.user, event=event1)
        # create booking for another user
        user1 = mommy.make_recipe('booking.user')
        mommy.make_recipe('booking.booking', user=user1, event=event2)

        # check only event1 shows in the booked events
        resp = view(request)
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(Booking.objects.all().count(), 2)
        self.assertEquals(len(booked_events), 1)
        self.assertTrue(event1 in booked_events)


class EventDetailViewTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()
        self.event = mommy.make_recipe('booking.future_EV')
        mommy.make_recipe('booking.future_PC', _quantity=3)
        mommy.make_recipe('booking.future_CL', _quantity=3)
        fbapp = mommy.make_recipe('booking.fb_app')
        site = Site.objects.get_current()
        fbapp.sites.add(site.id)
        self.user = mommy.make_recipe('booking.user')


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
        url = reverse('booking:event_detail', args=[self.event.slug])
        request = self.factory.get(url)
        # Set the user on the request
        request.user = self.user
        view = EventDetailView.as_view()
        resp = view(request, slug=self.event.slug)

        self.assertEqual(resp.status_code, 200)

    def test_with_booked_event(self):
        """
        Test that booked event is shown as booked
        """
        url = reverse('booking:event_detail', args=[self.event.slug])
        request = self.factory.get(url)

        #create a booking for this event and user
        mommy.make_recipe('booking.booking', user=self.user, event=self.event)

        # Set the user on the request
        request.user = self.user
        view = EventDetailView.as_view()
        resp = view(request, slug=self.event.slug)

        self.assertTrue(resp.context_data['booked'])
        self.assertEquals(resp.context_data['booking_info_text'],
                          'You have booked for this event.')

    def test_with_booked_event_for_different_user(self):
        """
        Test that the event is not shown as booked if the current user has
        not booked it
        """
        url = reverse('booking:event_detail', args=[self.event.slug])
        request = self.factory.get(url)

        user1 = mommy.make_recipe('booking.user')
        #create a booking for this event and a different user
        mommy.make_recipe('booking.booking', user=user1, event=self.event)

        # Set the user on the request
        request.user = self.user
        view = EventDetailView.as_view()
        resp = view(request, slug=self.event.slug)

        self.assertFalse('booked' in resp.context_data)
        self.assertEquals(resp.context_data['booking_info_text'], '')

class EventDetailContextTests(TestCase):
    #TODO:
    #TODO Test that the context is returned properly for events with adv payment, full,
    #TODO paid, spaces left, costs, payment info etc.
    #TODO Should only need to do this for events once, not separately for events and classes
    pass



# TODO Block tests (for forms/views?)
# TODO If a block has 5 or 10 bookings, no more bookings can be made
# TODO If a user has an active block, they can't buy a new block
# TODO Can user book against a block before block payment confirmed?  Maybe allow
# TODO booking for 1 week after block start date, then prevent it if payment not
# TODO received

# TODO Test trying to book with a block for an event that is not a pole class
