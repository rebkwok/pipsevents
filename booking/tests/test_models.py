# -*- coding: utf-8 -*-
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import override_settings, TestCase
from django.utils import timezone
from django.urls import reverse

from datetime import timedelta, datetime
from datetime import timezone as dt_timezone

from unittest.mock import patch
from model_bakery import baker
import pytest

from booking.models import AllowedGroup, Banner, Event, EventType, Block, BlockType, BlockTypeError, \
    Booking, TicketBooking, Ticket, TicketBookingError, BlockVoucher, \
    EventVoucher, GiftVoucherType, FilterCategory, UsedBlockVoucher, UsedEventVoucher
from common.tests.helpers import PatchRequestMixin
from stripe_payments.tests.mock_connector import MockConnector


now = timezone.now()


class EventTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.event = baker.make_recipe('booking.future_EV')

    def test_location_index(self):
        assert self.event.location_index == 1

    def test_bookable_booking_not_open(self):
        """
        Test that event bookable logic returns correctly
        """
        event = baker.make_recipe('booking.future_EV', booking_open=False)
        self.assertFalse(event.bookable)

    def test_bookable_with_no_payment_date(self):
        """
        Test that event bookable logic returns correctly
        """
        event = baker.make_recipe('booking.future_EV')
        self.assertTrue(event.bookable)

    def test_bookable_spaces(self):
        event = baker.make_recipe('booking.future_EV', max_participants=2)
        self.assertTrue(event.bookable)

        baker.make_recipe('booking.booking', event=event, _quantity=2)
        # need to get event again as bookable is cached property
        event = Event.objects.get(id=event.id)
        self.assertFalse(event.bookable)

    @patch('booking.models.booking_models.timezone')
    def test_bookable_with_payment_dates(self, mock_tz):
        """
        Test that event bookable logic returns correctly for events with
        payment due dates
        """
        mock_tz.now.return_value = datetime(2015, 2, 1, tzinfo=dt_timezone.utc)
        event = baker.make_recipe(
            'booking.future_EV',
            cost=10,
            payment_due_date=datetime(2015, 2, 2, tzinfo=dt_timezone.utc))

        self.assertTrue(event.bookable)

        # bookable even if payment due date has passed
        event1 = baker.make_recipe(
            'booking.future_EV',
            cost=10,
            payment_due_date=datetime(2015, 1, 31, tzinfo=dt_timezone.utc)
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

        poleclass = baker.make_recipe(
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
        workshop = baker.make_recipe('booking.future_WS',
                                     cost=10,
                                     payment_open=True,
                                     payment_info="Pay me")
        self.assertEqual(workshop.payment_open, True)
        self.assertEqual(workshop.payment_info, "Pay me")

    def test_pre_save_external_instructor(self):
        pc = baker.make_recipe(
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
        pc = baker.make_recipe(
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
        event = baker.make_recipe(
            'booking.past_event',
            name='Test event',
            date=datetime(2015, 1, 1, tzinfo=dt_timezone.utc)
        )
        self.assertEqual(
            str(event), 'Test event - 01 Jan 2015, 00:00 (Main Studio)'
        )

    def test_online_class_show_video_link(self):
        online_event_type = baker.make(EventType, event_type="CL", subtype="Online class")
        event = baker.make_recipe('booking.past_event')
        # not an online event
        assert event.show_video_link is False

        # online event, past
        event.event_type = online_event_type
        event.save()
        assert event.show_video_link is True

        # future online event, <20 mins ahead
        event.date = timezone.now() + timedelta(minutes=19)
        event.save()
        assert event.show_video_link is True

        # future online event, >20mins ahead
        event.date = timezone.now() + timedelta(minutes=21)
        event.save()
        assert event.show_video_link is False

    def test_allowed_group(self):
        pp_et = baker.make_recipe("booking.event_type_PP")
        allowed_group = baker.make(AllowedGroup, description="test", group__name="test")
        pp = baker.make_recipe('booking.future_PP', event_type=pp_et, allowed_group_override=allowed_group)
        pp1 = baker.make_recipe('booking.future_PP', event_type=pp_et, allowed_group_override=None)

        assert pp.allowed_group_for_event() == allowed_group
        assert pp_et.allowed_group_description ==  pp_et.allowed_group.description
        assert pp.allowed_group_description == "test"
        assert pp1.allowed_group_description == "regular student only"


        assert self.event.allowed_group == AllowedGroup.default_group()
        assert self.event.allowed_group_description == "default group; open to all"


class BookingTests(PatchRequestMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.event = baker.make_recipe('booking.future_EV', max_participants=20)
        cls.subscribed = baker.make(Group, name='subscribed')

    def setUp(self):
        super(BookingTests, self).setUp()
        baker.make_recipe('booking.user', _quantity=15)
        self.users = User.objects.all()
        self.event_with_cost = baker.make_recipe('booking.future_EV',
                                                 advance_payment_required=True,
                                                 cost=10)

    def test_event_spaces_left(self):
        """
        Test that spaces left is calculated correctly
        """

        self.assertEqual(self.event.max_participants, 20)
        self.assertEqual(self.event.spaces_left, 20)

        for user in self.users:
            baker.make_recipe('booking.booking', user=user, event=self.event)

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
            baker.make_recipe('booking.booking', user=user, event=self.event)
        baker.make_recipe(
            'booking.booking', event=self.event, no_show=True
        )
        baker.make_recipe(
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

        booking = baker.make_recipe('booking.booking',
                                    user=self.users[0], event=self.event)
        self.assertTrue(booking.space_confirmed())

    def test_confirm_space(self):
        """
        Test confirm_space method on a booking
        """

        booking = baker.make_recipe('booking.booking',
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

        booking = baker.make_recipe('booking.booking',
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

        booking = baker.make_recipe('booking.booking',
                                    user=self.users[0],
                                    event=self.event_with_cost)
        self.assertTrue(booking.space_confirmed())

    def test_date_payment_confirmed(self):
        """
        Test autopopulating date payment confirmed.
        """
        booking = baker.make_recipe('booking.booking',
                                    user=self.users[0],
                                    event=self.event_with_cost)
        # booking is created with no payment confirmed date
        self.assertFalse(booking.date_payment_confirmed)

        booking.payment_confirmed = True
        booking.save()
        self.assertTrue(booking.date_payment_confirmed)

    def test_cancelled_booking_is_no_longer_confirmed(self):
        booking = baker.make_recipe('booking.booking',
                                    user=self.users[0],
                                    event=self.event_with_cost)
        booking.confirm_space()
        self.assertTrue(booking.space_confirmed())

        booking.status = 'CANCELLED'
        booking.save()
        self.assertFalse(booking.space_confirmed())

    def test_free_class_is_set_to_paid(self):
        booking = baker.make_recipe('booking.booking',
                                    user=self.users[0],
                                    event=self.event_with_cost,
                                    free_class=True)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)
        self.assertTrue(booking.space_confirmed())

    def test_str(self):
        booking = baker.make_recipe(
            'booking.booking',
            event=baker.make_recipe(
                'booking.future_EV', name='Test event', date=datetime(2015, 1, 1, 18, 0, tzinfo=dt_timezone.utc)),
            user=baker.make_recipe('booking.user', username='Test user'),
            )
        self.assertEqual(str(booking), 'Test event - Test user - 01Jan2015 18:00')

    def test_booking_full_event(self):
        """
        Test that attempting to create new booking for full event raises
        ValidationError
        """
        self.event_with_cost.max_participants = 3
        self.event_with_cost.save()
        baker.make_recipe(
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
        baker.make_recipe(
            'booking.booking', event=self.event_with_cost, _quantity=3
        )
        event = Event.objects.get(id=self.event_with_cost.id)
        booking = baker.make_recipe(
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
        new_user = baker.make_recipe('booking.user')
        self.event_with_cost.max_participants = 3
        self.event_with_cost.save()
        baker.make_recipe(
            'booking.booking', event=self.event_with_cost, _quantity=3
        )
        Booking.objects.create(
            event=self.event_with_cost, user=new_user, status='CANCELLED'
        )
        self.assertEqual(
            Booking.objects.filter(event=self.event_with_cost).count(), 4
        )

    @patch('booking.models.booking_models.timezone')
    def test_reopening_booking_sets_date_reopened(self, mock_tz):
        """
        Test that reopening a cancelled booking for an event with spaces sets
        the rebooking date
        """
        mock_now = datetime(2015, 1, 1, tzinfo=dt_timezone.utc)
        mock_tz.now.return_value = mock_now
        user = self.users[0]
        booking = baker.make_recipe(
            'booking.booking', event=self.event_with_cost, user=user,
            status='CANCELLED'
        )

        self.assertIsNone(booking.date_rebooked)
        booking.status = 'OPEN'
        booking.save()
        booking.refresh_from_db()
        self.assertEqual(booking.date_rebooked, mock_now)


    @patch('booking.models.booking_models.timezone')
    def test_reopening_booking_again_resets_date_reopened(self, mock_tz):
        """
        Test that reopening a second time resets the rebooking date
        """
        mock_now = datetime(2015, 3, 1, tzinfo=dt_timezone.utc)
        mock_tz.now.return_value = mock_now
        user = self.users[0]
        booking = baker.make_recipe(
            'booking.booking', event=self.event_with_cost, user=user,
            status='CANCELLED',
            date_rebooked=datetime(2015, 1, 1, tzinfo=dt_timezone.utc)
        )
        self.assertEqual(
            booking.date_rebooked, datetime(2015, 1, 1, tzinfo=dt_timezone.utc)
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
        baker.make_recipe(
            'booking.booking', event=self.event_with_cost, _quantity=3
        )
        event = Event.objects.get(id=self.event_with_cost.id)
        booking = baker.make_recipe(
            'booking.booking', event=event, user=user, status='CANCELLED'
        )
        with self.assertRaises(ValidationError):
            booking.status = 'OPEN'
            booking.save()

        booking.refresh_from_db()
        self.assertIsNone(booking.date_rebooked)

    def test_user_not_added_to_mailing_list_when_booking_first_CL(self):
        # test that previous behaviour has been removed
        user = baker.make_recipe('booking.user')
        self.assertNotIn(self.subscribed, user.groups.all())
        baker.make(Booking, user=user, event__event_type__event_type='CL')
        self.assertNotIn(self.subscribed, user.groups.all())

    def test_unsubscribed_user_with_past_CL_not_added_to_mailing_list(self):
        user = baker.make_recipe('booking.user')
        self.subscribed.user_set.add(user)
        baker.make(Booking, user=user, event__event_type__event_type='CL')
        self.assertIn(self.subscribed, user.groups.all())

        self.subscribed.user_set.remove(user)
        self.assertNotIn(self.subscribed, user.groups.all())

        baker.make(Booking, user=user, event__event_type__event_type='CL')
        self.assertEqual(Booking.objects.filter(user=user).count(), 2)
        self.assertNotIn(self.subscribed, user.groups.all())

    def test_user_not_added_to_mailing_list_when_booking_non_CL(self):
        user = baker.make_recipe('booking.user')
        self.assertNotIn(self.subscribed, user.groups.all())
        baker.make(Booking, user=user, event__event_type__event_type='EV')
        self.assertNotIn(self.subscribed, user.groups.all())
        self.assertTrue(Booking.objects.filter(user=user).exists())

        # no longer added when booking clasas either
        baker.make(Booking, user=user, event__event_type__event_type='CL')
        self.assertNotIn(self.subscribed, user.groups.all())

    def test_booking_autocancelled(self):
        # new booking set to auto_cancelled = False
        booking = baker.make(Booking, user=self.users[0])
        self.assertFalse(booking.auto_cancelled)
        booking.status = 'CANCELLED'
        booking.auto_cancelled = True
        booking.save()

        # changing booking to open again resets autocancelled
        booking.status = 'OPEN'
        booking.save()
        self.assertFalse(booking.auto_cancelled)

    @patch('booking.models.booking_models.timezone')
    def test_can_cancel(self, mock_tz):
        mock_now = datetime(2015, 3, 1, tzinfo=dt_timezone.utc)
        mock_tz.now.return_value = mock_now

        event = baker.make_recipe(
            'booking.future_PC',
            date=datetime(2015, 3, 3, tzinfo=dt_timezone.utc),
            cancellation_period=24
        )
        booking = baker.make(Booking, user=self.users[0], event=event)

        # event allows cancellation and outside cancellation period
        self.assertTrue(booking.can_cancel)

        event.allow_booking_cancellation = False
        event.save()
        # get booking from db because can_cancel is cached property
        booking = Booking.objects.get(id=booking.id)
        self.assertFalse(booking.can_cancel)

        event.allow_booking_cancellation = True
        event.save()
        booking = Booking.objects.get(id=booking.id)
        self.assertTrue(booking.can_cancel)

        mock_now = datetime(2015, 3, 2, 18, 0, tzinfo=dt_timezone.utc)
        mock_tz.now.return_value = mock_now
        # event cancellation allowed but now we're within cancellation period
        booking = Booking.objects.get(id=booking.id)
        self.assertFalse(booking.can_cancel)

    def test_booking_cannot_be_attended_and_no_show(self):
        with self.assertRaises(ValidationError):
            baker.make(Booking, attended=True, no_show=True)

    def test_cost_with_voucher(self):
        event = baker.make_recipe(
            'booking.future_PC',
            cost=10,
            date=datetime(2015, 3, 3, tzinfo=dt_timezone.utc),
            cancellation_period=24
        )
        booking = baker.make(Booking, event=event)

        assert booking.cost_with_voucher == 10
        booking.voucher_code = "unk"
        booking.save()

        assert booking.cost_with_voucher == 10
        booking.voucher_code is None

        voucher = EventVoucher.objects.create(code="foo", discount=10)
        voucher.event_types.add(event.event_type)
        booking.voucher_code = "foo"
        booking.save()
        assert booking.cost_with_voucher == 9

    def test_process_voucher(self):
        event = baker.make_recipe(
            'booking.future_PC',
            cost=10,
            date=datetime(2015, 3, 3, tzinfo=dt_timezone.utc),
            cancellation_period=24
        )
        booking = baker.make(Booking, event=event)
        voucher = EventVoucher.objects.create(code="foo", discount=10)
        voucher.event_types.add(event.event_type)

        # invalid voucher
        booking.voucher_code = "unk"
        booking.save()
        booking.process_voucher()
        assert UsedEventVoucher.objects.exists() is False

        # valid voucher
        booking.voucher_code = "foo"
        booking.save()
        booking.process_voucher()
        assert UsedEventVoucher.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "now,event_date,can_cancel,cancellation_period",
    [
        # now = DST, event = not DST
        # Although there are only 23 hrs between now and the event datetime, cancellation
        # is allowed because it crosses DST
        # i.e. in local time, it's currently 9.30am, and the event start is 10am, so users
        # expect to be able to cancel
        (
            datetime(2023, 3, 25, 9, 30, tzinfo=dt_timezone.utc), # not DST
            datetime(2023, 3, 26, 9, 0, tzinfo=dt_timezone.utc), # DST
            True,
            24
        ),
        # This is > 24 hrs
        (
            datetime(2023, 3, 25, 8, 30, tzinfo=dt_timezone.utc), # not DST
            datetime(2023, 3, 26, 9, 0, tzinfo=dt_timezone.utc), # DST
            True,
            24
        ),
        # less than 23 hrs
        (
            datetime(2023, 3, 25, 10, 5, tzinfo=dt_timezone.utc), # not DST
            datetime(2023, 3, 26, 9, 0, tzinfo=dt_timezone.utc), # DST
            False,
            24
        ),
        # both DST, <24 hrs
        (
            datetime(2023, 3, 26, 9, 30, tzinfo=dt_timezone.utc),
            datetime(2023, 3, 27, 9, 0, tzinfo=dt_timezone.utc),
            False,
            24
        ),
        # longer cancellation period
        (
            datetime(2023, 3, 23, 9, 30, tzinfo=dt_timezone.utc), # not DST
            datetime(2023, 3, 26, 9, 0, tzinfo=dt_timezone.utc), # DST
            True,
            72
        ),
        # longer cancellation period
        (
            datetime(2023, 3, 23, 8, 30, tzinfo=dt_timezone.utc), # not DST
            datetime(2023, 3, 26, 9, 0, tzinfo=dt_timezone.utc), # DST
            True,
            72
        ),
        # longer cancellation period
        (
            datetime(2023, 3, 23, 10, 30, tzinfo=dt_timezone.utc), # not DST
            datetime(2023, 3, 26, 9, 0, tzinfo=dt_timezone.utc), # DST
            False,
            72
        ),
        # now is DST, event not DST
        # > 24.5 hrs between now and event date
        (
            datetime(2022, 10, 29, 9, 30, tzinfo=dt_timezone.utc), # DST; 10:30 local
            datetime(2022, 10, 30, 10, 0, tzinfo=dt_timezone.utc), # not DST
            False,
            24
        ),
        (
            datetime(2022, 10, 29, 8, 55, tzinfo=dt_timezone.utc), # DST; 10:30 local
            datetime(2022, 10, 30, 10, 0, tzinfo=dt_timezone.utc), # not DST
            True,
            24
        ),
    ]
)
@patch('booking.models.booking_models.timezone')
def test_can_cancel_with_daylight_savings_time(mock_tz, now, event_date, can_cancel, cancellation_period):
    mock_tz.now.return_value = now
    event = baker.make_recipe(
        'booking.future_PC',
        date=event_date,
        cancellation_period=cancellation_period
    )
    assert event.can_cancel == can_cancel


class BlockTests(PatchRequestMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        baker.make_recipe('booking.future_PC', _quantity=10)

    def setUp(self):
        super(BlockTests, self).setUp()
        # note for purposes of testing, start_date is set to 1.1.15
        self.small_block = baker.make_recipe('booking.block_5')
        self.large_block = baker.make_recipe('booking.block_10')

    def test_block_expiry_date(self):
        """
        Test that block expiry dates are populated correctly
        """
        dt = datetime(2015, 1, 1, tzinfo=dt_timezone.utc)
        self.assertEqual(self.small_block.start_date, dt)
        # Times are in UTC, but converted from local (GMT/BST)
        # No daylight savings
        self.assertEqual(self.small_block.expiry_date,
                         datetime(2015, 3, 1, 23, 59, 59, tzinfo=dt_timezone.utc))
        # Daylight savings
        self.assertEqual(self.large_block.expiry_date,
                 datetime(2015, 5, 1, 22, 59, 59, tzinfo=dt_timezone.utc))

    def test_block_extended_expiry_date_set_to_end_of_day(self):
        """
        Test that extended expiry dates are set to end of day on save
        """
        self.assertIsNone(self.small_block.extended_expiry_date)

        self.small_block.extended_expiry_date = datetime(
            2016, 2, 1, 18, 30, tzinfo=dt_timezone.utc
        )
        self.small_block.save()
        self.assertEqual(
            self.small_block.extended_expiry_date,
            datetime(2016, 2, 1, 23, 59, 59, tzinfo=dt_timezone.utc)
        )

        # with DST
        self.small_block.extended_expiry_date = datetime(
            2016, 5, 1, 18, 30, tzinfo=dt_timezone.utc
        )
        self.small_block.save()
        self.assertEqual(
            self.small_block.extended_expiry_date,
            datetime(2016, 5, 1, 22, 59, 59, tzinfo=dt_timezone.utc)
        )

    def test_block_expiry_date_with_extended_date(self):
        """
        Test that expiry_date shows extended expiry date if set
        """
        # expiry date calculated based on start data and duration
        self.assertEqual(
            self.small_block.expiry_date,
            datetime(2015, 3, 1, 23, 59, 59, tzinfo=dt_timezone.utc)
        )

        self.small_block.extended_expiry_date = datetime(
            2016, 2, 1, 18, 30, tzinfo=dt_timezone.utc
        )
        self.small_block.save()
        # expiry date is now extended expiry date
        self.assertEqual(
            self.small_block.expiry_date,
            datetime(2016, 2, 1, 23, 59, 59, tzinfo=dt_timezone.utc)
        )

        # set extended exipry date to a date < the expiry date calculated by
        # start date and duration
        self.small_block.extended_expiry_date = datetime(
            2015, 2, 1, 18, 30, tzinfo=dt_timezone.utc
        )
        self.small_block.save()
        self.assertEqual(
            self.small_block.extended_expiry_date,
            datetime(2015, 2, 1, 23, 59, 59, tzinfo=dt_timezone.utc)
        )
        # earlier extended expiry date is allowed
        self.assertEqual(
            self.small_block.expiry_date,
            datetime(2015, 2, 1, 23, 59, 59, tzinfo=dt_timezone.utc)
        )

    @patch('booking.models.booking_models.timezone.now')
    def test_block_start_date_reset_on_paid(self, mock_now):
        """
        Test that a block's start date is set to current date on payment
        """
        now = datetime(2015, 2, 1, tzinfo=dt_timezone.utc)
        mock_now.return_value = now

        # self.small_block has not expired, block isn't full, payment not
        # confirmed
        self.assertFalse(self.small_block.paid)
        self.assertNotEqual(self.small_block.start_date, now)
        # set paid
        self.small_block.paid = True
        self.small_block.save()
        self.assertEqual(self.small_block.start_date, now)

    @patch.object(timezone, 'now',
                  return_value=datetime(2015, 2, 1, tzinfo=dt_timezone.utc))
    def test_active_small_block(self, mock_now):
        """
        Test that a 5 class unexpired block returns active correctly
        """
        # self.small_block has not expired, block isn't full, payment not
        # confirmed
        self.assertFalse(self.small_block.active_block())
        # set paid
        self.small_block.paid = True
        self.small_block.save()
        self.assertTrue(self.small_block.active_block())

    @patch.object(timezone, 'now',
                  return_value=datetime(2015, 3, 2, tzinfo=dt_timezone.utc))
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
                  return_value=datetime(2015, 2, 1, tzinfo=dt_timezone.utc))
    def test_active_full_blocks(self, mock_now):
        """
        Test that active is set to False if a block is full
        """

        # Neither self.small_block or self.large_block have expired
        # both paid
        self.small_block.paid = True
        self.large_block.paid = True
        # no bookings against either, active_block = True
        self.assertEqual(Booking.objects.filter(
            block__id=self.small_block.id).count(), 0)
        self.assertEqual(Booking.objects.filter(
            block__id=self.large_block.id).count(), 0)
        self.assertTrue(self.small_block.active_block())
        self.assertTrue(self.large_block.active_block())

        # make some bookings against the blocks
        poleclasses = Event.objects.all()
        poleclasses5 = poleclasses[0:5]
        for pc in poleclasses5:
            baker.make_recipe(
                'booking.booking',
                user=self.small_block.user,
                block=self.small_block,
                event=pc
            )
            baker.make_recipe(
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
            baker.make_recipe(
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

        events = baker.make_recipe('booking.future_EV', cost=10, _quantity=5)
        block_bookings = [baker.make_recipe(
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
        blocktype = baker.make_recipe('booking.blocktype', size=4,
            event_type__subtype="Pole level class"
        )
        block = baker.make_recipe(
            'booking.block',
            start_date=datetime(2015, 1, 1, tzinfo=dt_timezone.utc),
            user=baker.make_recipe('booking.user', username="TestUser"),
            block_type=blocktype,
        )

        self.assertEqual(
            str(block), 'TestUser -- Pole level class -- size 4 -- '
                        'start 01 Jan 2015'
        )

    def test_str_for_transfer_block(self):
        blocktype1 = baker.make_recipe(
            'booking.blocktype', size=1, duration=1, identifier='transferred',
            event_type__subtype="Pole level class"
        )
        block1 = baker.make_recipe(
            'booking.block',
            start_date=datetime(2015, 1, 1, tzinfo=dt_timezone.utc),
            user=baker.make_recipe('booking.user', username="TestUser1"),
            block_type=blocktype1,
        )

        self.assertEqual(
            str(block1), 'TestUser1 -- Pole level class (transferred) -- '
                         'size 1 -- start 01 Jan 2015'
        )

    def test_str_for_free_class_block(self):
        blocktype = baker.make_recipe('booking.blocktype', size=1, cost=0,
            event_type__subtype="Pole level class", identifier='free class'
        )
        block = baker.make_recipe(
            'booking.block',
            start_date=datetime(2015, 1, 1, tzinfo=dt_timezone.utc),
            user=baker.make_recipe('booking.user', username="TestUser"),
            block_type=blocktype,
        )

        self.assertEqual(
            str(block), 'TestUser -- Pole level class (free class) '
                        '-- size 1 -- start 01 Jan 2015'
        )

    def test_cost_with_voucher(self):
        blocktype = baker.make_recipe(
            'booking.blocktype', size=10, cost=60, duration=4,
        )
        block = baker.make_recipe(
            'booking.block',
            block_type=blocktype, paid=False
        )
        assert block.cost_with_voucher == 60
        block.voucher_code = "unk"
        block.save()

        assert block.cost_with_voucher == 60
        block.voucher_code is None

        voucher = BlockVoucher.objects.create(code="foo", discount=10)
        voucher.block_types.add(blocktype)
        block.voucher_code = "foo"
        block.save()
        assert block.cost_with_voucher == 54
        assert block.voucher_code == "foo"

    def test_process_voucher(self):
        blocktype = baker.make_recipe(
            'booking.blocktype', size=10, cost=60, duration=4,
        )
        block = baker.make_recipe(
            'booking.block',
            block_type=blocktype, paid=False
        )

        voucher = BlockVoucher.objects.create(code="foo", discount=10)
        voucher.block_types.add(blocktype)

        # invalid voucher
        block.voucher_code = "unk"
        block.save()
        block.process_voucher()
        assert UsedBlockVoucher.objects.exists() is False

        # valid voucher
        block.voucher_code = "foo"
        block.save()
        block.process_voucher()
        assert UsedBlockVoucher.objects.exists()
        

class EventTypeTests(TestCase):

    def test_str_class(self):
        evtype = baker.make_recipe('booking.event_type_PC', subtype="class subtype")
        self.assertEqual(str(evtype), 'Class - class subtype')

    def test_str_event(self):
        evtype = baker.make_recipe('booking.event_type_OE', subtype="event subtype")
        self.assertEqual(str(evtype), 'Event - event subtype')

        # unknown event type
        evtype.event_type = 'UK'
        evtype.save()
        self.assertEqual(str(evtype), 'Unknown - event subtype')

    def test_str_room_hire(self):
        evtype = baker.make_recipe('booking.event_type_RH', subtype="event subtype")
        self.assertEqual(str(evtype), 'Room hire - event subtype')


class TicketedEventTests(TestCase):

    def setUp(self):
        self.ticketed_event = baker.make_recipe(
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
        ticket_booking = baker.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            purchase_confirmed=True
        )
        baker.make(
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
            2015, 1, 1, 13, 30, tzinfo=dt_timezone.utc
        )
        self.ticketed_event.save()
        self.assertEqual(
            self.ticketed_event.payment_due_date, datetime(
            2015, 1, 1, 23, 59, 59, 0, tzinfo=dt_timezone.utc
        )
        )

    def test_str(self):
        ticketed_event = baker.make_recipe(
            'booking.ticketed_event_max10',
            name='Test event',
            date=datetime(2015, 1, 1, tzinfo=dt_timezone.utc)
        )
        self.assertEqual(str(ticketed_event), 'Test event - 01 Jan 2015, 00:00')

    def test_waiting_list_str(self):
        user = baker.make(User, username="test")
        wluser = baker.make("booking.TicketedEventWaitingListUser", ticketed_event=self.ticketed_event, user=user)
        assert str(wluser) == f"test - {self.ticketed_event}" 


class TicketBookingTests(TestCase):

    def setUp(self):
        self.ticketed_event = baker.make_recipe('booking.ticketed_event_max10')

    def tearDown(self):
        del self.ticketed_event

    def test_event_tickets_left(self):
        """
        Test that tickets left is calculated correctly
        """

        self.assertEqual(self.ticketed_event.max_tickets, 10)
        self.assertEqual(self.ticketed_event.tickets_left(), 10)

        baker.make(
            Ticket,
            ticket_booking__ticketed_event=self.ticketed_event,
            ticket_booking__purchase_confirmed=True,
            _quantity=5
        )
        self.assertEqual(self.ticketed_event.tickets_left(), 5)

    def test_event_tickets_left_does_not_count_cancelled(self):
        self.assertEqual(self.ticketed_event.max_tickets, 10)
        self.assertEqual(self.ticketed_event.tickets_left(), 10)

        open_booking = baker.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            purchase_confirmed=True,
            cancelled=False
        )
        baker.make(
            Ticket, ticket_booking=open_booking, _quantity=5
        )
        self.assertEqual(self.ticketed_event.tickets_left(), 5)

        cancelled_booking = baker.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            purchase_confirmed=True,
            cancelled=False
        )
        baker.make(
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

        confirmed_booking = baker.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            purchase_confirmed=True,
            cancelled=False
        )
        baker.make(
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
        booking = baker.make(
            TicketBooking,
            ticketed_event=baker.make_recipe(
                'booking.ticketed_event_max10', name='Test event'
            ),
            user=baker.make_recipe('booking.user', username='Test user'),
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
        booking = baker.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            purchase_confirmed=True
        )
        baker.make(
            Ticket, ticket_booking=booking,
            _quantity=10)

        self.assertEqual(self.ticketed_event.tickets_left(), 0)
        with self.assertRaises(TicketBookingError):
            TicketBooking.objects.create(
                ticketed_event=self.ticketed_event,
                user=baker.make_recipe('booking.user')
            )

    def test_booking_reference_set(self):
        ticket_booking = baker.make(
            TicketBooking,
            purchase_confirmed=True,
            ticketed_event=baker.make_recipe(
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
        ticketed_event = baker.make_recipe('booking.ticketed_event_max10')
        booking = baker.make(
            TicketBooking, ticketed_event=ticketed_event,
            purchase_confirmed=True
        )
        baker.make(
            Ticket, ticket_booking=booking,
            _quantity=10)
        self.assertEqual(ticketed_event.tickets_left(), 0)

        with self.assertRaises(TicketBookingError):
            Ticket.objects.create(ticket_booking=booking)


class BlockTypeTests(TestCase):

    def test_cannot_create_multiple_free_class_block_types(self):
        ev_type = baker.make_recipe('booking.event_type_PC')
        baker.make(BlockType, event_type=ev_type, identifier='free class', duration=1)
        self.assertEqual(BlockType.objects.count(), 1)

        with self.assertRaises(BlockTypeError):
            baker.make(BlockType, event_type=ev_type, identifier='free class', duration=1)
        self.assertEqual(BlockType.objects.count(), 1)

    def test_cannot_create_multiple_transfer_block_types(self):
        ev_type = baker.make_recipe('booking.event_type_PC')
        baker.make(BlockType, event_type=ev_type, identifier='transferred', duration=1)
        self.assertEqual(BlockType.objects.count(), 1)

        with self.assertRaises(BlockTypeError):
            baker.make(BlockType, event_type=ev_type, identifier='transferred', duration=1)
        self.assertEqual(BlockType.objects.count(), 1)

    def test_cann_create_transfer_block_types_for_different_events(self):
        pc_ev_type = baker.make_recipe('booking.event_type_PC')
        pp_ev_type = baker.make_recipe('booking.event_type_PP')

        baker.make(BlockType, event_type=pc_ev_type, identifier='transferred', duration=1)
        self.assertEqual(BlockType.objects.count(), 1)

        baker.make(BlockType, event_type=pp_ev_type, identifier='transferred', duration=1)
        self.assertEqual(BlockType.objects.count(), 2)

    @override_settings(TESTING=False)
    def test_block_type_duration(self):
        pc_ev_type = baker.make_recipe('booking.event_type_PC')
        with pytest.raises(
            ValidationError, 
            match=r"A block type must have a duration or duration_weeks"
        ) as e:
                BlockType.objects.create(
                    event_type=pc_ev_type, size=1, cost=10
                )

        with pytest.raises(
            ValidationError, 
            match=r"A block type must have a duration or duration_weeks \(not both\)"
        ):
            BlockType.objects.create(
                event_type=pc_ev_type, duration=2, duration_weeks=2, size=1, cost=10
            )


class VoucherTests(TestCase):

    @patch('booking.models.booking_models.timezone')
    def test_voucher_dates(self, mock_tz):
        mock_now = datetime(
            2016, 1, 5, 16, 30, 30, 30, tzinfo=dt_timezone.utc
        )
        mock_tz.now.return_value = mock_now
        voucher = baker.make(EventVoucher, start_date=mock_now)
        self.assertEqual(
            voucher.start_date,
            datetime(2016, 1, 5, 0, 0, 0, 0, tzinfo=dt_timezone.utc)
        )

        voucher.expiry_date = datetime(
            2016, 1, 6, 18, 30, 30, 30, tzinfo=dt_timezone.utc
        )
        voucher.save()
        self.assertEqual(
            voucher.expiry_date,
            datetime(2016, 1, 6, 23, 59, 59, 0, tzinfo=dt_timezone.utc)
        )

    @patch('booking.models.booking_models.timezone')
    def test_has_expired(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2016, 1, 5, 12, 30, tzinfo=dt_timezone.utc
        )

        voucher = baker.make(
            EventVoucher,
            start_date=datetime(2016, 1, 1, tzinfo=dt_timezone.utc),
            expiry_date=datetime(2016, 1, 4, tzinfo=dt_timezone.utc)
        )
        self.assertTrue(voucher.has_expired)

        mock_tz.now.return_value = datetime(
            2016, 1, 3, 12, 30, tzinfo=dt_timezone.utc
        )
        # get voucher from id b/c has_expired is cached property
        voucher = EventVoucher.objects.get(id=voucher.id)
        self.assertFalse(voucher.has_expired)

    @patch('booking.models.booking_models.timezone')
    def test_has_started(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2016, 1, 5, 12, 30, tzinfo=dt_timezone.utc
        )

        voucher = baker.make(
            EventVoucher,
            start_date=datetime(2016, 1, 1, tzinfo=dt_timezone.utc),
        )
        self.assertTrue(voucher.has_started)

        voucher.start_date = datetime(2016, 1, 6, tzinfo=dt_timezone.utc)
        voucher.save()
        # get voucher from id b/c has_started is cached property
        voucher = EventVoucher.objects.get(id=voucher.id)
        self.assertFalse(voucher.has_started)

    def test_check_event_type(self):
        voucher = baker.make(EventVoucher)
        pc_event_type = baker.make_recipe('booking.event_type_PC')
        pp_event_type = baker.make_recipe('booking.event_type_PP')
        ws_event_type = baker.make_recipe('booking.event_type_WS')
        voucher.event_types.add(pp_event_type)
        voucher.event_types.add(pc_event_type)

        assert not voucher.check_event_type(ws_event_type)
        assert voucher.check_event_type(pc_event_type)
        assert voucher.check_event_type(pp_event_type)

        assert list(voucher.valid_for().order_by("id")) == [pc_event_type, pp_event_type]

    def test_check_block_type(self):
        voucher = baker.make(BlockVoucher)
        block_type1 = baker.make_recipe('booking.blocktype')
        block_type2 = baker.make_recipe('booking.blocktype')
        block_type3 = baker.make_recipe('booking.blocktype')
        voucher.block_types.add(block_type1)
        voucher.block_types.add(block_type2)

        self.assertFalse(voucher.check_block_type(block_type3))
        self.assertTrue(voucher.check_block_type(block_type1))
        self.assertTrue(voucher.check_block_type(block_type2))

    def test_str(self):
        voucher = baker.make(EventVoucher, code="testcode")
        self.assertEqual(str(voucher), 'testcode')


class GiftVoucherTypeTests(TestCase):

    def test_event_type_or_block_type_required(self):

        block_type = baker.make_recipe("booking.blocktype5")
        event_type = baker.make_recipe("booking.event_type_PC")

        with pytest.raises(ValidationError):
            gift_voucher = GiftVoucherType.objects.create()
            gift_voucher.clean()

        with pytest.raises(ValidationError):
            gift_voucher = GiftVoucherType.objects.create(event_type=event_type, block_type=block_type)
            gift_voucher.clean()

    def test_gift_voucher_cost(self):
        block_type = baker.make_recipe("booking.blocktype5", cost=40)
        gift_voucher_type = GiftVoucherType.objects.create(block_type=block_type)
        assert gift_voucher_type.cost == 40


@pytest.mark.django_db
def test_banner_str():
    banner = baker.make(Banner, content="test")
    # defaults to all type
    assert str(banner) == "banner_all"


@pytest.mark.django_db
def test_filter_category_str():
    category = baker.make(FilterCategory, category="test category")
    assert str(category) == "test category"


@pytest.mark.django_db
def test_allowed_group_create():
    gp = AllowedGroup.create_with_group(group_name="foo", description="foo group")
    assert gp.description == "foo group"
    assert Group.objects.filter(name="foo").exists()


@pytest.mark.django_db
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_event_has_permission_to_book(configured_user, purchasable_membership):
    gp = AllowedGroup.create_with_group(group_name="foo", description="foo group")
    event = baker.make_recipe("booking.future_PC")
    restricted_event = baker.make_recipe("booking.future_PC", allowed_group_override=gp)
    members_only_event = baker.make_recipe("booking.future_PC", members_only=True)
    
    member = baker.make(User)
    baker.make("booking.UserMembership", user=member, membership=purchasable_membership, subscription_status="active")

    allowed_user = baker.make(User)
    gp.add_user(allowed_user)

    assert event.has_permission_to_book(configured_user)
    assert not restricted_event.has_permission_to_book(configured_user)
    assert not members_only_event.has_permission_to_book(configured_user)

    assert event.has_permission_to_book(allowed_user)
    assert restricted_event.has_permission_to_book(allowed_user)
    assert not members_only_event.has_permission_to_book(allowed_user)

    assert event.has_permission_to_book(member)
    assert not restricted_event.has_permission_to_book(member)
    assert members_only_event.has_permission_to_book(member)



