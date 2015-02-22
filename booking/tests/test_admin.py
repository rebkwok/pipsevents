from django.test import TestCase
from model_mommy import mommy
from booking.models import Event, Booking, Block
import booking.admin as admin


class AdminFilterTests(TestCase):
    def test_booking_date_list_filter(self):
        past_event = mommy.make_recipe('booking.past_event', name='past')
        future_event = mommy.make_recipe('booking.future_EV', name='future')
        mommy.make_recipe('booking.booking', event=past_event)
        mommy.make_recipe('booking.booking', event=future_event)

        filter = admin.BookingDateListFilter(
            None, {'event__date': 'past'}, Booking, admin.BookingAdmin
        )
        booking = filter.queryset(None, Booking.objects.all())[0]
        self.assertEqual(booking.event.name, 'past')

        filter = admin.BookingDateListFilter(
            None, {'event__date': 'upcoming'}, Booking, admin.BookingAdmin
        )
        booking = filter.queryset(None, Booking.objects.all())[0]
        self.assertEqual(booking.event.name, 'future')

    def test_event_date_list_filter(self):
        past_event = mommy.make_recipe('booking.past_event', name='past')
        future_event = mommy.make_recipe('booking.future_EV', name='future')

        filter = admin.EventDateListFilter(
            None, {'date': 'past'}, Event, admin.EventAdmin
        )
        event = filter.queryset(None, Event.objects.all())[0]
        self.assertEqual(event.name, 'past')

        filter = admin.EventDateListFilter(
            None, {'date': 'upcoming'}, Event, admin.EventAdmin
        )
        event = filter.queryset(None, Event.objects.all())[0]
        self.assertEqual(event.name, 'future')
