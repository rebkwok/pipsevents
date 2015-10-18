from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from django.core.urlresolvers import reverse

from datetime import timedelta, datetime
from mock import patch
from model_mommy import mommy

from booking.models import Event, Booking, BookingError, TicketBooking, \
    Ticket, TicketedEvent, TicketBookingError

now = timezone.now()


class EventTests(TestCase):

    def setUp(self):
        self.event = mommy.make_recipe('booking.future_EV')

    def tearDown(self):
        del self.event

    def test_bookable_with_no_payment_date(self):
        """
        Test that event bookable logic returns correctly
        """
        event = mommy.make_recipe('booking.future_EV')
        self.assertTrue(event.bookable())

    @patch('booking.models.timezone')
    def test_bookable_with_payment_dates(self, mock_tz):
        """
        Test that event bookable logic returns correctly for events with
        payment due dates
        """
        mock_tz.now.return_value = datetime(2015, 2, 1, tzinfo=timezone.utc)
        event = mommy.make_recipe(
            'booking.future_EV',
            cost=10,
            payment_due_date=datetime(2015, 2, 2, tzinfo=timezone.utc))

        self.assertTrue(event.bookable())

        event1 = mommy.make_recipe(
            'booking.future_EV',
            cost=10,
            payment_due_date=datetime(2015, 1, 31, tzinfo=timezone.utc)
        )
        self.assertFalse(event1.bookable())


    def test_event_pre_save(self):
        """
        Test that an event with no cost has correct fields set
        """
        # if an event is created with 0 cost, the following fields are set to
        # False/None/""
        # advance_payment_required, payment_open, payment_due_date

        poleclass = mommy.make_recipe('booking.future_PC', cost=7)

        #change cost to 0
        poleclass.cost = 0
        poleclass.save()

        # event with cost, check other fields are left as is
        workshop = mommy.make_recipe('booking.future_WS',
                                     cost=10,
                                     payment_open=True,
                                     payment_info="Pay me")
        self.assertEquals(workshop.payment_open, True)
        self.assertEquals(workshop.payment_info, "Pay me")

    def test_absolute_url(self):
        self.assertEqual(
            self.event.get_absolute_url(),
            reverse('booking:event_detail', kwargs={'slug': self.event.slug})
        )

    def test_str(self):
        event = mommy.make_recipe(
            'booking.past_event',
            name='Test event',
            date=datetime(2015, 1, 1, tzinfo=timezone.utc)
        )
        self.assertEqual(str(event), 'Test event - 01 Jan 2015, 00:00')


