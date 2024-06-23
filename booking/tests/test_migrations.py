from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

import pytest

from django.utils import timezone

from django_migration_testcase import MigrationTest


@pytest.mark.skip(reason="Old migration tests")
class VoucherMigrationTests(MigrationTest):

    before = [
        ('auth', '0007_alter_validators_add_error_messages'),
        ('booking', '0047_auto_20160413_1703')
    ]
    after = [
        ('auth', '0007_alter_validators_add_error_messages'),
        ('booking', '0050_auto_20160707_2143')
    ]

    def test_data_migration_voucher_to_event_voucher(self):
        # get pre-migration models
        User = self.get_model_before('auth.User')
        EventType = self.get_model_before('booking.EventType')
        Voucher = self.get_model_before('booking.Voucher')


        # set up pre-migration data
        event_type1 = EventType.objects.create(
            event_type='CL', subtype='Pole level class'
        )
        event_type2 = EventType.objects.create(
            event_type='EV', subtype='Workshop'
        )
        event_type3 = EventType.objects.create(
            event_type='RH', subtype='Room hire'
        )
        event_type4 = EventType.objects.create(
            event_type='CL', subtype='Class not on voucher'
        )
        user1 = User.objects.create(
            username='user1', password='user1', email='user1@test.com'
        )
        user2 = User.objects.create(
            username='user2', password='user2', email='user2@test.com'
        )
        user3 = User.objects.create(
            username='user3', password='user3', email='user3@test.com'
        )
        user4 = User.objects.create(
            username='user4', password='user4', email='user4@test.com'
        )
        voucher = Voucher.objects.create(
            code='test', discount=10,
            start_date=datetime(2016, 1, 1, tzinfo=dt_timezone.utc),
            expiry_date=datetime(2016, 2, 1, tzinfo=dt_timezone.utc),
            max_vouchers=5
        )
        voucher1 = Voucher.objects.create(
            code='test1', discount=5,
            start_date=datetime(2016, 3, 1, tzinfo=dt_timezone.utc),
            expiry_date=datetime(2016, 4, 1, tzinfo=dt_timezone.utc),
            max_vouchers=6
        )
        voucher.event_types.add(event_type1)
        voucher.event_types.add(event_type2)
        voucher.users.add(user1.id)
        voucher.users.add(user2.id)
        voucher1.event_types.add(event_type3)
        voucher1.users.add(user3.id)

        # run migration
        self.run_migration()

        # get post-migration models
        User = self.get_model_after('auth.User')
        EventType = self.get_model_after('booking.EventType')
        EventVoucher = self.get_model_after('booking.EventVoucher')
        BlockVoucher = self.get_model_after('booking.BlockVoucher')
        UsedEventVoucher = self.get_model_after('booking.UsedEventVoucher')

        user1_after = User.objects.get(username='user1')
        user2_after = User.objects.get(username='user2')
        user3_after = User.objects.get(username='user3')
        user4_after = User.objects.get(username='user4')
        ev_type1_after = EventType.objects.get(subtype='Pole level class')
        ev_type2_after = EventType.objects.get(subtype='Workshop')
        ev_type3_after = EventType.objects.get(subtype='Room hire')
        ev_type4_after = EventType.objects.get(subtype='Class not on voucher')

        # check data
        # 2 EventVouchers; details match voucher and voucher1
        self.assertEqual(EventVoucher.objects.count(), 2)
        evoucher = EventVoucher.objects.get(code='test')
        evoucher1 = EventVoucher.objects.get(code='test1')
        self.assertEqual(evoucher.discount, 10)
        self.assertEqual(
            evoucher.start_date, datetime(2016, 1, 1, tzinfo=dt_timezone.utc)
        )
        self.assertEqual(
            evoucher.expiry_date, datetime(2016, 2, 1, tzinfo=dt_timezone.utc)
        )
        self.assertEqual(evoucher.max_vouchers, 5)
        # max per user is set to the default (1)
        self.assertEqual(evoucher.max_per_user, 1)

        self.assertEqual(evoucher1.discount, 5)
        self.assertEqual(
            evoucher1.start_date, datetime(2016, 3, 1, tzinfo=dt_timezone.utc)
        )
        self.assertEqual(
            evoucher1.expiry_date, datetime(2016, 4, 1, tzinfo=dt_timezone.utc)
        )
        self.assertEqual(evoucher1.max_vouchers, 6)
        # max per user is set to the default (1)
        self.assertEqual(evoucher1.max_per_user, 1)

        # 2 UsedEventVouchers for voucher/user1 and user2
        # 1 UsedEventVoucher for voucher1/user3
        self.assertEqual(UsedEventVoucher.objects.count(), 3)
        ev_used_vouchers = UsedEventVoucher.objects.filter(voucher=evoucher)
        self.assertEqual(
            sorted([usedvoucher.user.id for usedvoucher in ev_used_vouchers]),
            sorted([user1_after.id, user2_after.id])
        )
        ev1_used_vouchers = UsedEventVoucher.objects.filter(voucher=evoucher1)
        self.assertEqual(
            [usedvoucher.user.id for usedvoucher in ev1_used_vouchers],
            [user3_after.id]
        )
        with self.assertRaises(UsedEventVoucher.DoesNotExist):
            UsedEventVoucher.objects.get(user=user4_after.id)

        self.assertEqual(
            sorted([et.id for et in evoucher.event_types.all()]),
            sorted([ev_type1_after.id, ev_type2_after.id])
        )
        self.assertEqual(
            sorted([et.id for et in evoucher1.event_types.all()]),
            [ev_type3_after.id]
        )

        # no BlockVouchers
        self.assertEqual(BlockVoucher.objects.count(), 0)


