from datetime import timedelta

from model_mommy import mommy

from django.core.urlresolvers import reverse
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

import booking.admin as admin
from booking.models import Event, Booking, Block, BlockType, TicketBooking, \
    Ticket, BlockVoucher, EventVoucher, UsedBlockVoucher, UsedEventVoucher
from booking.tests.helpers import format_content


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

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username='test', email='test@test.com', password='test'
        )

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

    def test_adding_new_booking_to_block(self):
        self.client.login(username=self.superuser.username, password='test')

        user = mommy.make_recipe('booking.user')
        block = mommy.make_recipe('booking.block_5', paid=True, user=user)
        event = mommy.make_recipe(
            'booking.future_PC', event_type=block.block_type.event_type
        )

        url = reverse('admin:booking_block_change', args=[block.id])
        data = {
            'user': user.id,
            'block_type': block.block_type.id,
            'start_date_0': block.start_date.strftime('%d/%m/%Y'),
            'start_date_1': block.start_date.strftime('%H:%M:%S'),
            'paid': block.paid,
            'bookings-TOTAL_FORMS': 1,
            'bookings-INITIAL_FORMS': 0,
            'bookings-0-event': event.id,
            'bookings-0-status': 'OPEN'
        }

        self.assertEqual(block.bookings.count(), 0)
        resp = self.client.post(url, data, follow=True)
        self.assertEqual(block.bookings.count(), 1)

    def test_adding_existing_booking_to_block(self):
        self.client.login(username=self.superuser.username, password='test')

        user = mommy.make_recipe('booking.user')
        block = mommy.make_recipe('booking.block_5', paid=True, user=user)
        event = mommy.make_recipe(
            'booking.future_PC', event_type=block.block_type.event_type
        )
        booking = mommy.make_recipe(
            'booking.booking', user=user, event=event, paid=False
        )

        url = reverse('admin:booking_block_change', args=[block.id])
        data = {
            'user': user.id,
            'block_type': block.block_type.id,
            'start_date_0': block.start_date.strftime('%d/%m/%Y'),
            'start_date_1': block.start_date.strftime('%H:%M:%S'),
            'paid': block.paid,
            'bookings-TOTAL_FORMS': 1,
            'bookings-INITIAL_FORMS': 0,
            'bookings-0-event': event.id,
            'bookings-0-status': 'OPEN'
        }

        self.assertEqual(block.bookings.count(), 0)
        self.assertIsNone(booking.block)

        resp = self.client.post(url, data, follow=True)
        self.assertEqual(block.bookings.count(), 1)

        booking.refresh_from_db()
        self.assertEqual(booking.block, block)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)

        content = format_content(resp.rendered_content)
        self.assertIn(
            'Booking {} with user {} and event {} already existed and has been '
            'associated with block {}.'.format(
                booking.id, user.username, event, block.id
            ),
            content
        )

    def test_adding_cancelled_booking_to_block(self):
        self.client.login(username=self.superuser.username, password='test')

        user = mommy.make_recipe('booking.user')
        block = mommy.make_recipe('booking.block_5', paid=True, user=user)
        event = mommy.make_recipe(
            'booking.future_PC', event_type=block.block_type.event_type
        )
        booking = mommy.make_recipe(
            'booking.booking', user=user, event=event, paid=False,
            status='CANCELLED'
        )

        url = reverse('admin:booking_block_change', args=[block.id])
        data = {
            'user': user.id,
            'block_type': block.block_type.id,
            'start_date_0': block.start_date.strftime('%d/%m/%Y'),
            'start_date_1': block.start_date.strftime('%H:%M:%S'),
            'paid': block.paid,
            'bookings-TOTAL_FORMS': 1,
            'bookings-INITIAL_FORMS': 0,
            'bookings-0-event': event.id,
            'bookings-0-status': 'OPEN'
        }

        self.assertEqual(block.bookings.count(), 0)
        self.assertIsNone(booking.block)

        resp = self.client.post(url, data, follow=True)
        self.assertEqual(block.bookings.count(), 1)

        booking.refresh_from_db()
        self.assertEqual(booking.block, block)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)
        self.assertEqual(booking.status, 'OPEN')

        content = format_content(resp.rendered_content)
        self.assertIn(
            'Booking {} with user {} and event {} has been reopened and has '
            'been associated with block {}.'.format(
                booking.id, user.username, event, block.id
            ),
            content
        )

    def test_cancelling_booking_on_block(self):
        self.client.login(username=self.superuser.username, password='test')

        user = mommy.make_recipe('booking.user')
        block = mommy.make_recipe('booking.block_5', paid=True, user=user)
        event = mommy.make_recipe(
            'booking.future_PC', event_type=block.block_type.event_type
        )
        booking = mommy.make_recipe(
            'booking.booking', user=user, event=event, block=block,
            status='OPEN'
        )

        url = reverse('admin:booking_block_change', args=[block.id])
        data = {
            'user': user.id,
            'block_type': block.block_type.id,
            'start_date_0': block.start_date.strftime('%d/%m/%Y'),
            'start_date_1': block.start_date.strftime('%H:%M:%S'),
            'paid': block.paid,
            'bookings-TOTAL_FORMS': 1,
            'bookings-INITIAL_FORMS': 1,
            'bookings-0-id': booking.id,
            'bookings-0-event': event.id,
            'bookings-0-status': 'CANCELLED'
        }

        self.assertEqual(block.bookings.count(), 1)
        self.assertEqual(booking.block, block)
        self.assertTrue(booking.paid)

        resp = self.client.post(url, data, follow=True)
        self.assertEqual(block.bookings.count(), 0)

        booking.refresh_from_db()
        self.assertIsNone(booking.block)
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)
        self.assertEqual(booking.status, 'CANCELLED')

        content = format_content(resp.rendered_content)
        self.assertIn(
            'Booking {} with user {} and event {} has been cancelled, set to '
            'unpaid and disassociated from block {}.'.format(
                booking.id, user.username, event, block.id
            ),
            content
        )


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


