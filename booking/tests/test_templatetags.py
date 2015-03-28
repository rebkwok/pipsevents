from django.core.urlresolvers import reverse
from django.test import TestCase, RequestFactory
from django.test.client import Client
from model_mommy import mommy
from booking.views import EventDetailView
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

    def test_cancellation_format_tag(self):
        """
        Test that cancellation period is formatted correctly
        """
        event = mommy.make_recipe('booking.future_EV', cancellation_period=24)
        resp = self._get_response(self.user, event)
        resp.render()
        import ipdb; ipdb.set_trace()
        self.assertEquals(resp.context_data['booking_info_text'],
                          'You have booked for this event.')
