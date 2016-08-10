# -*- coding: utf-8 -*-
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from django.core.urlresolvers import reverse

from datetime import timedelta, datetime
from mock import patch
from model_mommy import mommy

from booking.models import Event, EventType, Block, BlockType, BlockTypeError, \
    Booking, TicketBooking, Ticket, TicketBookingError, BlockVoucher, \
    EventVoucher, UsedBlockVoucher, UsedEventVoucher

now = timezone.now()


class EventTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.event = mommy.make_recipe('booking.future_EV')

    def test_bookable_booking_not_open(self):
        """
        Test that event bookable logic returns correctly
        """
        event = mommy.make_recipe('booking.future_EV', booking_open=False)
        self.assertFalse(event.bookable)

    def test_bookable_with_no_payment_date(self):
        """
        Test that event bookable logic returns correctly
        """
        event = mommy.make_recipe('booking.future_EV')
        self.assertTrue(event.bookable)

    def test_bookable_spaces(self):
        event = mommy.make_recipe('booking.future_EV', max_participants=2)
        self.assertTrue(event.bookable)

        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        # need to get event again as bookable is cached property
        event = Event.objects.get(id=event.id)
        self.assertFalse(event.bookable)

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

        self.assertTrue(event.bookable)

        # bookable even if payment due date has passed
        event1 = mommy.make_recipe(
            'booking.future_EV',
            cost=10,
            payment_due_date=datetime(2015, 1, 31, tzinfo=timezone.utc)
        )
        self.assertTrue(event1.bookable)

    def test_event_pre_save_event_with_no_cost(self):
        """
        Test that an event with no cost has correct fields set
        """
        # if an event is created with 0 cost, the following fields are set to
        # False/None/""
        # advance_payment_required, payment_open, payment_due_date,
        # payment_time_allowed

        poleclass = mommy.make_recipe(
            'booking.future_PC', cost=7, payment_open=True,
            advance_payment_required=True,
            payment_time_allowed=4,
            payment_due_date=timezone.now() + timedelta(hours=1))

        #change cost to 0
        poleclass.cost = 0
        poleclass.save()

        self.assertFalse(poleclass.payment_open)
        self.assertFalse(poleclass.advance_payment_required)
        self.assertIsNone(poleclass.payment_time_allowed)
        self.assertIsNone(poleclass.payment_due_date)

        # event with cost, check other fields are left as is
        workshop = mommy.make_recipe('booking.future_WS',
                                     cost=10,
                                     payment_open=True,
                                     payment_info="Pay me")
        self.assertEquals(workshop.payment_open, True)
        self.assertEquals(workshop.payment_info, "Pay me")

    def test_pre_save_external_instructor(self):
        pc = mommy.make_recipe(
            'booking.future_PC', external_instructor=True
        )
        self.assertFalse(pc.booking_open)
        self.assertFalse(pc.payment_open)
        # we can't make these fields true
        pc.booking_open = True
        pc.payment_open = True
        pc.save()
        self.assertFalse(pc.booking_open)
        self.assertFalse(pc.payment_open)

    def test_pre_save_payment_time_allowed(self):
        """
        payment_time_allowed automatically makes advance_payment_required true
        """
        pc = mommy.make_recipe(
            'booking.future_PC', cost=10, advance_payment_required=False
        )
        self.assertFalse(pc.advance_payment_required)

        pc.payment_time_allowed = 4
        pc.save()
        self.assertTrue(pc.advance_payment_required)

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

    @classmethod
    def setUpTestData(cls):
        cls.event = mommy.make_recipe('booking.future_EV', max_participants=20)
        cls.subscribed = mommy.make(Group, name='subscribed')

    def setUp(self):
        mommy.make_recipe('booking.user', _quantity=15)
        self.users = User.objects.all()
        self.event_with_cost = mommy.make_recipe('booking.future_EV',
                                                 advance_payment_required=True,
                                                 cost=10)

    def test_event_spaces_left(self):
        """
        Test that spaces left is calculated correctly
        """

        self.assertEqual(self.event.max_participants, 20)
        self.assertEqual(self.event.spaces_left, 20)

        for user in self.users:
            mommy.make_recipe('booking.booking', user=user, event=self.event)

        # we need to get the event again as spaces_left is cached property
        event = Event.objects.get(id=self.event.id)
        self.assertEqual(event.spaces_left, 5)

    def test_event_spaces_left_does_not_count_cancelled_or_no_shows(self):
        """
        Test that spaces left is calculated correctly
        """

        self.assertEqual(self.event.max_participants, 20)
        self.assertEqual(self.event.spaces_left, 20)

        for user in self.users:
            mommy.make_recipe('booking.booking', user=user, event=self.event)
        mommy.make_recipe(
            'booking.booking', event=self.event, no_show=True
        )
        mommy.make_recipe(
            'booking.booking', event=self.event, status='CANCELLED'
        )
        # 20 total spaces, 15 open bookings, 1 cancelled, 1 no-show; still 5
        # spaces left
        # we need to get the event again as spaces_left is cached property
        event = Event.objects.get(id=self.event.id)
        self.assertEqual(event.bookings.count(), 17)
        self.assertEqual(event.spaces_left, 5)

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

        booking = mommy.make_recipe('booking.booking',
                                    user=self.users[0],
                                    event=self.event_with_cost)
        self.assertFalse(booking.space_confirmed())

        booking.confirm_space()
        self.assertTrue(booking.space_confirmed())

    def test_space_confirmed_advance_payment_not_required(self):
        """
        Test space confirmed automatically for events with advance payments
        not required
        """
        self.event_with_cost.advance_payment_required = False
        self.event_with_cost.save()

        booking = mommy.make_recipe('booking.booking',
                                    user=self.users[0],
                                    event=self.event_with_cost)
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
        ValidationError
        """
        self.event_with_cost.max_participants = 3
        self.event_with_cost.save()
        mommy.make_recipe(
            'booking.booking', event=self.event_with_cost, _quantity=3
        )
        # we need to get the event again as spaces_left is cached property
        event = Event.objects.get(id=self.event_with_cost.id)
        with self.assertRaises(ValidationError):
            Booking.objects.create(
                event=event, user=self.users[0]
            )

    def test_reopening_booking_full_event(self):
        """
        Test that attempting to reopen a cancelled booking for now full event
        raises ValidationError
        """
        self.event_with_cost.max_participants = 3
        self.event_with_cost.save()
        user = self.users[0]
        mommy.make_recipe(
            'booking.booking', event=self.event_with_cost, _quantity=3
        )
        event = Event.objects.get(id=self.event_with_cost.id)
        booking = mommy.make_recipe(
            'booking.booking', event=event, user=user, status='CANCELLED'
        )
        with self.assertRaises(ValidationError):
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
        raises ValidationError and does not set date_reopened
        """
        self.event_with_cost.max_participants = 3
        self.event_with_cost.save()
        user = self.users[0]
        mommy.make_recipe(
            'booking.booking', event=self.event_with_cost, _quantity=3
        )
        event = Event.objects.get(id=self.event_with_cost.id)
        booking = mommy.make_recipe(
            'booking.booking', event=event, user=user, status='CANCELLED'
        )
        with self.assertRaises(ValidationError):
            booking.status = 'OPEN'
            booking.save()

        booking.refresh_from_db()
        self.assertIsNone(booking.date_rebooked)

    def test_user_added_to_mailing_list_when_booking_first_CL(self):
        user = mommy.make_recipe('booking.user')
        self.assertNotIn(self.subscribed, user.groups.all())
        mommy.make(Booking, user=user, event__event_type__event_type='CL')
        self.assertIn(self.subscribed, user.groups.all())

    def test_unsubscribed_user_with_past_CL_not_added_to_mailing_list(self):
        user = mommy.make_recipe('booking.user')
        mommy.make(Booking, user=user, event__event_type__event_type='CL')
        self.assertIn(self.subscribed, user.groups.all())

        self.subscribed.user_set.remove(user)
        self.assertNotIn(self.subscribed, user.groups.all())

        mommy.make(Booking, user=user, event__event_type__event_type='CL')
        self.assertEqual(Booking.objects.filter(user=user).count(), 2)
        self.assertNotIn(self.subscribed, user.groups.all())

    def test_user_not_added_to_mailing_list_when_booking_non_CL(self):
        user = mommy.make_recipe('booking.user')
        self.assertNotIn(self.subscribed, user.groups.all())
        mommy.make(Booking, user=user, event__event_type__event_type='EV')
        self.assertNotIn(self.subscribed, user.groups.all())
        self.assertTrue(Booking.objects.filter(user=user).exists())

        mommy.make(Booking, user=user, event__event_type__event_type='CL')
        self.assertIn(self.subscribed, user.groups.all())


class BlockTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        mommy.make_recipe('booking.future_PC', _quantity=10)

    def setUp(self):
        # note for purposes of testing, start_date is set to 1.1.15
        self.small_block = mommy.make_recipe('booking.block_5')
        self.large_block = mommy.make_recipe('booking.block_10')

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
            str(block), 'TestUser -- Pole level class -- size 4 -- '
                        'start 01 Jan 2015'
        )

    def test_str_for_transfer_block(self):
        blocktype1 = mommy.make_recipe(
            'booking.blocktype', size=1, duration=1, identifier='transferred',
            event_type__subtype="Pole level class"
        )
        block1 = mommy.make_recipe(
            'booking.block',
            start_date=datetime(2015, 1, 1, tzinfo=timezone.utc),
            user=mommy.make_recipe('booking.user', username="TestUser1"),
            block_type=blocktype1,
        )

        self.assertEqual(
            str(block1), 'TestUser1 -- Pole level class (transferred) -- '
                         'size 1 -- start 01 Jan 2015'
        )

    def test_str_for_free_class_block(self):
        blocktype = mommy.make_recipe('booking.blocktype', size=1, cost=0,
            event_type__subtype="Pole level class", identifier='free class'
        )
        block = mommy.make_recipe(
            'booking.block',
            start_date=datetime(2015, 1, 1, tzinfo=timezone.utc),
            user=mommy.make_recipe('booking.user', username="TestUser"),
            block_type=blocktype,
        )

        self.assertEqual(
            str(block), 'TestUser -- Pole level class (free class) '
                        '-- size 1 -- start 01 Jan 2015'
        )

    def test_create_free_class_block_with_parent(self):
        """
        Free block has duration 1; if it has a parent block, override
        start date and duration with parent data
        """
        ev_type = mommy.make(
            EventType, event_type='CL', subtype="Pole level class"
        )
        blocktype = mommy.make_recipe(
            'booking.blocktype', size=10, cost=60, duration=4,
            event_type=ev_type, identifier='standard'
        )
        free_blocktype = mommy.make_recipe(
            'booking.blocktype', size=1, cost=0, duration=1,
            event_type=ev_type, identifier='free class'
        )
        user = mommy.make_recipe('booking.user', username="TestUser")
        block = mommy.make_recipe(
            'booking.block',
            start_date=datetime(2015, 1, 1, tzinfo=timezone.utc),
            user=user,
            block_type=blocktype,
        )
        free_block = mommy.make_recipe(
            'booking.block', parent=block,
            user=user,
            block_type=free_blocktype,
        )
        self.assertEqual(free_block.start_date, block.start_date)
        self.assertEqual(free_block.expiry_date, block.expiry_date)

    def test_create_free_class_block_without_parent(self):
        """
        Free block has duration 1; if no parent block keep start date and
        duration from free block type
        """
        free_blocktype = mommy.make_recipe(
            'booking.blocktype', size=1, cost=0,
            event_type__subtype="Pole level class", identifier='free class',
            duration=1
        )
        user = mommy.make_recipe('booking.user', username="TestUser")

        free_block = mommy.make_recipe(
            'booking.block', user=user, block_type=free_blocktype,
            start_date=datetime(2015, 1, 1, tzinfo=timezone.utc)
        )

        self.assertEqual(
            free_block.expiry_date,
            datetime(2015, 2, 1, 23, 59, 59, tzinfo=timezone.utc)
        )

    def test_booking_last_in_10_class_block_creates_free_block(self):
        """
        Creating a new booking that uses the last of 10 pole level class
        blocks automatically creates a free class block with the original
        block as its parent
        """
        self.assertEqual(Block.objects.count(), 2)

        ev_type = mommy.make(
            EventType, event_type='CL', subtype="Pole level class"
        )
        mommy.make_recipe('booking.blocktype', size=1, cost=0,
            event_type=ev_type, identifier='free class'
        )
        blocktype = mommy.make_recipe(
            'booking.blocktype', size=10, cost=60, duration=4,
            event_type=ev_type, identifier='standard'
        )
        block = mommy.make_recipe(
            'booking.block',
            user=mommy.make_recipe('booking.user', username="TestUser"),
            block_type=blocktype, paid=True
        )
        self.assertTrue(block.active_block())
        mommy.make_recipe(
            'booking.booking', user=block.user, block=block, _quantity=9
        )
        self.assertEqual(Booking.objects.count(), 9)
        self.assertEqual(block.bookings.count(), 9)
        self.assertEqual(Block.objects.count(), 3)

        mommy.make_recipe('booking.booking', user=block.user, block=block)
        self.assertEqual(block.bookings.count(), 10)
        self.assertEqual(Block.objects.count(), 4)
        self.assertTrue(block.children.exists())

    def test_booking_last_on_expired_10_class_block_does_not_create_free(self):
        """
        Test that if a booking is made on an expired block, no free class is
        created.  This shouldn't happen because cancelling bookings removes
        the block, and if you try to reopen after block has expired, you won't
        have the option to use the expired block.  However, it could happen if
        a superuser creates a booking on an expired block in the admin - don't
        want this to automatically create free class blocks that can't be
        used (expiry dates are set to same as parent block)
        """
        self.assertEqual(Block.objects.count(), 2)

        ev_type = mommy.make(
            EventType, event_type='CL', subtype="Pole level class"
        )
        mommy.make_recipe('booking.blocktype', size=1, cost=0,
            event_type=ev_type, identifier='free class'
        )
        blocktype = mommy.make_recipe(
            'booking.blocktype', size=10, cost=60, duration=4,
            event_type=ev_type, identifier='standard'
        )
        # make an expired block
        block = mommy.make_recipe(
            'booking.block',
            start_date=datetime(2015, 1, 1, tzinfo=timezone.utc),
            user=mommy.make_recipe('booking.user', username="TestUser"),
            block_type=blocktype, paid=True
        )
        self.assertTrue(block.expired)
        mommy.make_recipe(
            'booking.booking', user=block.user, block=block, _quantity=9
        )
        self.assertEqual(Booking.objects.count(), 9)
        self.assertEqual(block.bookings.count(), 9)
        self.assertEqual(Block.objects.count(), 3)

        mommy.make_recipe('booking.booking', user=block.user, block=block)
        # last space in block filled but no free class block created
        self.assertEqual(block.bookings.count(), 10)
        self.assertEqual(Block.objects.count(), 3)
        self.assertFalse(block.children.exists())

    def test_cancelling_booking_from_full_block_with_free_block(self):
        """
        Cancelling a booking on a block that has an associated free class
        deletes the free class block if it's unused and moves the free class
        to the original block if it has been used
        """
        self.assertEqual(Block.objects.count(), 2)

        ev_type = mommy.make(
            EventType, event_type='CL', subtype="Pole level class"
        )
        mommy.make_recipe('booking.blocktype', size=1, cost=0,
            event_type=ev_type, identifier='free class'
        )
        blocktype = mommy.make_recipe(
            'booking.blocktype', size=10, cost=60, duration=4,
            event_type=ev_type, identifier='standard'
        )
        block = mommy.make_recipe(
            'booking.block',
            user=mommy.make_recipe('booking.user', username="TestUser"),
            block_type=blocktype, paid=True
        )
        self.assertTrue(block.active_block())
        # fill block, which will create a free class block
        mommy.make_recipe(
            'booking.booking', user=block.user, block=block, _quantity=10
        )
        self.assertEqual(block.bookings.count(), 10)
        self.assertTrue(block.children.exists())
        self.assertEqual(block.children.count(), 1)

        # cancel a booking from the block
        booking = block.bookings.first()
        booking.status = 'CANCELLED'
        booking.save()

        # free block class has been deleted
        self.assertEqual(block.bookings.count(), 9)
        self.assertFalse(block.children.exists())

        # fill block again
        mommy.make_recipe('booking.booking', user=block.user, block=block)
        self.assertEqual(block.bookings.count(), 10)
        self.assertTrue(block.children.exists())
        self.assertEqual(block.children.count(), 1)

        # use free class block
        free_booking = mommy.make_recipe(
            'booking.booking', user=block.user, block=block.children.first()
        )
        self.assertEqual(block.bookings.count(), 10)
        self.assertEqual(block.children.first().bookings.count(), 1)

        # cancel a booking from the original block again
        booking = block.bookings.last()
        booking.status = 'CANCELLED'
        booking.save()

        # free block class still exists, but free_booking has been moved to
        # original block
        self.assertEqual(block.bookings.count(), 10)
        self.assertTrue(block.children.exists())
        self.assertEqual(block.children.first().bookings.count(), 0)
        free_booking.refresh_from_db()
        self.assertEqual(free_booking.block, block)

    def test_reopening_booking_from_block_creates_free_block(self):
        """
        Test reopening a booking that uses the last in 10 blocks creates a
        free class block
        """
        self.assertEqual(Block.objects.count(), 2)

        ev_type = mommy.make(
            EventType, event_type='CL', subtype="Pole level class"
        )
        mommy.make_recipe('booking.blocktype', size=1, cost=0,
            event_type=ev_type, identifier='free class'
        )
        blocktype = mommy.make_recipe(
            'booking.blocktype', size=10, cost=60, duration=4,
            event_type=ev_type, identifier='standard'
        )
        block = mommy.make_recipe(
            'booking.block',
            user=mommy.make_recipe('booking.user', username="TestUser"),
            block_type=blocktype, paid=True
        )
        self.assertTrue(block.active_block())
        # fill block, which will create a free class block
        mommy.make_recipe(
            'booking.booking', user=block.user, block=block, _quantity=10
        )

        self.assertEqual(block.bookings.count(), 10)
        self.assertTrue(block.children.exists())
        self.assertEqual(block.children.count(), 1)

        # cancel a booking from the block deletes free class block
        booking = block.bookings.first()
        booking.status = 'CANCELLED'
        booking.save()

        # free block class has been deleted
        self.assertEqual(block.bookings.count(), 9)
        self.assertFalse(block.children.exists())

        # reopening booking with the block creates a new free class block
        booking.status = 'OPEN'
        booking.block = block
        booking.save()
        self.assertEqual(block.bookings.count(), 10)
        self.assertTrue(block.children.exists())
        self.assertEqual(block.children.count(), 1)


    def test_cancelling_non_block_booking_doesnt_affect_free_block(self):

        self.assertEqual(Block.objects.count(), 2)

        ev_type = mommy.make(
            EventType, event_type='CL', subtype="Pole level class"
        )
        mommy.make_recipe('booking.blocktype', size=1, cost=0,
            event_type=ev_type, identifier='free class'
        )
        blocktype = mommy.make_recipe(
            'booking.blocktype', size=10, cost=60, duration=4,
            event_type=ev_type, identifier='standard'
        )
        block = mommy.make_recipe(
            'booking.block',
            user=mommy.make_recipe('booking.user', username="TestUser"),
            block_type=blocktype, paid=True
        )
        self.assertTrue(block.active_block())
        # fill block, which will create a free class block
        mommy.make_recipe(
            'booking.booking', user=block.user, block=block, _quantity=10
        )
        unrelated_booking = mommy.make_recipe(
            'booking.booking', user=block.user
        )

        self.assertEqual(block.bookings.count(), 10)
        self.assertTrue(block.children.exists())
        self.assertEqual(block.children.count(), 1)

        # cancelling unrelated booking deosn't delete free class block
        unrelated_booking.status = 'CANCELLED'
        unrelated_booking.save()
        self.assertEqual(block.bookings.count(), 10)
        self.assertTrue(block.children.exists())
        self.assertEqual(block.children.count(), 1)

    def test_adding_block_to_booking_creates_free_class(self):
        """
        Adding a block to an existing booking that uses the last of 10 pole
        level class blocks automatically creates a free class block with the original
        block as its parent
        """
        self.assertEqual(Block.objects.count(), 2)

        ev_type = mommy.make(
            EventType, event_type='CL', subtype="Pole level class"
        )
        mommy.make_recipe('booking.blocktype', size=1, cost=0,
            event_type=ev_type, identifier='free class'
        )
        blocktype = mommy.make_recipe(
            'booking.blocktype', size=10, cost=60, duration=4,
            event_type=ev_type, identifier='standard'
        )
        block = mommy.make_recipe(
            'booking.block',
            user=mommy.make_recipe('booking.user', username="TestUser"),
            block_type=blocktype, paid=True
        )
        self.assertTrue(block.active_block())
        mommy.make_recipe(
            'booking.booking', user=block.user, block=block, _quantity=9
        )
        non_block_booking = mommy.make_recipe('booking.booking', user=block.user)
        self.assertEqual(Booking.objects.count(), 10)
        self.assertEqual(block.bookings.count(), 9)
        self.assertEqual(Block.objects.count(), 3)

        non_block_booking.block = block
        non_block_booking.save()
        self.assertEqual(block.bookings.count(), 10)
        self.assertEqual(Block.objects.count(), 4)
        self.assertTrue(block.children.exists())

    def test_removing_block_from_booking_deletes_unused_free_class(self):
        self.assertEqual(Block.objects.count(), 2)

        ev_type = mommy.make(
            EventType, event_type='CL', subtype="Pole level class"
        )
        mommy.make_recipe('booking.blocktype', size=1, cost=0,
            event_type=ev_type, identifier='free class'
        )
        blocktype = mommy.make_recipe(
            'booking.blocktype', size=10, cost=60, duration=4,
            event_type=ev_type, identifier='standard'
        )
        block = mommy.make_recipe(
            'booking.block',
            user=mommy.make_recipe('booking.user', username="TestUser"),
            block_type=blocktype, paid=True
        )
        self.assertTrue(block.active_block())
        mommy.make_recipe(
            'booking.booking', user=block.user, block=block, _quantity=9
        )
        booking = mommy.make_recipe(
            'booking.booking', block=block, user=block.user
        )
        self.assertEqual(Booking.objects.count(), 10)
        self.assertEqual(block.bookings.count(), 10)
        self.assertEqual(Block.objects.count(), 4)

        booking.block = None
        booking.save()

        self.assertEqual(block.bookings.count(), 9)
        self.assertEqual(Block.objects.count(), 3)
        self.assertFalse(block.children.exists())

    def test_removing_block_from_booking_moves_existing_free_class_booking(self):
        self.assertEqual(Block.objects.count(), 2)

        ev_type = mommy.make(
            EventType, event_type='CL', subtype="Pole level class"
        )
        mommy.make_recipe('booking.blocktype', size=1, cost=0,
            event_type=ev_type, identifier='free class'
        )
        blocktype = mommy.make_recipe(
            'booking.blocktype', size=10, cost=60, duration=4,
            event_type=ev_type, identifier='standard'
        )
        block = mommy.make_recipe(
            'booking.block',
            user=mommy.make_recipe('booking.user', username="TestUser"),
            block_type=blocktype, paid=True
        )
        self.assertTrue(block.active_block())
        mommy.make_recipe(
            'booking.booking', user=block.user, block=block, _quantity=9
        )
        block_booking = mommy.make_recipe(
            'booking.booking', block=block, user=block.user
        )
        free_booking = mommy.make_recipe(
            'booking.booking', block=block.children.first(), user=block.user
        )

        self.assertEqual(Booking.objects.count(), 11)
        self.assertEqual(block.bookings.count(), 10)

        block_booking.block = None
        block_booking.save()
        free_booking.refresh_from_db()
        # previous free booking has been moved to empty space in block
        self.assertEqual(block.bookings.count(), 10)
        self.assertEqual(free_booking.block, block)
        # free block still exists but has no booking anymore
        self.assertTrue(block.children.exists())
        self.assertFalse(block.children.first().bookings.exists())

    def test_booking_cannot_be_attended_and_no_show(self):
        with self.assertRaises(ValidationError):
            mommy.make(Booking, attended=True, no_show=True)


