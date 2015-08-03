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

from booking.models import Event, Booking, Block
from booking.views import BookingListView, BookingCreateView, BookingDeleteView, \
    EventListView, EventDetailView, \
    duplicate_booking, fully_booked, cancellation_period_past
from booking.tests.helpers import set_up_fb, _create_session


class TestWaitingList(TestCase):

    def setUp(self):
        set_up_fb()
        self.client = Client()
        self.factory = RequestFactory()

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

    def _get_booking_create(self, user, event):
        url = reverse('booking:book_event', kwargs={'event_slug': event.slug})
        store = _create_session()
        request = self.factory.get(url, {'event': event.id})
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
