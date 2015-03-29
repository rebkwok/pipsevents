from django.core.urlresolvers import reverse
from django.test import TestCase, RequestFactory
from django.test.client import Client
from model_mommy import mommy
from booking.views import EventDetailView, BookingDetailView
from booking.tests.helpers import set_up_fb


class BookingtagTests(TestCase):

    def setUp(self):
        set_up_fb()
        self.client = Client()
        self.factory = RequestFactory()
        self.user = mommy.make_recipe('booking.user')

    def _get_response(self, user, event):
        url = reverse('booking:event_detail', args=[event.slug])
        request = self.factory.get(url)
        request.user = user
        view = EventDetailView.as_view()
        return view(request, slug=event.slug)

    def test_cancellation_format_tag_event_detail(self):
        """
        Test that cancellation period is formatted correctly
        """
        event = mommy.make_recipe('booking.future_EV', cancellation_period=24)
        resp = self._get_response(self.user, event)
        resp.render()
        self.assertIn('24 hours', str(resp.content))

        event = mommy.make_recipe('booking.future_EV', cancellation_period=619)
        resp = self._get_response(self.user, event)
        resp.render()
        self.assertIn('3 weeks, 4 days and 19 hours', str(resp.content))

        event = mommy.make_recipe('booking.future_EV', cancellation_period=168)
        resp = self._get_response(self.user, event)
        resp.render()
        self.assertIn('1 week', str(resp.content))

        event = mommy.make_recipe('booking.future_EV', cancellation_period=192)
        resp = self._get_response(self.user, event)
        resp.render()
        self.assertIn('1 week, 1 day and 0 hours', str(resp.content))

    def test_cancellation_format_tag_booking_detail(self):
        """
        Test that cancellation period is formatted correctly
        """
        event = mommy.make_recipe('booking.future_EV', cancellation_period=24)
        booking = mommy.make_recipe('booking.booking', event=event, user=self.user)
        url = reverse('booking:booking_detail', args=[booking.pk])
        request = self.factory.get(url)
        request.user = self.user
        view = BookingDetailView.as_view()
        resp = view(request, pk=booking.pk)
        resp.render()
        self.assertIn('24 hours', str(resp.content))