class BookingTests(TestCase):

    def setUp(self):
        mommy.make_recipe('booking.user', _quantity=15)
        self.users = User.objects.all()
        self.event = mommy.make_recipe('booking.future_EV', max_participants=20)
        self.event_with_cost = mommy.make_recipe('booking.future_EV',
                                                 advance_payment_required=True,
                                                 cost=10)

    def tearDown(self):
        del self.users
        del self.event

    def test_event_spaces_left(self):
        """
        Test that spaces left is calculated correctly
        """

        self.assertEqual(self.event.max_participants, 20)
        self.assertEqual(self.event.spaces_left(), 20)

        for user in self.users:
            mommy.make_recipe('booking.booking', user=user, event=self.event)

        self.assertEqual(self.event.spaces_left(), 5)

    def test_space_confirmed_no_cost(self):
        """
        Test that a booking for an event with no cost is automatically confirmed
        """

        booking = mommy.make_recipe('booking.booking',
                                    user=self.users[0], event=self.event)
        self.assertTrue(booking.space_confirmed())

    def test_confirm_space(self):
        """
        Test confirm_space method on a booking
        """

        booking = mommy.make_recipe('booking.booking',
                                    user=self.users[0],
                                    event=self.event_with_cost)
        self.assertFalse(booking.space_confirmed())
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)

        booking.confirm_space()
        self.assertTrue(booking.space_confirmed())
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)

    def test_space_confirmed_advance_payment_req(self):
        """
        Test space confirmed requires manual confirmation for events with
        advance payments required
        """
        event = self.event_with_cost
        booking = mommy.make_recipe('booking.booking',
                                    user=self.users[0],
                                    event=event)
        self.assertFalse(booking.space_confirmed())

        booking.confirm_space()
        self.assertTrue(booking.space_confirmed())

    def test_space_confirmed_advance_payment_not_required(self):
        """
        Test space confirmed automatically for events with advance payments
        not required
        """
        event = self.event_with_cost
        event.advance_payment_required = False

        booking = mommy.make_recipe('booking.booking',
                                    user=self.users[0],
                                    event=event)
        self.assertTrue(booking.space_confirmed())

    def test_date_payment_confirmed(self):
        """
        Test autopopulating date payment confirmed.
        """
        booking = mommy.make_recipe('booking.booking',
                                    user=self.users[0],
                                    event=self.event_with_cost)
        # booking is created with no payment confirmed date
        self.assertFalse(booking.date_payment_confirmed)

        booking.payment_confirmed = True
        booking.save()
        self.assertTrue(booking.date_payment_confirmed)

    def test_cancelled_booking_is_no_longer_confirmed(self):
        booking = mommy.make_recipe('booking.booking',
                                    user=self.users[0],
                                    event=self.event_with_cost)
        booking.confirm_space()
        self.assertTrue(booking.space_confirmed())

        booking.status = 'CANCELLED'
        booking.save()
        self.assertFalse(booking.space_confirmed())

    def test_free_class_is_set_to_paid(self):
        booking = mommy.make_recipe('booking.booking',
                                    user=self.users[0],
                                    event=self.event_with_cost,
                                    free_class=True)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)
        self.assertTrue(booking.space_confirmed())

    def test_str(self):
        booking = mommy.make_recipe(
            'booking.booking',
            event=mommy.make_recipe('booking.future_EV', name='Test event'),
            user=mommy.make_recipe('booking.user', username='Test user'),
            )
        self.assertEqual(str(booking), 'Test event - Test user')

    def test_booking_full_event(self):
        """
        Test that attempting to create new booking for full event raises
        BookingError
        """
        self.event_with_cost.max_participants = 3
        self.event_with_cost.save()
        mommy.make_recipe(
            'booking.booking', event=self.event_with_cost, _quantity=3
        )
        with self.assertRaises(BookingError):
            Booking.objects.create(
                event=self.event_with_cost, user=self.users[0]
            )

    def test_reopening_booking_full_event(self):
        """
        Test that attempting to reopen a cancelled booking for now full event
        raises BookingError
        """
        self.event_with_cost.max_participants = 3
        self.event_with_cost.save()
        user = self.users[0]
        booking = mommy.make_recipe(
            'booking.booking', event=self.event_with_cost, user=user,
            status='CANCELLED'
        )
        mommy.make_recipe(
            'booking.booking', event=self.event_with_cost, _quantity=3
        )
        with self.assertRaises(BookingError):
            booking.status = 'OPEN'
            booking.save()

    def test_can_create_cancelled_booking_for_full_event(self):
        """
        Test that attempting to create new cancelled booking for full event
        does not raise error
        """
        self.event_with_cost.max_participants = 3
        self.event_with_cost.save()
        mommy.make_recipe(
            'booking.booking', event=self.event_with_cost, _quantity=3
        )
        Booking.objects.create(
            event=self.event_with_cost, user=self.users[0], status='CANCELLED'
        )
        self.assertEqual(
            Booking.objects.filter(event=self.event_with_cost).count(), 4
        )

    @patch('booking.models.timezone')
    def test_reopening_booking_sets_date_reopened(self, mock_tz):
        """
        Test that reopening a cancelled booking for an event with spaces sets
        the rebooking date
        """
        mock_now = datetime(2015, 1, 1, tzinfo=timezone.utc)
        mock_tz.now.return_value = mock_now
        user = self.users[0]
        booking = mommy.make_recipe(
            'booking.booking', event=self.event_with_cost, user=user,
            status='CANCELLED'
        )

        self.assertIsNone(booking.date_rebooked)
        booking.status = 'OPEN'
        booking.save()
        booking.refresh_from_db()
        self.assertEqual(booking.date_rebooked, mock_now)


    @patch('booking.models.timezone')
    def test_reopening_booking_again_resets_date_reopened(self, mock_tz):
        """
        Test that reopening a second time resets the rebooking date
        """
        mock_now = datetime(2015, 3, 1, tzinfo=timezone.utc)
        mock_tz.now.return_value = mock_now
        user = self.users[0]
        booking = mommy.make_recipe(
            'booking.booking', event=self.event_with_cost, user=user,
            status='CANCELLED',
            date_rebooked=datetime(2015, 1, 1, tzinfo=timezone.utc)
        )
        self.assertEqual(
            booking.date_rebooked, datetime(2015, 1, 1, tzinfo=timezone.utc)
        )
        booking.status = 'OPEN'
        booking.save()
        booking.refresh_from_db()
        self.assertEqual(booking.date_rebooked, mock_now)

    def test_reopening_booking_full_event_does_not_set_date_reopened(self):
        """
        Test that attempting to reopen a cancelled booking for now full event
        raises BookingError and does not set date_reopened
        """
        self.event_with_cost.max_participants = 3
        self.event_with_cost.save()
        user = self.users[0]
        booking = mommy.make_recipe(
            'booking.booking', event=self.event_with_cost, user=user,
            status='CANCELLED'
        )
        mommy.make_recipe(
            'booking.booking', event=self.event_with_cost, _quantity=3
        )
        with self.assertRaises(BookingError):
            booking.status = 'OPEN'
            booking.save()

        booking.refresh_from_db()
        self.assertIsNone(booking.date_rebooked)


