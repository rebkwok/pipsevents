from datetime import timedelta

from django.test import TestCase
from django.contrib.admin.sites import AdminSite
from django.utils import timezone

from model_mommy import mommy
from booking.models import Event, Booking, Block, BlockType
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

        # no filter parameters returns all
        filter = admin.EventDateListFilter(None, {}, Event, admin.EventAdmin)
        events = filter.queryset(None, Event.objects.all())
        self.assertEqual(events.count(), 2)

    def test_event_type_list_filter(self):
        event = mommy.make_recipe('booking.future_EV', name='event')
        pclass = mommy.make_recipe('booking.future_PC', name='pole class')

        filter = admin.EventTypeListFilter(
            None, {'type': 'class'}, Event, admin.EventAdmin
        )

        result = filter.queryset(None, Event.objects.all())
        self.assertEqual(result.count(), 1)
        self.assertEqual(result[0].name, 'pole class')

        filter = admin.EventTypeListFilter(
            None, {'type': 'event'}, Event, admin.EventAdmin
        )

        result = filter.queryset(None, Event.objects.all())
        self.assertEqual(result.count(), 1)
        self.assertEqual(result[0].name, 'event')

        # no filter parameters returns all
        filter = admin.EventTypeListFilter(None, {}, Event, admin.EventAdmin)
        events = filter.queryset(None, Event.objects.all())
        self.assertEqual(events.count(), 2)

    def test_spaces_left_display(self):
        event = mommy.make_recipe('booking.future_EV', max_participants=5)
        mommy.make_recipe('booking.booking', event=event, _quantity=3)

        ev_admin = admin.EventAdmin(Event, AdminSite())
        ev_query = ev_admin.get_queryset(None)[0]
        self.assertEqual(ev_admin.get_spaces_left(ev_query), 2)


class BookingAdminTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = mommy.make_recipe(
            'booking.user', first_name="Test", last_name="User",
            username="testuser"
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

        # no filter parameters returns all
        filter = admin.BookingDateListFilter(
            None, {}, Booking, admin.BookingAdmin
        )
        bookings = filter.queryset(None, Booking.objects.all())
        self.assertEqual(bookings.count(), 2)


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
            booking_admin.get_user(booking_query), 'Test User (testuser)'
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

    def test_booking_user_filter_choices(self):
        # test that user filter shows formatted choices ordered by first name
        user = mommy.make_recipe(
            'booking.user', first_name='Donald', last_name='Duck',
            username='dd')
        userfilter = admin.UserFilter(None, {}, Booking, admin.BookingAdmin)
        self.assertEqual(
            userfilter.lookup_choices,
            [
                (user.id, 'Donald Duck (dd)'),
                (self.user.id, 'Test User (testuser)')
            ]
        )

    def test_paypal_booking_user_filter(self):
        user = mommy.make_recipe(
            'booking.user', first_name='Donald', last_name='Duck',
            username='dd')
        mommy.make_recipe('booking.booking', user=self.user, _quantity=5)
        mommy.make_recipe('booking.booking', user=user, _quantity=5)

        userfilter = admin.UserFilter(None, {}, Booking, admin.BookingAdmin)
        result = userfilter.queryset(None, Booking.objects.all())

        # with no filter parameters, return all
        self.assertEqual(Booking.objects.count(), 10)
        self.assertEqual(result.count(), 10)
        self.assertEqual(
            [booking.id for booking in result],
            [booking.id for booking in Booking.objects.all()]
        )

        userfilter = admin.UserFilter(
            None, {'user': self.user.id}, Booking, admin.BookingAdmin
        )
        result = userfilter.queryset(None, Booking.objects.all())
        self.assertEqual(result.count(), 5)
        self.assertEqual(
            [booking.id for booking in result],
            [booking.id for booking in Booking.objects.filter(user=self.user)]
        )


class BlockAdminTests(TestCase):

    def test_block_admin_display(self):
        user = mommy.make_recipe(
            'booking.user', first_name='Donald', last_name='Duck',
            username='dd')
        block = mommy.make_recipe('booking.block_5', user=user)
        block_admin = admin.BlockAdmin(Block, AdminSite())
        block_query = block_admin.get_queryset(None)[0]

        self.assertEqual(
            block_admin.formatted_cost(block_query),
            u"\u00A3{}".format(block.block_type.cost)
        )
        self.assertEqual(
            block_admin.formatted_expiry_date(block_query),
            block.expiry_date.strftime('%d %b %Y, %H:%M')
        )
        self.assertEqual(
            block_admin.get_full(block_query), False
        )
        self.assertEqual(
            block_admin.block_size(block_query), 5
        )
        self.assertEqual(
            block_admin.formatted_start_date(block_query),
            block.start_date.strftime('%d %b %Y, %H:%M')
        )
        self.assertEqual(block_admin.get_user(block_query), 'Donald Duck (dd)')

    def test_block_list_filter(self):
        unpaid_block = mommy.make_recipe(
            'booking.block_5', paid=False,
            start_date=timezone.now() - timedelta(1)
        )
        paid_block = mommy.make_recipe(
            'booking.block_5', paid=True,
            start_date=timezone.now() - timedelta(1)
        )
        expired_block = mommy.make_recipe(
            'booking.block_5', paid=True,
            start_date=timezone.now() - timedelta(weeks=10)
        )
        full_block = mommy.make_recipe(
            'booking.block_5', paid=True,
            start_date=timezone.now() - timedelta(1)
        )
        mommy.make_recipe('booking.booking', block=full_block, _quantity=5)

        filter = admin.BlockFilter(
            None, {'status': 'active'}, Block, admin.BlockAdmin
        )
        block_qset = filter.queryset(None, Block.objects.all())
        self.assertEqual(block_qset.count(), 1)
        block = block_qset[0]
        self.assertEqual(block.id, paid_block.id)

        filter = admin.BlockFilter(
            None, {'status': 'inactive'}, Block, admin.BlockAdmin
        )
        block_qset = filter.queryset(None, Block.objects.all())
        self.assertEqual(block_qset.count(), 3)
        block_ids = [block.id for block in block_qset]
        self.assertEqual(
            sorted(block_ids),
            sorted([expired_block.id, full_block.id, unpaid_block.id])
        )

        filter = admin.BlockFilter(
            None, {'status': 'unpaid'}, Block, admin.BlockAdmin
        )
        block_qset = filter.queryset(None, Block.objects.all())
        self.assertEqual(block_qset.count(), 1)
        block = block_qset[0]
        self.assertEqual(block.id, unpaid_block.id)

        # no filter parameters returns all
        filter = admin.BlockFilter(None, {}, Block, admin.BlockAdmin)
        blocks = filter.queryset(None, Block.objects.all())
        self.assertEqual(blocks.count(), 4)


class BlockTypeAdminTests(TestCase):

    def test_block_type_admin_display(self):
        block = mommy.make_recipe('booking.block_5')
        block_type_admin = admin.BlockTypeAdmin(BlockType, AdminSite())
        block_type_query = block_type_admin.get_queryset(None)[0]

        self.assertEqual(
            block_type_admin.formatted_cost(block_type_query),
            u"\u00A3{}".format(block.block_type.cost)
        )
        self.assertEqual(
            block_type_admin.formatted_duration(block_type_query),
            '2 months'
        )