class EventTypeTests(TestCase):

    def test_str_class(self):
        evtype = mommy.make_recipe('booking.event_type_PC', subtype="class subtype")
        self.assertEqual(str(evtype), 'Class - class subtype')

    def test_str_event(self):
        evtype = mommy.make_recipe('booking.event_type_OE', subtype="event subtype")
        self.assertEqual(str(evtype), 'Event - event subtype')

        # unknown event type
        evtype.event_type = 'OT'
        evtype.save()
        self.assertEqual(str(evtype), 'Unknown - event subtype')

    def test_str_room_hire(self):
        evtype = mommy.make_recipe('booking.event_type_RH', subtype="event subtype")
        self.assertEqual(str(evtype), 'Room hire - event subtype')


class TicketedEventTests(TestCase):

    def setUp(self):
        self.ticketed_event = mommy.make_recipe(
            'booking.ticketed_event_max10', payment_time_allowed=4
        )

    def tearDown(self):
        del self.ticketed_event

    def test_bookable(self):
        """
        Test that event bookable logic returns correctly
        """
        self.assertTrue(self.ticketed_event.bookable)
        # if we make 10 bookings on this event, it should no longer be bookable
        ticket_booking = mommy.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            purchase_confirmed=True
        )
        mommy.make(
            Ticket,
            ticket_booking=ticket_booking, _quantity=10
        )
        self.assertEqual(self.ticketed_event.tickets_left(), 0)
        self.assertFalse(self.ticketed_event.bookable())

    def test_payment_fields_set_on_save(self):
        """
        Test that an event with no cost has correct fields set
        """
        # if an event is created with 0 cost, the following fields are set to
        # False/None/""
        # advance_payment_required, payment_open, payment_due_date,
        # payment_time_allowed

        self.assertTrue(self.ticketed_event.advance_payment_required)
        self.assertTrue(self.ticketed_event.payment_open)
        self.assertTrue(self.ticketed_event.payment_time_allowed)
        self.assertTrue(self.ticketed_event.ticket_cost > 0)
        #change cost to 0
        self.ticketed_event.ticket_cost = 0
        self.ticketed_event.save()
        self.assertFalse(self.ticketed_event.advance_payment_required)
        self.assertFalse(self.ticketed_event.payment_open)
        self.assertFalse(self.ticketed_event.payment_time_allowed)

    def test_pre_save_payment_time_allowed(self):
        """
        payment_time_allowed automatically makes advance_payment_required true
        """

        self.ticketed_event.payment_due_date = None
        self.ticketed_event.payment_time_allowed = None
        self.ticketed_event.advance_payment_required = False
        self.ticketed_event.save()
        self.assertFalse(self.ticketed_event.advance_payment_required)

        self.ticketed_event.payment_time_allowed = 4
        self.ticketed_event.save()
        self.assertTrue(self.ticketed_event.advance_payment_required)

    def test_pre_save_payment_due_date(self):
        """
        payment_due_date automatically makes advance_payment_required true
        """

        self.ticketed_event.payment_due_date = None
        self.ticketed_event.payment_time_allowed = None
        self.ticketed_event.advance_payment_required = False
        self.ticketed_event.save()
        self.assertFalse(self.ticketed_event.advance_payment_required)

        self.ticketed_event.payment_due_date = timezone.now() + timedelta(1)
        self.ticketed_event.save()
        self.assertTrue(self.ticketed_event.advance_payment_required)

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
            ticket_booking__ticketed_event=self.ticketed_event,
            ticket_booking__purchase_confirmed=True,
            _quantity=5
        )
        self.assertEqual(self.ticketed_event.tickets_left(), 5)

    def test_event_tickets_left_does_not_count_cancelled(self):
        self.assertEqual(self.ticketed_event.max_tickets, 10)
        self.assertEqual(self.ticketed_event.tickets_left(), 10)

        open_booking = mommy.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            purchase_confirmed=True,
            cancelled=False
        )
        mommy.make(
            Ticket, ticket_booking=open_booking, _quantity=5
        )
        self.assertEqual(self.ticketed_event.tickets_left(), 5)

        cancelled_booking = mommy.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            purchase_confirmed=True,
            cancelled=False
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
        # cancelling booking doesn't the tickets but doesn't include them in
        # the ticket count
        self.assertEqual(event_tickets.count(), 10)
        self.assertEqual(self.ticketed_event.tickets_left(), 5)

    def test_event_tickets_left_does_not_count_unconfirmed_purchases(self):
        self.assertEqual(self.ticketed_event.max_tickets, 10)
        self.assertEqual(self.ticketed_event.tickets_left(), 10)

        confirmed_booking = mommy.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            purchase_confirmed=True,
            cancelled=False
        )
        mommy.make(
            Ticket, ticket_booking=confirmed_booking, _quantity=5
        )
        self.assertEqual(self.ticketed_event.tickets_left(), 5)

        # make purchase unconfirmed
        confirmed_booking.purchase_confirmed=False
        confirmed_booking.save()

        event_tickets = Ticket.objects.filter(
            ticket_booking__ticketed_event=self.ticketed_event
        )
        self.assertEqual(event_tickets.count(), 5)
        self.assertEqual(self.ticketed_event.tickets_left(), 10)


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
        booking = mommy.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            purchase_confirmed=True
        )
        mommy.make(
            Ticket, ticket_booking=booking,
            _quantity=10)

        self.assertEqual(self.ticketed_event.tickets_left(), 0)
        with self.assertRaises(TicketBookingError):
            TicketBooking.objects.create(
                ticketed_event=self.ticketed_event,
                user=mommy.make_recipe('booking.user')
            )

    def test_booking_reference_set(self):
        ticket_booking = mommy.make(
            TicketBooking,
            purchase_confirmed=True,
            ticketed_event=mommy.make_recipe(
                'booking.ticketed_event_max10', name='Test event'
            ),
        )
        self.assertIsNotNone(ticket_booking.booking_reference)

        # we can change the booking ref on an exisiting booking and a new one
        # is not created on save
        ticket_booking.booking_reference = "Test booking ref"
        ticket_booking.save()
        self.assertEqual(ticket_booking.booking_reference,  "Test booking ref")


