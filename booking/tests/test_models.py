from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta, datetime
from mock import patch
from model_mommy import mommy

from booking.models import Event, Block, Booking

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
        # advance_payment_required, payment_open, payment_due_date, payment_link
        # (these are the defaults for all except payment_link)

        # event with 0 cost; check payment_link is "" and not the default paypal
        self.assertEquals(self.event.payment_link, "")

        # event with cost, check payment link is default
        poleclass = mommy.make_recipe('booking.future_PC', cost=7)
        self.assertEquals(
            poleclass.payment_link,
            "https://www.paypal.com/uk/webapps/mpp/send-money-online"
        )

        #change cost to 0, check payment_link is reset to ""
        poleclass.cost = 0
        poleclass.save()
        self.assertEquals(poleclass.payment_link, "")

        # event with cost, check other fields are left as is
        workshop = mommy.make_recipe('booking.future_WS',
                                     cost=10,
                                     payment_open=True,
                                     payment_info="Pay me")
        self.assertEquals(workshop.payment_open, True)
        self.assertEquals(workshop.payment_info, "Pay me")
        self.assertEquals(
            workshop.payment_link,
            "https://www.paypal.com/uk/webapps/mpp/send-money-online"
        )

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

    def test_date_space_confirmed_free_event(self):
        """
        Test autopopulating date space confirmed.  For free event, this is the
        datetime the booking is created
        """
        booking = mommy.make_recipe('booking.booking',
                                    user=self.users[0],
                                    event=self.event)
        self.assertTrue(booking.date_space_confirmed)

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

    def test_date_space_confirmed_paid_event(self):
        """
        Test autopopulating date space confirmed for paid event
        """
        booking = mommy.make_recipe('booking.booking',                                    user=self.users[0],
                                    event=self.event_with_cost)
        # booking is created with no space confirmed date
        self.assertFalse(booking.space_confirmed())
        self.assertFalse(booking.date_space_confirmed)

        booking.confirm_space()
        self.assertTrue(booking.space_confirmed())
        self.assertTrue(booking.date_space_confirmed)

    def test_cancelled_booking_is_no_longer_confirmed(self):
        booking = mommy.make_recipe('booking.booking',
                                    user=self.users[0],
                                    event=self.event_with_cost)
        booking.confirm_space()
        self.assertTrue(booking.space_confirmed())

        booking.status = 'CANCELLED'
        booking.save()
        self.assertFalse(booking.space_confirmed())


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
                         datetime(2015, 3, 1, tzinfo=timezone.utc))
        self.assertEqual(self.large_block.expiry_date,
                 datetime(2015, 5, 1, tzinfo=timezone.utc))

    @patch.object(timezone, 'now',
                  return_value=datetime(2015, 2, 1, tzinfo=timezone.utc))
    def test_active_small_block(self, mock_now):
        """
        Test that a 5 class unexpired block returns active correctly
        """
        #self.small_block has not expired, block isn't full, payment not confirmed
        self.assertFalse(self.small_block.active_block())
        # set payment confirmed
        self.small_block.payment_confirmed=True
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
        # set payment confirmed
        self.large_block.payment_confirmed = True
        self.assertTrue(self.large_block.active_block())

        # but self.small_block has expired, not active even if payment confirmed
        self.small_block.payment_confirmed = True
        self.assertFalse(self.small_block.active_block())

    @patch.object(timezone, 'now',
                  return_value=datetime(2015, 2, 1, tzinfo=timezone.utc))
    def test_active_full_blocks(self, mock_now):
        """
        Test that active is set to False if a block is full
        """

        # Neither self.small_block or self.large_block have expired
        # confirm payment on both
        self.small_block.payment_confirmed = True
        self.large_block.payment_confirmed = True
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