class EventVoucherAdminTests(TestCase):

    def test_event_types_display(self):
        voucher = mommy.make(EventVoucher)
        event_typepp = mommy.make_recipe(
            'booking.event_type_PP', subtype='Pole class')
        event_typepc = mommy.make_recipe(
            'booking.event_type_PC', subtype='Pole practice'
        )
        voucher.event_types.add(event_typepc)
        voucher.event_types.add(event_typepp)

        voucher_admin = admin.EventVoucherAdmin(EventVoucher, AdminSite())
        voucher_query = voucher_admin.get_queryset(None)[0]

        self.assertEqual(
            voucher_admin.ev_types(voucher_query),
            'Pole class, Pole practice'
        )

    def test_times_used_display(self):
        voucher = mommy.make(EventVoucher)
        users = mommy.make_recipe('booking.user', _quantity=2)
        for user in users:
            UsedEventVoucher.objects.create(voucher=voucher, user=user)

        voucher_admin = admin.EventVoucherAdmin(EventVoucher, AdminSite())
        voucher_query = voucher_admin.get_queryset(None)[0]

        self.assertEqual(
            voucher_admin.times_used(voucher_query), 2
        )


class BlockVoucherAdminTests(TestCase):

    def test_block_types_display(self):
        voucher = mommy.make(BlockVoucher)
        block_type = mommy.make_recipe('booking.blocktype')

        voucher.block_types.add(block_type)

        voucher_admin = admin.BlockVoucherAdmin(BlockVoucher, AdminSite())
        voucher_query = voucher_admin.get_queryset(None)[0]

        self.assertEqual(
            voucher_admin.block_types(voucher_query),
            str(block_type)
        )

    def test_times_used_display(self):
        voucher = mommy.make(BlockVoucher)
        users = mommy.make_recipe('booking.user', _quantity=2)
        for user in users:
            UsedBlockVoucher.objects.create(voucher=voucher, user=user)

        voucher_admin = admin.BlockVoucherAdmin(BlockVoucher, AdminSite())
        voucher_query = voucher_admin.get_queryset(None)[0]

        self.assertEqual(
            voucher_admin.times_used(voucher_query), 2
        )


class TicketBookingAdminTests(TestCase):

    def test_ticket_number_display(self):
        ticket_booking = mommy.make_recipe('booking.ticket_booking')
        mommy.make(Ticket, ticket_booking=ticket_booking, _quantity=3)
        tb_admin = admin.TicketBookingAdmin(TicketBooking, AdminSite())
        tb_query = tb_admin.get_queryset(None)[0]
        self.assertEqual(tb_admin.number_of_tickets(tb_query), 3)


class TicketAdmin(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.ticketed_event = mommy.make_recipe('booking.ticketed_event_max10')
        cls.ticket_booking = mommy.make_recipe(
            'booking.ticket_booking', ticketed_event=cls.ticketed_event,
            user=mommy.make_recipe(
                'booking.user', first_name='Donald', last_name='Duck',
                username='dd'
            )
        )
        mommy.make(Ticket, ticket_booking=cls.ticket_booking)

    def test_ticketed_event_display(self):
        ticket_admin = admin.TicketAdmin(Ticket, AdminSite())
        ticket_query = ticket_admin.get_queryset(None)[0]
        self.assertEqual(
            ticket_admin.ticketed_event(ticket_query), self.ticketed_event
        )

    def test_ticket_booking_ref_display(self):
        ticket_admin = admin.TicketAdmin(Ticket, AdminSite())
        ticket_query = ticket_admin.get_queryset(None)[0]
        self.assertEqual(
            ticket_admin.ticket_booking_ref(ticket_query),
            self.ticket_booking.booking_reference
        )

    def test_user_display(self):
        ticket_admin = admin.TicketAdmin(Ticket, AdminSite())
        ticket_query = ticket_admin.get_queryset(None)[0]
        self.assertEqual(
            ticket_admin.user(ticket_query), 'Donald Duck (dd)'
        )