class BlockTests(TestCase):

    def setUp(self):
        # note for purposes of testing, start_date is set to 1.1.15
        self.small_block = mommy.make_recipe('booking.block_5')
        self.large_block = mommy.make_recipe('booking.block_10')

        mommy.make_recipe('booking.future_PC', _quantity=10)

    def tearDown(self):
        del self.small_block
        del self.large_block

    def test_block_not_expiry_date(self):
        """
        Test that block expiry dates are populated correctly
        """
        dt = datetime(2015, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(self.small_block.start_date, dt)
        self.assertEqual(self.small_block.expiry_date,
                         datetime(2015, 3, 1, 23, 59, 59, tzinfo=timezone.utc))
        self.assertEqual(self.large_block.expiry_date,
                 datetime(2015, 5, 1, 23, 59, 59, tzinfo=timezone.utc))

    @patch.object(timezone, 'now',
                  return_value=datetime(2015, 2, 1, tzinfo=timezone.utc))
    def test_active_small_block(self, mock_now):
        """
        Test that a 5 class unexpired block returns active correctly
        """
        # self.small_block has not expired, block isn't full, payment not
        # confirmed
        self.assertFalse(self.small_block.active_block())
        # set paid
        self.small_block.paid=True
        self.assertTrue(self.small_block.active_block())

    @patch.object(timezone, 'now',
                  return_value=datetime(2015, 3, 2, tzinfo=timezone.utc))
    def test_active_large_block(self, mock_now):
        """
        Test that a 10 class unexpired block returns active correctly
        """

        # self.large_block has not expired, block isn't full,
        # payment not confirmed
        self.assertFalse(self.large_block.active_block())
        # set paid
        self.large_block.paid = True
        self.assertTrue(self.large_block.active_block())

        # but self.small_block has expired, not active even if paid
        self.small_block.paid = True
        self.assertFalse(self.small_block.active_block())

    @patch.object(timezone, 'now',
                  return_value=datetime(2015, 2, 1, tzinfo=timezone.utc))
    def test_active_full_blocks(self, mock_now):
        """
        Test that active is set to False if a block is full
        """

        # Neither self.small_block or self.large_block have expired
        # both paid
        self.small_block.paid = True
        self.large_block.paid = True
        # no bookings against either, active_block = True
        self.assertEquals(Booking.objects.filter(
            block__id=self.small_block.id).count(), 0)
        self.assertEquals(Booking.objects.filter(
            block__id=self.large_block.id).count(), 0)
        self.assertTrue(self.small_block.active_block())
        self.assertTrue(self.large_block.active_block())

        # make some bookings against the blocks
        poleclasses = Event.objects.all()
        poleclasses5 = poleclasses[0:5]
        for pc in poleclasses5:
            mommy.make_recipe(
                'booking.booking',
                user=self.small_block.user,
                block=self.small_block,
                event=pc
            )
            mommy.make_recipe(
                'booking.booking',
                user=self.large_block.user,
                block=self.large_block,
                event=pc
            )

        # small block is now full, large block isn't
        self.assertFalse(self.small_block.active_block())
        self.assertTrue(self.large_block.active_block())

        # fill up the large block
        poleclasses10 = poleclasses[5:]
        for pc in poleclasses10:
            mommy.make_recipe(
                'booking.booking',
                user=self.large_block.user,
                block=self.large_block,
                event=pc
            )
        self.assertFalse(self.large_block.active_block())

    def test_unpaid_block_is_not_active(self):
        self.small_block.paid = False
        self.assertFalse(self.small_block.active_block())

    def test_block_pre_delete(self):
        """
        Test that bookings are reset to unpaid when a block is deleted
        """

        events = mommy.make_recipe('booking.future_EV', cost=10, _quantity=5)
        block_bookings = [mommy.make_recipe(
            'booking.booking',
            block=self.large_block,
            user=self.large_block.user,
            paid=True,
            payment_confirmed=True,
            event=event
            ) for event in events]
        self.assertEqual(Booking.objects.filter(paid=True).count(), 5)
        self.large_block.delete()
        self.assertEqual(Booking.objects.filter(paid=True).count(), 0)

        for booking in Booking.objects.all():
            self.assertIsNone(booking.block)
            self.assertFalse(booking.paid)
            self.assertFalse(booking.payment_confirmed)

    def test_str(self):
        blocktype = mommy.make_recipe('booking.blocktype', size=4,
            event_type__subtype="Pole level class"
        )
        block = mommy.make_recipe(
            'booking.block',
            start_date=datetime(2015, 1, 1, tzinfo=timezone.utc),
            user=mommy.make_recipe('booking.user', username="TestUser"),
            block_type=blocktype,
        )

        self.assertEqual(
            str(block), 'TestUser -- Pole level class -- size 4 -- start 01 Jan 2015'
        )


class EventTypeTests(TestCase):

    def test_str_class(self):
        evtype = mommy.make_recipe('booking.event_type_PC', subtype="class subtype")
        self.assertEqual(str(evtype), 'Class - class subtype')

    def test_str_event(self):
        evtype = mommy.make_recipe('booking.event_type_OE', subtype="event subtype")
        self.assertEqual(str(evtype), 'Event - event subtype')


class TicketedEventTests(TestCase):

    def setUp(self):
        self.ticketed_event = mommy.make_recipe('booking.ticketed_event_max10')

    def tearDown(self):
        del self.ticketed_event

    def test_bookable(self):
        """
        Test that event bookable logic returns correctly
        """
        self.assertTrue(self.ticketed_event.bookable())
        # if we make 10 bookings on this event, it should no longer be bookable
        ticket_booking = mommy.make(
            TicketBooking, ticketed_event=self.ticketed_event
        )
        mommy.make(
            Ticket,
            ticket_booking__ticketed_event=self.ticketed_event, _quantity=10
        )
        self.assertFalse(self.ticketed_event.bookable())

    def test_payment_fields_set_on_save(self):
        """
        Test that an event with no cost has correct fields set
        """
        # if an event is created with 0 cost, the following fields are set to
        # False/None/""
        # advance_payment_required, payment_open, payment_due_date

        self.assertTrue(self.ticketed_event.advance_payment_required)
        self.assertTrue(self.ticketed_event.payment_open)
        self.assertTrue(self.ticketed_event.ticket_cost > 0)
        #change cost to 0
        self.ticketed_event.ticket_cost = 0
        self.ticketed_event.save()
        self.assertFalse(self.ticketed_event.advance_payment_required)
        self.assertFalse(self.ticketed_event.payment_open)

    def test_payment_due_date_set_on_save(self):
        """
        Test that an event payment due date is set to the end of the selected
        day
        """
        self.ticketed_event.payment_due_date = datetime(
            2015, 1, 1, 13, 30, tzinfo=timezone.utc
        )
        self.ticketed_event.save()
        self.assertEqual(
            self.ticketed_event.payment_due_date, datetime(
            2015, 1, 1, 23, 59, 59, 0, tzinfo=timezone.utc
        )
        )

    # def test_absolute_url(self):
    #     self.assertEqual(
    #         self.event.get_absolute_url(),
    #         reverse('booking:ticketed_event_detail', kwargs={'slug': self.event.slug})
    #     )

    def test_str(self):
        ticketed_event = mommy.make_recipe(
            'booking.ticketed_event_max10',
            name='Test event',
            date=datetime(2015, 1, 1, tzinfo=timezone.utc)
        )
        self.assertEqual(str(ticketed_event), 'Test event - 01 Jan 2015, 00:00')


class TicketBookingTests(TestCase):

    def setUp(self):
        self.ticketed_event = mommy.make_recipe('booking.ticketed_event_max10')

    def tearDown(self):
        del self.ticketed_event

    def test_event_tickets_left(self):
        """
        Test that tickets left is calculated correctly
        """

        self.assertEqual(self.ticketed_event.max_tickets, 10)
        self.assertEqual(self.ticketed_event.tickets_left(), 10)

        mommy.make(
            Ticket,
            ticket_booking__ticketed_event=self.ticketed_event, _quantity=5
        )
        self.assertEqual(self.ticketed_event.tickets_left(), 5)

    def test_event_tickets_left_does_not_count_cancelled(self):
        self.assertEqual(self.ticketed_event.max_tickets, 10)
        self.assertEqual(self.ticketed_event.tickets_left(), 10)

        open_booking = mommy.make(
            TicketBooking, ticketed_event=self.ticketed_event, cancelled=False
        )
        mommy.make(
            Ticket, ticket_booking=open_booking, _quantity=5
        )
        self.assertEqual(self.ticketed_event.tickets_left(), 5)

        # cancelled booking deletes the tickets
        cancelled_booking = mommy.make(
            TicketBooking, ticketed_event=self.ticketed_event, cancelled=False
        )
        mommy.make(
            Ticket, ticket_booking=cancelled_booking, _quantity=5
        )
        event_tickets = Ticket.objects.filter(
            ticket_booking__ticketed_event=self.ticketed_event
        )
        self.assertEqual(event_tickets.count(), 10)
        self.assertEqual(self.ticketed_event.tickets_left(), 0)
        cancelled_booking.cancelled = True
        cancelled_booking.save()

        event_tickets = Ticket.objects.filter(
            ticket_booking__ticketed_event=self.ticketed_event
        )
        self.assertEqual(event_tickets.count(), 5)
        self.assertEqual(self.ticketed_event.tickets_left(), 5)


    def test_date_payment_confirmed(self):
        """
        Test autopopulating date payment confirmed.
        """
        booking = mommy.make(TicketBooking, ticketed_event=self.ticketed_event)
        # booking is created with no payment confirmed date
        self.assertFalse(booking.date_payment_confirmed)

        booking.payment_confirmed = True
        booking.save()
        self.assertTrue(booking.date_payment_confirmed)

    def test_cannot_cancel_paid_booking(self):
        booking = mommy.make(
            TicketBooking, ticketed_event=self.ticketed_event, paid=True
        )
        booking.cancelled = True
        with self.assertRaises(TicketBookingError):
            booking.save()


    def test_str(self):
        booking = mommy.make(
            TicketBooking,
            ticketed_event=mommy.make_recipe(
                'booking.ticketed_event_max10', name='Test event'
            ),
            user=mommy.make_recipe('booking.user', username='Test user'),
            )
        self.assertEqual(
            str(booking), 'Booking ref {} - Test event - Test user'.format(
                booking.booking_reference
            )
        )

    def test_booking_full_event(self):
        """
        Test that attempting to create new ticket booking for full event raises
        TicketBookingError
        """
        booking = mommy.make(TicketBooking, ticketed_event=self.ticketed_event)
        mommy.make(Ticket, ticket_booking=booking, _quantity=10)

        self.assertEqual(self.ticketed_event.tickets_left(), 0)
        with self.assertRaises(TicketBookingError):
            TicketBooking.objects.create(
                ticketed_event=self.ticketed_event,
                user=mommy.make_recipe('booking.user')
            )

    def test_cannot_reopen_booking_full_event(self):
        """
        Test that attempting to create new ticket booking for full event raises
        TicketBookingError
        """
        # make booking with some tickets and cancel it
        booking = mommy.make(TicketBooking, ticketed_event=self.ticketed_event)
        mommy.make(Ticket, ticket_booking=booking, _quantity=5)
        booking.cancelled = True
        booking.save()

        # make another booking with as many tickets as the max
        new_booking = mommy.make(TicketBooking, ticketed_event=self.ticketed_event)
        mommy.make(Ticket, ticket_booking=new_booking, _quantity=10)
        self.assertEqual(self.ticketed_event.tickets_left(), 0)

        # try to reopen the cancelled booking
        booking.cancelled = False
        with self.assertRaises(TicketBookingError):
            booking.save()

    @patch('booking.models.timezone')
    def test_reopening_booking_sets_reopen_date(self, mock_tz):
        mock_now = datetime(2015, 1, 1, tzinfo=timezone.utc)
        mock_tz.now.return_value = mock_now
        booking = mommy.make(TicketBooking, ticketed_event=self.ticketed_event)
        self.assertIsNone(booking.date_rebooked)
        booking.cancelled = True
        booking.save()
        booking.cancelled = False
        booking.save()
        self.assertEqual(booking.date_rebooked, mock_now)

    def test_failed_reopening_does_not_set_reopened_date(self):
        booking = mommy.make(TicketBooking, ticketed_event=self.ticketed_event)
        self.assertIsNone(booking.date_rebooked)
        booking.cancelled = True
        booking.save()
        mommy.make(
            Ticket, ticket_booking__ticketed_event=self.ticketed_event,
            _quantity=10
           )
        booking.cancelled = False
        try:
            booking.save()
        except TicketBookingError:
            pass
        self.assertIsNone(booking.date_rebooked)


class TicketTests(TestCase):

    def test_cannot_create_ticket_for_full_event(self):
        ticketed_event = mommy.make_recipe('booking.ticketed_event_max10')
        booking = mommy.make(TicketBooking, ticketed_event=ticketed_event)
        mommy.make(Ticket, ticket_booking=booking, _quantity=10)
        self.assertEqual(ticketed_event.tickets_left(), 0)

        with self.assertRaises(TicketBookingError):
            Ticket.objects.create(ticket_booking=booking)