class TicketTests(TestCase):

    def test_cannot_create_ticket_for_full_event(self):
        ticketed_event = mommy.make_recipe('booking.ticketed_event_max10')
        booking = mommy.make(
            TicketBooking, ticketed_event=ticketed_event,
            purchase_confirmed=True
        )
        mommy.make(
            Ticket, ticket_booking=booking,
            _quantity=10)
        self.assertEqual(ticketed_event.tickets_left(), 0)

        with self.assertRaises(TicketBookingError):
            Ticket.objects.create(ticket_booking=booking)


class BlockTypeTests(TestCase):

    def test_cannot_create_multiple_free_class_block_types(self):
        ev_type = mommy.make_recipe('booking.event_type_PC')
        mommy.make(BlockType, event_type=ev_type, identifier='free class')
        self.assertEqual(BlockType.objects.count(), 1)

        with self.assertRaises(BlockTypeError):
            mommy.make(BlockType, event_type=ev_type, identifier='free class')
        self.assertEqual(BlockType.objects.count(), 1)

    def test_cannot_create_multiple_transfer_block_types(self):
        ev_type = mommy.make_recipe('booking.event_type_PC')
        mommy.make(BlockType, event_type=ev_type, identifier='transferred')
        self.assertEqual(BlockType.objects.count(), 1)

        with self.assertRaises(BlockTypeError):
            mommy.make(BlockType, event_type=ev_type, identifier='transferred')
        self.assertEqual(BlockType.objects.count(), 1)

    def test_cann_create_transfer_block_types_for_different_events(self):
        pc_ev_type = mommy.make_recipe('booking.event_type_PC')
        pp_ev_type = mommy.make_recipe('booking.event_type_PP')

        mommy.make(BlockType, event_type=pc_ev_type, identifier='transferred')
        self.assertEqual(BlockType.objects.count(), 1)

        mommy.make(BlockType, event_type=pp_ev_type, identifier='transferred')
        self.assertEqual(BlockType.objects.count(), 2)