@pytest.mark.skip(reason="Old migration tests")
class DateWarningSentMigrationTests(MigrationTest):

    before = [
        ('auth', '0011_update_proxy_permissions'),
        ('payments', '0011_auto_20180104_1301'),
        ('booking', '0060_blocktype_assign_free_class_on_completion')
    ]
    after = [
        ('auth', '0011_update_proxy_permissions'),
        ('payments', '0012_add_paypalgiftvouchertransaction'),
        ('booking', '0064_auto_20191123_0800')
    ]

    def test_data_migration_booking_date_warning_sent(self):
        # get pre-migration models
        User = self.get_model_before('auth.User')
        EventType = self.get_model_before('booking.EventType')
        Event = self.get_model_before('booking.Event')
        Booking = self.get_model_before('booking.Booking')


        # set up pre-migration data
        event_type = EventType.objects.create(
            event_type='CL', subtype='Pole level class'
        )

        user1 = User.objects.create(username='user1', password='user1', email='user1@test.com')
        user2 = User.objects.create(username='user2', password='user2', email='user2@test.com')
        user3 = User.objects.create(username='user3', password='user3', email='user3@test.com')
        user4 = User.objects.create(username='user4', password='user4', email='user4@test.com')
        user5 = User.objects.create(username='user5', password='user4', email='user4@test.com')
        future_event = Event.objects.create(
            event_type=event_type,
            date=timezone.now() + timedelta(days=7),
            cost=10,
            advance_payment_required=True,
            payment_open=True,
            booking_open=True
        )
        past_event = Event.objects.create(
            event_type=event_type,
            date=timezone.now() - timedelta(days=7),
            cost=10,
            advance_payment_required=True,
            payment_open=True,
            booking_open=True
        )
        # past_booking_with_warning - no warning date added
        Booking.objects.create(event=past_event, user=user1, paid=False, warning_sent=True)
        # open_unpaid_booking_without_warning - past_booking_with_warning - no warning date added
        Booking.objects.create(user=user2, event=future_event, paid=False, warning_sent=False)
        # open_paid_booking_with_warning - past_booking_with_warning - no warning date added
        Booking.objects.create(user=user3, event=future_event, paid=True, warning_sent=True)
        # cancelled_unpaid_booking_with_warning - past_booking_with_warning - no warning date added
        Booking.objects.create(
            user=user4, event=future_event, paid=False, warning_sent=True, status="CANCELLED"
        )

        # open_unpaid_booking_with_warning - warning date added
        Booking.objects.create(user=user5, event=future_event, paid=False, warning_sent=True)

        # run migration
        self.run_migration()

        # get post-migration models
        User = self.get_model_after('auth.User')
        Booking = self.get_model_after('booking.Booking')

        user1_after = User.objects.get(username='user1')
        user2_after = User.objects.get(username='user2')
        user3_after = User.objects.get(username='user3')
        user4_after = User.objects.get(username='user4')
        user5_after = User.objects.get(username='user5')

        # no warning date added
        no_warning_date_added = Booking.objects.filter(user__in=[user1_after, user2_after, user3_after, user4_after])
        # warning date added
        open_unpaid_booking_with_warning_after = Booking.objects.get(user=user5_after)

        # check data
        for booking in no_warning_date_added:
            self.assertIsNone(booking.date_warning_sent)

        self.assertIsNotNone(open_unpaid_booking_with_warning_after.date_warning_sent)

    def test_data_migration_ticket_booking_date_warning_sent(self):
        # get pre-migration models
        User = self.get_model_before('auth.User')
        TicketedEvent = self.get_model_before('booking.TicketedEvent')
        TicketBooking = self.get_model_before('booking.TicketBooking')

        # set up pre-migration data
        user1 = User.objects.create(username='user1', password='user1', email='user1@test.com')
        user2 = User.objects.create(username='user2', password='user2', email='user2@test.com')
        user3 = User.objects.create(username='user3', password='user3', email='user3@test.com')
        user4 = User.objects.create(username='user4', password='user4', email='user4@test.com')
        user5 = User.objects.create(username='user5', password='user4', email='user4@test.com')
        future_event = TicketedEvent.objects.create(
            date=timezone.now() + timedelta(days=7),
            ticket_cost=10,
            advance_payment_required=True,
            payment_open=True,
        )
        past_event = TicketedEvent.objects.create(
            date=timezone.now() - timedelta(days=7),
            ticket_cost=10,
            advance_payment_required=True,
            payment_open=True,
        )
        # past_booking_with_warning - no warning date added
        TicketBooking.objects.create(ticketed_event=past_event, user=user1, paid=False, warning_sent=True)
        # future_unpaid_booking_without_warning - no warning date added
        TicketBooking.objects.create(user=user2, ticketed_event=future_event, paid=False, warning_sent=False)
        # future_paid_booking_with_warning - no warning date added
        TicketBooking.objects.create(user=user3, ticketed_event=future_event, paid=True, warning_sent=True)
        # cancelled_unpaid_booking_with_warning - past_booking_with_warning - no warning date added
        TicketBooking.objects.create(
            user=user4, ticketed_event=future_event, paid=False, warning_sent=True, cancelled=True
        )

        # open_unpaid_booking_with_warning - warning date added
        TicketBooking.objects.create(user=user5, ticketed_event=future_event, paid=False, warning_sent=True)

        # run migration
        self.run_migration()

        # get post-migration models
        User = self.get_model_after('auth.User')
        TicketBooking = self.get_model_after('booking.TicketBooking')

        user1_after = User.objects.get(username='user1')
        user2_after = User.objects.get(username='user2')
        user3_after = User.objects.get(username='user3')
        user4_after = User.objects.get(username='user4')
        user5_after = User.objects.get(username='user5')

        # no warning date added
        no_warning_date_added = TicketBooking.objects.filter(user__in=[user1_after, user2_after, user3_after, user4_after])
        # warning date added
        open_unpaid_booking_with_warning_after = TicketBooking.objects.get(user=user5_after)

        # check data
        for booking in no_warning_date_added:
            self.assertIsNone(booking.date_warning_sent)

        self.assertIsNotNone(open_unpaid_booking_with_warning_after.date_warning_sent)
