from django.test import TestCase
from django.contrib.admin.sites import AdminSite

from model_mommy import mommy
from booking.models import Event, Booking, Block
import booking.admin as admin


class EventAdminTests(TestCase):

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


class BookingAdminTests(TestCase):

    def setUp(self):
        self.user = mommy.make_recipe(
            'booking.user', first_name="Test", last_name="User"
        )

    def test_booking_date_list_filter(self):
        past_event = mommy.make_recipe('booking.past_event', name='past')
        future_event = mommy.make_recipe('booking.future_EV', name='future')
        mommy.make_recipe('booking.booking', user=self.user, event=past_event)
        mommy.make_recipe('booking.booking', user=self.user, event=future_event)

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

    def test_booking_admin_display(self):
        event = mommy.make_recipe('booking.future_EV', cost=6)

        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event
        )

        booking_admin = admin.BookingAdmin(Booking, AdminSite())
        booking_query = booking_admin.get_queryset(None)[0]

        self.assertEqual(
            booking_admin.get_date(booking_query), booking.event.date
        )
        self.assertEqual(
            booking_admin.get_user_first_name(booking_query), 'Test'
        )
        self.assertEqual(
            booking_admin.get_user_last_name(booking_query), 'User'
        )
        self.assertEqual(booking_admin.get_cost(booking_query), u"\u00A3{}.00".format(event.cost))
        self.assertEqual(booking_admin.event_name(booking_query), event.name)

    def test_confirm_space(self):
        users = mommy.make_recipe('booking.user', _quantity=10)
        ev = mommy.make_recipe('booking.future_EV', cost=5)
        ws = mommy.make_recipe('booking.future_WS', cost=5)
        for user in users[:5]:
            mommy.make_recipe('booking.booking', user=user, event=ev)
        for user in users[5:]:
            mommy.make_recipe('booking.booking', user=user, event=ws)

        self.assertEquals(len(Booking.objects.filter(paid=True)), 0)
        self.assertEquals(len(Booking.objects.filter(payment_confirmed=True)), 0)

        booking_admin = admin.BookingAdmin(Booking, AdminSite())
        queryset = Booking.objects.filter(event__event_type__subtype__contains='Other event')
        booking_admin.confirm_space(None, queryset)
        self.assertEquals(len(Booking.objects.filter(paid=True)), 5)
        self.assertEquals(len(Booking.objects.filter(payment_confirmed=True)), 5)


class BlockAdminTests(TestCase):

    def test_block_admin_display(self):
        block = mommy.make_recipe('booking.block_5')
        block_admin = admin.BlockAdmin(Block, AdminSite())
        block_query = block_admin.get_queryset(None)[0]

        self.assertEqual(
            block_admin.formatted_cost(block_query), u"\u00A3{}".format(block.block_type.cost)
        )
        self.assertEqual(
            block_admin.formatted_expiry_date(block_query),
            block.expiry_date.strftime('%d %b %Y, %H:%M')
        )