class VoucherTests(TestCase):

    @patch('booking.models.timezone')
    def test_voucher_dates(self, mock_tz):
        mock_now = datetime(
            2016, 1, 5, 16, 30, 30, 30, tzinfo=timezone.utc
        )
        mock_tz.now.return_value = mock_now
        voucher = mommy.make(EventVoucher, start_date=mock_now)
        self.assertEqual(
            voucher.start_date,
            datetime(2016, 1, 5, 0, 0, 0, 0, tzinfo=timezone.utc)
        )

        voucher.expiry_date = datetime(
            2016, 1, 6, 18, 30, 30, 30, tzinfo=timezone.utc
        )
        voucher.save()
        self.assertEqual(
            voucher.expiry_date,
            datetime(2016, 1, 6, 23, 59, 59, 0, tzinfo=timezone.utc)
        )

    @patch('booking.models.timezone')
    def test_has_expired(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2016, 1, 5, 12, 30, tzinfo=timezone.utc
        )

        voucher = mommy.make(
            EventVoucher,
            start_date=datetime(2016, 1, 1, tzinfo=timezone.utc),
            expiry_date=datetime(2016, 1, 4, tzinfo=timezone.utc)
        )
        self.assertTrue(voucher.has_expired)

        mock_tz.now.return_value = datetime(
            2016, 1, 3, 12, 30, tzinfo=timezone.utc
        )
        self.assertFalse(voucher.has_expired)

    @patch('booking.models.timezone')
    def test_has_started(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2016, 1, 5, 12, 30, tzinfo=timezone.utc
        )

        voucher = mommy.make(
            EventVoucher,
            start_date=datetime(2016, 1, 1, tzinfo=timezone.utc),
        )
        self.assertTrue(voucher.has_started)

        voucher.start_date = datetime(2016, 1, 6, tzinfo=timezone.utc)
        self.assertFalse(voucher.has_started)

    def test_check_event_type(self):
        voucher = mommy.make(EventVoucher)
        pc_event_type = mommy.make_recipe('booking.event_type_PC')
        pp_event_type = mommy.make_recipe('booking.event_type_PP')
        ws_event_type = mommy.make_recipe('booking.event_type_WS')
        voucher.event_types.add(pp_event_type)
        voucher.event_types.add(pc_event_type)

        self.assertFalse(voucher.check_event_type(ws_event_type))
        self.assertTrue(voucher.check_event_type(pc_event_type))
        self.assertTrue(voucher.check_event_type(pp_event_type))

    def test_check_block_type(self):
        voucher = mommy.make(BlockVoucher)
        block_type1 = mommy.make_recipe('booking.blocktype')
        block_type2 = mommy.make_recipe('booking.blocktype')
        block_type3 = mommy.make_recipe('booking.blocktype')
        voucher.block_types.add(block_type1)
        voucher.block_types.add(block_type2)

        self.assertFalse(voucher.check_block_type(block_type3))
        self.assertTrue(voucher.check_block_type(block_type1))
        self.assertTrue(voucher.check_block_type(block_type2))

    def test_str(self):
        voucher = mommy.make(EventVoucher, code="testcode")
        self.assertEqual(str(voucher), 'testcode')