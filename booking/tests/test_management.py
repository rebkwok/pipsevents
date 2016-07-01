import sys

from datetime import datetime, timedelta
from io import StringIO
from mock import patch
from model_mommy import mommy

from django.test import TestCase, override_settings
from django.conf import settings
from django.core import management
from django.core import mail
from django.db.models import Q
from django.contrib.auth.models import Group, User
from django.utils import timezone

from allauth.socialaccount.models import SocialApp

from activitylog.models import ActivityLog
from booking.models import Event, Block, Booking, EventType, BlockType, \
    TicketBooking, Ticket
from payments.models import PaypalBookingTransaction


class ManagementCommandsTests(TestCase):

    def setUp(self):
        # redirect stdout so we can test it
        self.output = StringIO()
        self.saved_stdout = sys.stdout
        sys.stdout = self.output

    def tearDown(self):
        self.output.close()
        sys.stdout = self.saved_stdout

    def test_setup_fb(self):
        self.assertEquals(SocialApp.objects.all().count(), 0)
        management.call_command('setup_fb')
        self.assertEquals(SocialApp.objects.all().count(), 1)

    def test_load_users(self):
        self.assertEquals(User.objects.all().count(), 0)
        management.call_command('load_users')
        self.assertEquals(User.objects.all().count(), 6)

    def test_load_users_existing_superuser(self):
        suser = mommy.make_recipe(
            'booking.user', username='admin', email='admin@admin.com'
        )
        suser.is_superuser = True
        suser.save()
        self.assertEquals(User.objects.all().count(), 1)
        management.call_command('load_users')
        self.assertEquals(User.objects.all().count(), 6)

        self.assertEqual(
            self.output.getvalue(),
            'Trying to create superuser...\n'
            'Superuser with username "admin" already exists\n'
            'Creating 5 test users\n'
        )

    def test_create_events(self):
        self.assertEquals(Event.objects.all().count(), 0)
        management.call_command('create_events')
        self.assertEquals(Event.objects.all().count(), 5)

    @patch('booking.utils.date')
    def test_create_classes_with_manage_command(self, mock_date):
        """
        Create timetable sessions and add classes
        """
        mock_date.today.return_value = datetime(2015, 2, 10)

        self.assertEquals(Event.objects.all().count(), 0)
        management.call_command('create_classes')
        # check that there are now classes on the Monday of the mocked week
        # (mocked now is Wed 10 Feb 2015)
        mon_classes = Event.objects.filter(
            Q(date__gte=datetime(2015, 2, 10, tzinfo=timezone.utc)) &
            Q(date__lte=datetime(2015, 2, 11, tzinfo=timezone.utc))
        )
        self.assertTrue(mon_classes)
        # check that there are now classes on the Monday of the following week
        # (mocked now is Wed 10 Feb 2015)
        next_mon_classes = Event.objects.filter(
            Q(date__gte=datetime(2015, 2, 17, tzinfo=timezone.utc)) &
            Q(date__lte=datetime(2015, 2, 18, tzinfo=timezone.utc))
        )
        self.assertTrue(next_mon_classes)

    def test_create_bookings(self):
        """
        test that create_bookings creates 3 bookings per event
        """
        mommy.make_recipe('booking.user', _quantity=3)
        mommy.make_recipe('booking.future_EV', _quantity=2)
        self.assertEquals(Booking.objects.all().count(), 0)
        management.call_command('create_bookings')
        self.assertEquals(Booking.objects.all().count(), 6)

    def test_create_bookings_without_users(self):
        """
        test that create_bookings creates users if none exist
        """
        mommy.make_recipe('booking.future_EV')
        self.assertEquals(Booking.objects.all().count(), 0)
        self.assertEquals(User.objects.all().count(), 0)
        management.call_command('create_bookings')
        self.assertEquals(Booking.objects.all().count(), 3)
        self.assertEquals(User.objects.all().count(), 6)

    def test_create_bookings_without_events(self):
        """
        test that create_bookings handles being called when there are no events
        """
        self.assertEquals(Booking.objects.all().count(), 0)

        management.call_command('create_bookings')
        # confirm no errors, and no booking are created
        self.assertEquals(Booking.objects.all().count(), 0)

    def test_create_events_and_blocktypes(self):
        """
        test that create_events_and_blocktypes creates the default types
        """
        self.assertEquals(EventType.objects.all().count(), 0)
        self.assertEquals(BlockType.objects.all().count(), 0)

        management.call_command('create_event_and_blocktypes')
        self.assertEquals(EventType.objects.all().count(), 10)
        self.assertEquals(BlockType.objects.all().count(), 7)

    def test_create_events_and_blocktypes_twice(self):
        """
        test that create_events_and_blocktypes does not create duplicates
        """
        self.assertEquals(EventType.objects.all().count(), 0)
        self.assertEquals(BlockType.objects.all().count(), 0)

        management.call_command('create_event_and_blocktypes')
        self.assertEquals(EventType.objects.all().count(), 10)
        self.assertEquals(BlockType.objects.all().count(), 7)

        management.call_command('create_event_and_blocktypes')
        self.assertEquals(EventType.objects.all().count(), 10)
        self.assertEquals(BlockType.objects.all().count(), 7)


class EmailReminderAndWarningTests(TestCase):

    @patch('booking.management.commands.email_reminders.timezone')
    def test_email_reminders(self, mock_tz):
        """
        Email reminders 24 hours before cancellation period starts
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 10, 19, 0, tzinfo=timezone.utc
            )

        # cancellation period starts 2015/2/11 18:00
        event = mommy.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 12, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            cost=10,
            cancellation_period=24)
        # cancellation period starts 2015/2/12 18:00
        event1 = mommy.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 13, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            cost=10,
            cancellation_period=24)
        mommy.make_recipe(
            'booking.booking', event=event, _quantity=5,
            )
        mommy.make_recipe(
            'booking.booking', event=event1, _quantity=5,
            )
        management.call_command('email_reminders')
        # emails are only sent for event1
        self.assertEquals(len(mail.outbox), 5)

    @patch('booking.management.commands.email_reminders.timezone')
    def test_email_reminders_not_sent_for_past_events(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 2, 10, tzinfo=timezone.utc
            )

        # cancellation period starts 2015/2/8 00:00
        event = mommy.make_recipe(
            'booking.past_event',
            date=datetime(2015, 2, 9, tzinfo=timezone.utc),
            payment_open=True,
            cost=10,
            cancellation_period=24)

        mommy.make_recipe(
            'booking.booking', event=event, _quantity=5,
            )
        management.call_command('email_reminders')
        self.assertEquals(len(mail.outbox), 0)

    @patch('booking.management.commands.email_reminders.timezone')
    def test_email_reminders_not_sent_twice(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 19, 0, tzinfo=timezone.utc
            )

        # cancellation period starts 2015/2/12 18:00
        event = mommy.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 13, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            cost=10,
            cancellation_period=24)
        mommy.make_recipe(
            'booking.booking', event=event, _quantity=5,
            )

        management.call_command('email_reminders')
        self.assertEquals(len(mail.outbox), 5)
        # emails are not sent again
        management.call_command('email_reminders')
        self.assertEquals(len(mail.outbox), 5)

    @patch('booking.management.commands.email_reminders.timezone')
    def test_email_reminders_set_flags(self, mock_tz):
        """
        Test that reminder_sent flag set
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 19, 0, tzinfo=timezone.utc
            )

        # cancellation period starts 2015/2/12 18:00
        event = mommy.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 13, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            cost=10,
            cancellation_period=24)
        mommy.make_recipe(
            'booking.booking', event=event, paid=True, payment_confirmed=True,
            )
        management.call_command('email_reminders')
        self.assertEquals(len(mail.outbox), 1)
        self.assertEquals(
            Booking.objects.filter(reminder_sent=True).count(), 1
            )

    @patch('booking.management.commands.email_reminders.timezone')
    def test_email_reminders_only_sent_for_open_bookings(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 2, 12, 19, 0, tzinfo=timezone.utc
            )

        # cancellation period starts 2015/2/11 18:00
        event = mommy.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 13, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            cost=10,
            cancellation_period=24)
        mommy.make_recipe(
            'booking.booking', event=event, status='OPEN', _quantity=5
            )
        mommy.make_recipe(
            'booking.booking', event=event, status='CANCELLED', _quantity=5
            )
        management.call_command('email_reminders')
        self.assertEquals(len(mail.outbox), 5)
        for booking in Booking.objects.filter(status='OPEN'):
            self.assertTrue(booking.reminder_sent)
        for booking in Booking.objects.filter(status='CANCELLED'):
            self.assertFalse(booking.reminder_sent)

    @patch('booking.management.commands.email_warnings.timezone')
    def test_email_warnings(self, mock_tz):
        """
        test email warning is sent 48 hours before cancellation_period or
        payment_due_date
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 10, 0, 0, tzinfo=timezone.utc
            )

        # cancellation period starts 2015/2/14 17:00
        # payment_due_date 2015/2/11 23:59
        event = mommy.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=timezone.utc),
            cancellation_period=1)
        # cancellation period starts 2015/2/14 17:00
        # payment_due_date 2015/2/12 23:59
        event1 = mommy.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            cost=10,
            payment_due_date=datetime(2015, 2, 12, tzinfo=timezone.utc),
            cancellation_period=1)
        mommy.make_recipe(
            'booking.booking', event=event, paid=False,
            payment_confirmed=False,
            date_booked=datetime(2015, 2, 9, 19, 30, tzinfo=timezone.utc),
            _quantity=5,
            )
        mommy.make_recipe(
            'booking.booking', event=event1, paid=False,
            payment_confirmed=False,
            date_booked=datetime(2015, 2, 9, 19, 30, tzinfo=timezone.utc),
            _quantity=5,
            )

        management.call_command('email_warnings')
        self.assertEquals(len(mail.outbox), 5)

    @patch('booking.management.commands.email_warnings.timezone')
    def test_email_warnings_sent_if_no_payment_due_date(self, mock_tz):
        """
        test email warning is sent 48 hours before cancellation_period for
        events with no payment_due_date
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 19, 0, tzinfo=timezone.utc
            )

        # cancellation period starts 2015/2/13 18:00
        # payment_due_date None
        event = mommy.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            cost=10,
            payment_due_date=None,
            cancellation_period=24)

        mommy.make_recipe(
            'booking.booking', event=event, paid=False,
            payment_confirmed=False,
            date_booked=datetime(2015, 2, 11, 14, 30, tzinfo=timezone.utc),
            _quantity=5,
            )

        management.call_command('email_warnings')
        self.assertEquals(len(mail.outbox), 5)

    @patch('booking.management.commands.email_warnings.timezone')
    def test_email_warnings_sent_for_booking_made_after_payment_due_date(
            self, mock_tz
    ):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 19, 0, tzinfo=timezone.utc
            )

        # No cancellation period
        # payment_due_date is in the past
        # # SEND WARNING
        event = mommy.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            cost=10,
            payment_due_date=datetime(2015, 2, 10, 18, 0, tzinfo=timezone.utc),
            cancellation_period=0)

        mommy.make_recipe(
            'booking.booking', event=event, paid=False,
            payment_confirmed=False,
            date_booked=datetime(2015, 2, 11, 14, 30, tzinfo=timezone.utc),
            )

        # Has cancellation period starts 2015/2/13 18:00 (<48 hrs from now)
        # payment_due_date is in the past
        # SEND WARNING
        event1 = mommy.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            cost=10,
            payment_due_date=datetime(2015, 2, 10, 18, 0, tzinfo=timezone.utc),
            cancellation_period=24)
        mommy.make_recipe(
            'booking.booking', event=event1, paid=False,
            payment_confirmed=False,
            date_booked=datetime(2015, 2, 11, 14, 30, tzinfo=timezone.utc),
            )

        # Has cancellation period starts 2015/2/13 18:00 (>48 hrs from now)
        # payment_due_date is in the past
        # SEND WARNING (ignore cancellation period if payment due date)
        event2 = mommy.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            cost=10,
            payment_due_date=datetime(2015, 2, 10, 18, 0, tzinfo=timezone.utc),
            cancellation_period=24)
        mommy.make_recipe(
            'booking.booking', event=event2, paid=False,
            payment_confirmed=False,
            date_booked=datetime(2015, 2, 11, 14, 30, tzinfo=timezone.utc),
            )

        management.call_command('email_warnings')
        self.assertEquals(len(mail.outbox), 3)

        for booking in Booking.objects.all():
            self.assertTrue(booking.warning_sent)

    @patch('booking.management.commands.email_warnings.timezone')
    def test_email_warnings_not_sent_twice(self, mock_tz):

        mock_tz.now.return_value = datetime(
            2015, 2, 10, tzinfo=timezone.utc
            )
        # cancellation period starts 2015/2/13 17:00
        # payment_due_date 2015/2/11 23:59
        event = mommy.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 13, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=timezone.utc),
            cancellation_period=1)
        mommy.make_recipe(
            'booking.booking', event=event, paid=False,
            payment_confirmed=False,
            date_booked=datetime(2015, 2, 9, 19, 30, tzinfo=timezone.utc),
            _quantity=5,
            )
        management.call_command('email_warnings')
        self.assertEquals(len(mail.outbox), 5)
        for booking in Booking.objects.all():
            self.assertTrue(booking.warning_sent)

        # no additional emails sent on subsequent calls
        management.call_command('email_warnings')
        self.assertEquals(len(mail.outbox), 5)

    @patch('booking.management.commands.email_warnings.timezone')
    def test_email_warnings_only_sent_for_payment_not_confirmed(self, mock_tz):
        """
        test email warning is only sent for bookings that are not marked as
        payment_confirmed
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 10, tzinfo=timezone.utc
            )
        # cancellation period starts 2015/2/13 17:00
        # payment_due_date 2015/2/11 23:59
        event = mommy.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 13, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=timezone.utc),
            cancellation_period=1)
        mommy.make_recipe(
            'booking.booking', event=event, paid=False,
            payment_confirmed=False,
            date_booked=datetime(2015, 2, 9, 19, 30, tzinfo=timezone.utc),
            _quantity=3,
            )
        mommy.make_recipe(
            'booking.booking', event=event, paid=True,
            payment_confirmed=True,
            date_booked=datetime(2015, 2, 9, 19, 30, tzinfo=timezone.utc),
            _quantity=3,
            )
        management.call_command('email_warnings')
        self.assertEquals(len(mail.outbox), 3)
        for booking in Booking.objects.filter(payment_confirmed=False):
            self.assertTrue(booking.warning_sent)
        for booking in Booking.objects.filter(payment_confirmed=True):
            self.assertFalse(booking.warning_sent)

    @patch('booking.management.commands.email_warnings.timezone')
    def test_email_warnings_only_sent_for_open_bookings(self, mock_tz):
        """
        test email warning is only sent for bookings that are not marked as
        payment_confirmed
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 10, tzinfo=timezone.utc
            )
        event = mommy.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 13, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=timezone.utc),
            cancellation_period=1)
        mommy.make_recipe(
            'booking.booking', event=event, paid=False,
            payment_confirmed=False, status='OPEN',
            date_booked=datetime(2015, 2, 9, 19, 30, tzinfo=timezone.utc),
            _quantity=3,
            )
        mommy.make_recipe(
            'booking.booking', event=event, paid=False,
            payment_confirmed=False, status='CANCELLED',
            date_booked=datetime(2015, 2, 9, 19, 30, tzinfo=timezone.utc),
            _quantity=3,
            )
        management.call_command('email_warnings')
        self.assertEquals(len(mail.outbox), 3)
        for booking in Booking.objects.filter(status='OPEN'):
            self.assertTrue(booking.warning_sent)
        for booking in Booking.objects.filter(status='CANCELLED'):
            self.assertFalse(booking.warning_sent)

    @patch('booking.management.commands.email_warnings.timezone')
    def test_email_warnings_not_sent_within_2_hrs_of_booking(self, mock_tz):
        """
        test email warning is only sent for bookings made more than 2 hrs ago
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 10, tzinfo=timezone.utc
            )
        event = mommy.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 13, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=timezone.utc),
            cancellation_period=1)
        booking1 = mommy.make_recipe(
            'booking.booking', event=event, paid=False,
            payment_confirmed=False, status='OPEN',
            date_booked=datetime(2015, 2, 9, 21, 30, tzinfo=timezone.utc)
            )
        booking2 = mommy.make_recipe(
            'booking.booking', event=event, paid=False,
            payment_confirmed=False, status='OPEN',
            date_booked=datetime(2015, 2, 9, 22, 30, tzinfo=timezone.utc)
            )
        management.call_command('email_warnings')
        self.assertEquals(len(mail.outbox), 1)
        booking1.refresh_from_db()
        booking2.refresh_from_db()
        self.assertTrue(booking1.warning_sent)
        self.assertFalse(booking2.warning_sent)


class CancelUnpaidBookingsTests(TestCase):

    def setUp(self):
        self.event = mommy.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 13, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            cost=10,
            payment_due_date=datetime(2015, 2, 9, tzinfo=timezone.utc),
            advance_payment_required=True,
            cancellation_period=1)
        self.unpaid = mommy.make_recipe(
            'booking.booking', event=self.event, paid=False,
            payment_confirmed=False, status='OPEN',
            user__email="unpaid@test.com",
            date_booked=datetime(
                2015, 2, 9, 18, 0, tzinfo=timezone.utc
            ),
            warning_sent=True
        )
        self.paid = mommy.make_recipe(
            'booking.booking', event=self.event, paid=True,
            payment_confirmed=True, status='OPEN',
            user__email="paid@test.com",
            date_booked= datetime(
                2015, 2, 9, 18, 0, tzinfo=timezone.utc
            )
        )

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_cancel_unpaid_bookings(self, mock_tz):
        """
        test unpaid bookings are cancelled
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 10, tzinfo=timezone.utc
        )
        self.assertEquals(
            self.unpaid.status, 'OPEN', self.unpaid.status
        )
        self.assertEquals(
            self.paid.status, 'OPEN', self.paid.status
        )
        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        unpaid_booking = Booking.objects.get(id=self.unpaid.id)
        paid_booking = Booking.objects.get(id=self.paid.id)
        self.assertEquals(len(mail.outbox), 2)
        self.assertEquals(
            unpaid_booking.status, 'CANCELLED', unpaid_booking.status
        )
        self.assertEquals(
            paid_booking.status, 'OPEN', paid_booking.status
        )

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_dont_cancel_if_advance_payment_not_required(self, mock_tz):
        """
        test unpaid bookings are not cancelled if advance payment not required
        for event
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 10, tzinfo=timezone.utc
        )
        # set payment_due_date to None, otherwise advance_payment_required is
        # automatically set to True
        self.event.payment_due_date = None
        self.event.advance_payment_required = False
        self.event.save()
        self.assertEquals(
            self.unpaid.status, 'OPEN', self.unpaid.status
        )
        self.assertEquals(
            self.paid.status, 'OPEN', self.paid.status
        )
        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        unpaid_booking = Booking.objects.get(id=self.unpaid.id)
        paid_booking = Booking.objects.get(id=self.paid.id)
        self.assertEquals(len(mail.outbox), 0)
        self.assertEquals(
            unpaid_booking.status, 'OPEN', unpaid_booking.status
        )
        self.assertEquals(
            paid_booking.status, 'OPEN', paid_booking.status
        )

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_dont_cancel_for_events_with_no_cost(self, mock_tz):
        """
        test unpaid bookings are not cancelled if advance payment not required
        for event
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 10, tzinfo=timezone.utc
        )
        self.event.cost = 0
        self.event.save()
        self.assertEquals(
            self.unpaid.status, 'OPEN', self.unpaid.status
        )
        self.assertEquals(
            self.paid.status, 'OPEN', self.paid.status
        )
        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        unpaid_booking = Booking.objects.get(id=self.unpaid.id)
        paid_booking = Booking.objects.get(id=self.paid.id)
        self.assertEquals(len(mail.outbox), 0)
        self.assertEquals(
            unpaid_booking.status, 'OPEN', unpaid_booking.status
        )
        self.assertEquals(
            paid_booking.status, 'OPEN', paid_booking.status
        )

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_dont_cancel_for_events_in_the_past(self, mock_tz):
        """
        test don't cancel or send emails for past events
        """
        mock_tz.now.return_value = datetime(
            2016, 2, 10, tzinfo=timezone.utc
        )
        self.assertEquals(
            self.unpaid.status, 'OPEN', self.unpaid.status
        )
        self.assertEquals(
            self.paid.status, 'OPEN', self.paid.status
        )
        self.assertTrue(timezone.now() > self.event.date)
        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking and studio once
        # for all cancelled bookings
        unpaid_booking = Booking.objects.get(id=self.unpaid.id)
        paid_booking = Booking.objects.get(id=self.paid.id)
        self.assertEquals(len(mail.outbox), 0)
        self.assertEquals(
            unpaid_booking.status, 'OPEN', unpaid_booking.status
        )
        self.assertEquals(
            paid_booking.status, 'OPEN', paid_booking.status
        )

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_dont_cancel_for_already_cancelled(self, mock_tz):
        """
        ignore already cancelled bookings
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 10, tzinfo=timezone.utc
        )
        self.unpaid.status = 'CANCELLED'
        self.unpaid.save()
        self.assertEquals(
            self.unpaid.status, 'CANCELLED', self.unpaid.status
        )
        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking and studio once
        # for all cancelled bookings
        unpaid_booking = Booking.objects.get(id=self.unpaid.id)
        self.assertEquals(len(mail.outbox), 0)
        self.assertEquals(
            unpaid_booking.status, 'CANCELLED', unpaid_booking.status
        )

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_dont_cancel_bookings_created_within_past_6_hours(self, mock_tz):
        """
        Avoid immediately cancelling bookings made within the cancellation
        period to allow time for users to make payments
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 10, 18, 0, tzinfo=timezone.utc
        )

        unpaid_within_6_hrs = mommy.make_recipe(
            'booking.booking', event=self.event, paid=False,
            payment_confirmed=False, status='OPEN',
            user__email="unpaid@test.com",
            date_booked=datetime(
                2015, 2, 10, 12, 30, tzinfo=timezone.utc
            ),
            warning_sent=True
        )
        unpaid_more_than_6_hrs = mommy.make_recipe(
            'booking.booking', event=self.event, paid=False,
            payment_confirmed=False, status='OPEN',
            user__email="unpaid@test.com",
            date_booked=datetime(
                2015, 2, 10, 11, 30, tzinfo=timezone.utc
            ),
            warning_sent=True
        )

        self.assertEquals(unpaid_within_6_hrs.status, 'OPEN')
        self.assertEquals(unpaid_more_than_6_hrs.status, 'OPEN')

        management.call_command('cancel_unpaid_bookings')
        unpaid_within_6_hrs.refresh_from_db()
        unpaid_more_than_6_hrs.refresh_from_db()
        self.assertEquals(unpaid_within_6_hrs.status, 'OPEN')
        self.assertEquals(unpaid_more_than_6_hrs.status, 'CANCELLED')

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_only_send_one_email_to_studio(self, mock_tz):
        """
        users are emailed per booking, studio just receives one summary
        email
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 10, tzinfo=timezone.utc
        )
        for i in range(5):
            bookings = mommy.make_recipe(
                'booking.booking', event=self.event,
                status='OPEN', paid=False,
                payment_confirmed=False,
                user__email="unpaid_user{}@test.com".format(i),
                date_booked= datetime(
                    2015, 2, 9, tzinfo=timezone.utc
                ),
                warning_sent=True
            )

        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking (6) and studio once
        # for all cancelled bookings
        unpaid_booking = Booking.objects.get(id=self.unpaid.id)
        self.assertEquals(len(mail.outbox), 7)
        self.assertEquals(
            unpaid_booking.status, 'CANCELLED', unpaid_booking.status
        )
        self.assertEquals(
            Booking.objects.filter(status='CANCELLED').count(), 6
        )
        cancelled_booking_emails = [
            [booking.user.email] for booking
            in Booking.objects.filter(status='CANCELLED')
        ]
        all_emails = cancelled_booking_emails + [[settings.DEFAULT_STUDIO_EMAIL]]
        self.assertEquals(
            sorted(all_emails),
            sorted([email.to for email in mail.outbox])
        )

    @override_settings(SEND_ALL_STUDIO_EMAILS=False)
    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_no_email_to_studio_if_setting_not_on(self, mock_tz):
        """
        users are emailed per booking, studio just receives one summary
        email
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 10, tzinfo=timezone.utc
        )
        for i in range(5):
            bookings = mommy.make_recipe(
                'booking.booking', event=self.event,
                status='OPEN', paid=False,
                payment_confirmed=False,
                user__email="unpaid_user{}@test.com".format(i),
                date_booked= datetime(
                    2015, 2, 9, tzinfo=timezone.utc
                ),
                warning_sent=True
            )

        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking (6); none to studio
        self.assertEquals(len(mail.outbox), 6)
        cancelled_booking_emails = [
            [booking.user.email] for booking
            in Booking.objects.filter(status='CANCELLED')
        ]
        self.assertEquals(
            sorted(cancelled_booking_emails),
            sorted([email.to for email in mail.outbox])
        )

    @patch('booking.management.commands.cancel_unpaid_bookings.send_mail')
    @patch('booking.management.commands.cancel_unpaid_bookings.'
           'send_waiting_list_email')
    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_email_errors(self, mock_tz, mock_send, mock_send_waiting_list):
        mock_tz.now.return_value = datetime(
            2015, 2, 10, tzinfo=timezone.utc
        )
        mock_send.side_effect = Exception('Error sending email')
        mock_send_waiting_list.side_effect = Exception('Error sending email')
        # make full event (setup has one paid and one unpaid)
        # cancellation period =1, date = 2015, 2, 13, 18, 0
        self.event.max_participants = 2
        self.event.save()
        mommy.make_recipe('booking.waiting_list_user', event=self.event)

        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking, studio and waiting
        # list user; 3 failure emails sent to support
        self.assertEquals(len(mail.outbox), 3)
        for email in mail.outbox:
            self.assertEqual(email.to, [settings.SUPPORT_EMAIL])

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_cancelling_for_full_event_emails_waiting_list(self, mock_tz):
        """
        Test that automatically cancelling a booking for a full event emails
        any users on the waiting list
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 13, 17, 15, tzinfo=timezone.utc
        )

        # make full event (setup has one paid and one unpaid)
        # cancellation period =1, date = 2015, 2, 13, 18, 0
        self.event.max_participants = 2
        self.event.save()

        # make some waiting list users
        for i in range(3):
            mommy.make_recipe(
                'booking.waiting_list_user', event=self.event,
                user__email='test{}@test.com'.format(i)
            )

        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking (1) and
        # one email with bcc to waiting list (1) and studio (1)
        self.assertEqual(len(mail.outbox), 3)
        self.assertEqual(
            sorted(mail.outbox[1].bcc),
            ['test0@test.com', 'test1@test.com', 'test2@test.com']
        )

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_cancelling_more_than_one_only_emails_once(self, mock_tz):
        """
        Test that the waiting list is only emailed once if more than one
        booking is cancelled
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 13, 17, 15, tzinfo=timezone.utc
        )

        # make full event (setup has one paid and one unpaid)
        # cancellation period =1, date = 2015, 2, 13, 18, 0
        self.event.max_participants = 3
        self.event.save()

        # make another booking that will be cancelled
        mommy.make_recipe(
            'booking.booking', event=self.event, paid=False,
            payment_confirmed=False, status='OPEN',
            user__email="unpaid@test.com",
            date_booked=datetime(
                2015, 2, 9, 18, 0, tzinfo=timezone.utc
            ),
            warning_sent=True
        )

        # make some waiting list users
        for i in range(3):
            mommy.make_recipe(
                'booking.waiting_list_user', event=self.event,
                user__email='test{}@test.com'.format(i)
            )

        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking (2) and
        # one email with bcc to waiting list (1) and studio (1)
        # waiting list email sent after the first cancelled booking
        self.assertEqual(len(mail.outbox), 4)
        self.assertEqual(
            sorted(mail.outbox[1].bcc),
            ['test0@test.com', 'test1@test.com', 'test2@test.com']
        )
        for email in [mail.outbox[0], mail.outbox[2], mail.outbox[3]]:
            self.assertEqual(email.bcc, [])

        self.assertEqual(Booking.objects.filter(status='CANCELLED').count(), 2)

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_cancelling_not_full_event_does_not_email_waiting_list(self, mock_tz):
        """
        Test that the waiting list is not emailed if event not full
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 13, 17, 15, tzinfo=timezone.utc
        )

        # make full event (setup has one paid and one unpaid)
        # cancellation period =1, date = 2015, 2, 13, 18, 0
        self.event.max_participants = 3
        self.event.save()

        # make some waiting list users
        for i in range(3):
            mommy.make_recipe(
                'booking.waiting_list_user', event=self.event,
                user__email='test{}@test.com'.format(i)
            )

        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking (1) and studio (1) only
        self.assertEqual(len(mail.outbox), 2)

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_dont_cancel_bookings_rebooked_within_past_6_hours(self, mock_tz):
        """
        Avoid immediately cancelling bookings made within the cancellation
        period to allow time for users to make payments
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 10, 18, 0, tzinfo=timezone.utc
        )
        self.unpaid.date_rebooked = datetime(
            2015, 2, 10, 12, 30, tzinfo=timezone.utc
        )
        self.unpaid.save()

        self.assertEquals(self.unpaid.status, 'OPEN')

        management.call_command('cancel_unpaid_bookings')
        # self.unpaid was booked > 6 hrs ago
        self.assertTrue(self.unpaid.date_booked <= (timezone.now() - timedelta(hours=6)))
        self.unpaid.refresh_from_db()
        # but still open
        self.assertEquals(self.unpaid.status, 'OPEN')

        # move time on one hour and try again
        mock_tz.now.return_value = datetime(
            2015, 2, 10, 19, 0, tzinfo=timezone.utc
        )
        management.call_command('cancel_unpaid_bookings')
        # self.unpaid was rebooked > 6 hrs ago
        self.assertTrue(self.unpaid.date_rebooked <= (timezone.now() - timedelta(hours=6)))
        self.unpaid.refresh_from_db()
        # now cancelled
        self.assertEquals(self.unpaid.status, 'CANCELLED')

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_cancel_bookings_over_payment_time_allowed_without_warnings(
            self, mock_tz
    ):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 10, 0, tzinfo=timezone.utc
        )
        self.event.payment_due_date = None
        self.event.payment_time_allowed = 8
        self.event.save()

        self.unpaid.date_booked = datetime(
            2015, 2, 11, 3, 0, tzinfo=timezone.utc
        )
        self.unpaid.warning_sent = False
        self.unpaid.save()
        # self.unpaid.date_booked is within 8 hrs, so not cancelled
        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEquals(len(mail.outbox), 0)
        self.assertEqual(self.unpaid.status, "OPEN")


        # set date booked to >8 hrs ago
        self.unpaid.date_booked = datetime(
            2015, 2, 11, 1, 59, tzinfo=timezone.utc
        )
        self.unpaid.save()
        # self.unpaid.date_booked is within 4 hrs, so not cancelled
        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEquals(len(mail.outbox), 2)
        self.assertEqual(self.unpaid.status, "CANCELLED")
        # even though warning has not been sent
        self.assertFalse(self.unpaid.warning_sent)


    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_payment_time_allowed_less_than_6_hours_defaults_to_6(
            self, mock_tz
    ):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 10, 0, tzinfo=timezone.utc
        )
        self.event.payment_due_date = None
        self.event.payment_time_allowed = 4
        self.event.save()

        self.unpaid.date_booked = datetime(
            2015, 2, 11, 5, 0, tzinfo=timezone.utc
        )
        self.unpaid.warning_sent = False
        self.unpaid.save()
        # self.unpaid.date_booked is more than 4 but <6 hrs, so not cancelled
        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(self.unpaid.status, "OPEN")

        # set date booked to >6 hrs ago
        self.unpaid.date_booked = datetime(
            2015, 2, 11, 3, 59, tzinfo=timezone.utc
        )
        self.unpaid.save()
        # self.unpaid.date_booked is within 4 hrs, so not cancelled
        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEquals(len(mail.outbox), 2)
        self.assertEqual(self.unpaid.status, "CANCELLED")
        # even though warning has not been sent
        self.assertFalse(self.unpaid.warning_sent)

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_free_class_requested_allows_24_hrs_after_booking(
            self, mock_tz
    ):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 10, 0, tzinfo=timezone.utc
        )
        self.event.payment_due_date = None
        self.event.payment_time_allowed = 6
        self.event.save()

        self.unpaid.date_booked = datetime(
            2015, 2, 11, 3, 0, tzinfo=timezone.utc
        )
        self.unpaid.warning_sent = False
        self.unpaid.free_class_requested = True
        self.unpaid.save()
        # self.unpaid.date_booked is more than 6 hrs ago, but is free class
        # requested so should default to 24 hrs instead
        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(self.unpaid.status, "OPEN")

        # set date booked to >24 hrs ago
        self.unpaid.date_booked = datetime(
            2015, 2, 10, 9, 59, tzinfo=timezone.utc
        )
        self.unpaid.save()
        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEquals(len(mail.outbox), 2)
        self.assertEqual(self.unpaid.status, "CANCELLED")
        # even though warning has not been sent
        self.assertFalse(self.unpaid.warning_sent)

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_free_class_requested_allows_24_hrs_after_rebooking(
            self, mock_tz
    ):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 10, 0, tzinfo=timezone.utc
        )
        self.event.payment_due_date = None
        self.event.payment_time_allowed = 6
        self.event.save()

        self.unpaid.date_booked = datetime(
            2015, 2, 9, 3, 0, tzinfo=timezone.utc
        )
        self.unpaid.date_rebooked = datetime(
            2015, 2, 11, 3, 0, tzinfo=timezone.utc
        )
        self.unpaid.warning_sent = False
        self.unpaid.free_class_requested = True
        self.unpaid.save()
        # self.unpaid.date_booked is and date_rebooked are more than 6 hrs ago,
        # but is free class
        # requested so should default to 24 hrs past date_rebooked instead
        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(self.unpaid.status, "OPEN")

        # set date rebooked to >24 hrs ago
        self.unpaid.date_rebooked = datetime(
            2015, 2, 10, 9, 59, tzinfo=timezone.utc
        )
        self.unpaid.save()
        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEquals(len(mail.outbox), 2)
        self.assertEqual(self.unpaid.status, "CANCELLED")
        # even though warning has not been sent
        self.assertFalse(self.unpaid.warning_sent)


class TicketBookingWarningTests(TestCase):

    @patch('booking.management.commands.email_ticket_booking_warnings.timezone')
    def test_email_warnings(self, mock_tz):
        """
        test email warning is sent 24 hours before payment_due_date
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 0, 0, tzinfo=timezone.utc
            )

        # payment_due_date 2015/2/11 23:59 (within 24hrs - warnings sent)
        ticketed_event = mommy.make_recipe(
            'booking.ticketed_event_max10',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            ticket_cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=timezone.utc),
        )
        # payment_due_date 2015/2/12 23:59 (>24hrs - warnings not sent)
        ticketed_event1 = mommy.make_recipe(
            'booking.ticketed_event_max10',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            ticket_cost=10,
            payment_due_date=datetime(2015, 2, 12, tzinfo=timezone.utc),
        )

        mommy.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=timezone.utc),
            _quantity=5,
            )
        mommy.make(
            TicketBooking,  ticketed_event=ticketed_event1, paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=timezone.utc),
            _quantity=5,
            )

        for ticket_booking in TicketBooking.objects.all():
            mommy.make(Ticket, ticket_booking=ticket_booking)

        management.call_command('email_ticket_booking_warnings')
        self.assertEquals(len(mail.outbox), 5)

    @patch('booking.management.commands.email_ticket_booking_warnings.timezone')
    def test_email_warnings_not_sent_for_payment_time_allowed(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 0, 0, tzinfo=timezone.utc
            )

        # no payment_due_date
        ticketed_event = mommy.make_recipe(
            'booking.ticketed_event_max10',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            ticket_cost=10,
            payment_time_allowed=4,
        )

        mommy.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=timezone.utc),
            _quantity=5,
            )

        for ticket_booking in TicketBooking.objects.all():
            mommy.make(Ticket, ticket_booking=ticket_booking)

        management.call_command('email_ticket_booking_warnings')
        self.assertEquals(len(mail.outbox), 0)


    @patch('booking.management.commands.email_ticket_booking_warnings.timezone')
    def test_email_warnings_sent_if_both_due_date_and_time_allowed(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 0, 0, tzinfo=timezone.utc
            )

        # payment_due_date 2015/2/11 23:59 (within 24hrs - warnings sent)
        # payment_time_allowed is set
        ticketed_event = mommy.make_recipe(
            'booking.ticketed_event_max10',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            ticket_cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=timezone.utc),
            payment_time_allowed=4,
        )

        mommy.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=timezone.utc),
            _quantity=5,
            )

        for ticket_booking in TicketBooking.objects.all():
            mommy.make(Ticket, ticket_booking=ticket_booking)

        management.call_command('email_ticket_booking_warnings')
        self.assertEquals(len(mail.outbox), 5)

    @patch('booking.management.commands.email_ticket_booking_warnings.timezone')
    def test_email_warnings_not_sent_twice(self, mock_tz):

        mock_tz.now.return_value = datetime(
            2015, 2, 11, 0, 0, tzinfo=timezone.utc
            )

        # payment_due_date 2015/2/11 23:59 (within 24hrs - warnings sent)
        ticketed_event = mommy.make_recipe(
            'booking.ticketed_event_max10',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            ticket_cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=timezone.utc),
        )

        mommy.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=timezone.utc),
            _quantity=5,
            )

        for ticket_booking in TicketBooking.objects.all():
            mommy.make(Ticket, ticket_booking=ticket_booking)

        management.call_command('email_ticket_booking_warnings')
        self.assertEquals(len(mail.outbox), 5)
        for ticket_booking in TicketBooking.objects.all():
            self.assertTrue(ticket_booking.warning_sent)

        # no additional emails sent on subsequent calls
        management.call_command('email_ticket_booking_warnings')
        self.assertEquals(len(mail.outbox), 5)

    @patch('booking.management.commands.email_ticket_booking_warnings.timezone')
    def test_email_warnings_only_sent_for_unpaid(self, mock_tz):
        """
        test email warning is only sent for bookings that are not marked as
        payment_confirmed
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 0, 0, tzinfo=timezone.utc
            )

        # payment_due_date 2015/2/11 23:59 (within 24hrs - warnings sent)
        ticketed_event = mommy.make_recipe(
            'booking.ticketed_event_max10',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            ticket_cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=timezone.utc),
        )

        mommy.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=timezone.utc),
            _quantity=5,
            )
        mommy.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=True,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=timezone.utc),
            _quantity=5,
            )
        for ticket_booking in TicketBooking.objects.all():
            mommy.make(Ticket, ticket_booking=ticket_booking)

        management.call_command('email_ticket_booking_warnings')
        self.assertEquals(len(mail.outbox), 5)
        for ticket_booking in TicketBooking.objects.filter(paid=False):
            self.assertTrue(ticket_booking.warning_sent)
        for ticket_booking in TicketBooking.objects.filter(paid=True):
            self.assertFalse(ticket_booking.warning_sent)

    @patch('booking.management.commands.email_ticket_booking_warnings.timezone')
    def test_email_warnings_only_sent_for_open_bookings(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 0, 0, tzinfo=timezone.utc
            )

        # payment_due_date 2015/2/11 23:59 (within 24hrs - warnings sent)
        ticketed_event = mommy.make_recipe(
            'booking.ticketed_event_max10',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            ticket_cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=timezone.utc),
        )

        mommy.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=timezone.utc),
            _quantity=5,
            )
        mommy.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=False,
            cancelled=True,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=timezone.utc),
            _quantity=5,
            )
        for ticket_booking in TicketBooking.objects.all():
            mommy.make(Ticket, ticket_booking=ticket_booking)

        management.call_command('email_ticket_booking_warnings')
        self.assertEquals(len(mail.outbox), 5)
        for ticket_booking in TicketBooking.objects.filter(cancelled=False):
            self.assertTrue(ticket_booking.warning_sent)
        for ticket_booking in TicketBooking.objects.filter(cancelled=True):
            self.assertFalse(ticket_booking.warning_sent)

    @patch('booking.management.commands.email_ticket_booking_warnings.timezone')
    def test_email_warnings_only_sent_for_open_events(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 0, 0, tzinfo=timezone.utc
            )

        # payment_due_date 2015/2/11 23:59 (within 24hrs - warnings sent)
        ticketed_event = mommy.make_recipe(
            'booking.ticketed_event_max10',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            ticket_cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=timezone.utc),
        )
        ticketed_event_cancelled = mommy.make_recipe(
            'booking.ticketed_event_max10',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            ticket_cost=10,
            cancelled=True,
            payment_due_date=datetime(2015, 2, 11, tzinfo=timezone.utc),
        )
        mommy.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=timezone.utc),
            _quantity=5,
            )
        mommy.make(
            TicketBooking,  ticketed_event=ticketed_event_cancelled,
            paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=timezone.utc),
            _quantity=5,
            )
        for ticket_booking in TicketBooking.objects.all():
            mommy.make(Ticket, ticket_booking=ticket_booking)

        management.call_command('email_ticket_booking_warnings')
        self.assertEquals(len(mail.outbox), 5)
        for ticket_booking in TicketBooking.objects.filter(
                ticketed_event=ticketed_event
        ):
            self.assertTrue(ticket_booking.warning_sent)
        for ticket_booking in TicketBooking.objects.filter(
            ticketed_event=ticketed_event_cancelled
        ):
            self.assertFalse(ticket_booking.warning_sent)

    @patch('booking.management.commands.email_ticket_booking_warnings.timezone')
    def test_email_warnings_only_sent_for_bookings_with_tickets(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 0, 0, tzinfo=timezone.utc
            )

        # payment_due_date 2015/2/11 23:59 (within 24hrs - warnings sent)
        ticketed_event = mommy.make_recipe(
            'booking.ticketed_event_max10',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            ticket_cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=timezone.utc),
        )
        mommy.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=timezone.utc),
            _quantity=5,
            )
        for ticket_booking in TicketBooking.objects.all()[0:5]:
            mommy.make(Ticket, ticket_booking=ticket_booking)

        management.call_command('email_ticket_booking_warnings')
        self.assertEquals(len(mail.outbox), 5)
        for ticket_booking in TicketBooking.objects.all():
            if ticket_booking.tickets.exists():
                self.assertTrue(ticket_booking.warning_sent)
            else:
                self.assertFalse(ticket_booking.warning_sent)

    @patch('booking.management.commands.email_ticket_booking_warnings.timezone')
    def test_email_warnings_not_sent_within_2_hrs_of_booking(self, mock_tz):
        """
        test email warning is only sent for bookings made more than 2 hrs ago
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 0, 0, tzinfo=timezone.utc
            )

        # payment_due_date 2015/2/11 23:59 (within 24hrs - warnings sent)
        ticketed_event = mommy.make_recipe(
            'booking.ticketed_event_max10',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            ticket_cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=timezone.utc),
        )
        booking1 = mommy.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=timezone.utc),
            )
        booking2 = mommy.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=False,
            date_booked=datetime(2015, 2, 10, 23, 0, tzinfo=timezone.utc),
            )
        for ticket_booking in TicketBooking.objects.all():
            mommy.make(Ticket, ticket_booking=ticket_booking)

        management.call_command('email_ticket_booking_warnings')
        self.assertEquals(len(mail.outbox), 1)
        booking1.refresh_from_db()
        booking2.refresh_from_db()
        self.assertTrue(booking1.warning_sent)
        self.assertFalse(booking2.warning_sent)


class CancelUnpaidTicketBookingsTests(TestCase):

    def setUp(self):
        # payment_due_date 2015/2/10 23:59
        self.ticketed_event = mommy.make_recipe(
            'booking.ticketed_event_max10',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=timezone.utc),
            payment_open=True,
            ticket_cost=10,
            advance_payment_required=True,
            payment_due_date=datetime(2015, 2, 10, tzinfo=timezone.utc),
        )
        self.paid = mommy.make(
            TicketBooking,  ticketed_event=self.ticketed_event, paid=True,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=timezone.utc),
            warning_sent=True,
            user__email='paid@test.com', purchase_confirmed=True
            )
        self.unpaid = mommy.make(
            TicketBooking,  ticketed_event=self.ticketed_event, paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=timezone.utc),
            warning_sent=True,
            user__email='unpaid@test.com', purchase_confirmed=True
            )
        for booking in [self.paid, self.unpaid]:
            mommy.make(Ticket, ticket_booking=booking)

        # redirect stdout so we can test it
        self.output = StringIO()
        self.saved_stdout = sys.stdout
        sys.stdout = self.output

    def tearDown(self):
        self.output.close()
        sys.stdout = self.saved_stdout

    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_cancel_unpaid_bookings(self, mock_tz):
        """
        test unpaid bookings are cancelled
        """
        # one min after payment due date
        mock_tz.now.return_value = datetime(
            2015, 2, 11, tzinfo=timezone.utc
        )

        self.assertFalse(self.unpaid.cancelled)
        self.assertFalse(self.paid.cancelled)

        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.paid.refresh_from_db()
        self.assertEquals(len(mail.outbox), 2)
        self.assertTrue(self.unpaid.cancelled)
        self.assertFalse(self.paid.cancelled)

    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_dont_cancel_if_advance_payment_not_required(self, mock_tz):
        """
        test unpaid bookings are not cancelled if advance payment not required
        for event
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 11, tzinfo=timezone.utc
        )
        # set payment_due_date to None, otherwise advance_payment_required is
        # automatically set to True
        self.ticketed_event.payment_due_date = None
        self.ticketed_event.advance_payment_required = False
        self.ticketed_event.save()
        self.assertFalse(self.unpaid.cancelled)
        self.assertFalse(self.paid.cancelled)

        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.paid.refresh_from_db()
        self.assertEquals(len(mail.outbox), 0)
        self.assertFalse(self.unpaid.cancelled)
        self.assertFalse(self.paid.cancelled)

    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_dont_cancel_for_events_with_no_cost(self, mock_tz):
        """
        test unpaid bookings are not cancelled if no cost for event
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 11, tzinfo=timezone.utc
        )
        self.ticketed_event.ticket_cost = 0
        self.ticketed_event.save()
        self.assertFalse(self.unpaid.cancelled)
        self.assertFalse(self.paid.cancelled)

        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.paid.refresh_from_db()
        self.assertEquals(len(mail.outbox), 0)
        self.assertFalse(self.unpaid.cancelled)
        self.assertFalse(self.paid.cancelled)

    @patch('booking.management.commands.email_ticket_booking_warnings.timezone')
    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_only_cancel_with_payment_due_date_if_warning_sent(
            self, cancel_mock_tz, warn_mock_tz
    ):
        cancel_mock_tz.now.return_value = datetime(
            2015, 2, 11, tzinfo=timezone.utc
        )
        warn_mock_tz.now.return_value = datetime(
            2015, 2, 11, tzinfo=timezone.utc
        )
        self.assertFalse(self.unpaid.cancelled)
        self.unpaid.warning_sent = False
        self.unpaid.save()

        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEquals(len(mail.outbox), 0)
        self.assertFalse(self.unpaid.cancelled)

        # send warnings
        management.call_command('email_ticket_booking_warnings')
        self.unpaid.refresh_from_db()
        self.assertTrue(self.unpaid.warning_sent)
        self.assertFalse(self.unpaid.cancelled)

        # run cancel commmand again now that warning is set
        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings; plus warning email
        self.unpaid.refresh_from_db()

        self.assertEquals(len(mail.outbox), 3)
        warning_email = mail.outbox[0]
        cancel_email_to_user = mail.outbox[1]
        cancel_email_to_studio = mail.outbox[2]
        self.assertEqual(
            warning_email.subject,
            '[watermelon studio bookings] Reminder: Ticket booking ref {} is '
            'not yet paid'.format(self.unpaid.booking_reference)
        )
        self.assertEqual(warning_email.to[0], self.unpaid.user.email)
        self.assertEqual(
            cancel_email_to_user.subject,
            '[watermelon studio bookings] Ticket Booking ref {} '
            'cancelled'.format(self.unpaid.booking_reference)
        )
        self.assertEqual(cancel_email_to_user.to[0], self.unpaid.user.email)
        self.assertEqual(
            cancel_email_to_studio.subject,
            '[watermelon studio bookings] Ticket Booking has been '
            'automatically cancelled'
        )
        self.assertEqual(cancel_email_to_studio.to[0], settings.DEFAULT_STUDIO_EMAIL)
        self.assertTrue(self.unpaid.cancelled)

    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_cancel_ticket_bookings_over_payment_time_allowed_without_warnings(
            self, mock_tz
    ):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 10, 0, tzinfo=timezone.utc
        )
        self.ticketed_event.payment_due_date = None
        self.ticketed_event.payment_time_allowed = 8
        self.ticketed_event.save()

        self.unpaid.date_booked = datetime(
            2015, 2, 11, 3, 0, tzinfo=timezone.utc
        )
        self.unpaid.warning_sent = False
        self.unpaid.save()
        # self.unpaid.date_booked is within 8 hrs, so not cancelled
        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEquals(len(mail.outbox), 0)
        self.assertFalse(self.unpaid.cancelled)


        # set date booked to >8 hrs ago
        self.unpaid.date_booked = datetime(
            2015, 2, 11, 1, 59, tzinfo=timezone.utc
        )
        self.unpaid.save()
        # self.unpaid.date_booked is within 4 hrs, so not cancelled
        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEquals(len(mail.outbox), 2)
        self.assertTrue(self.unpaid.cancelled)
        # even though warning has not been sent
        self.assertFalse(self.unpaid.warning_sent)


    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_payment_time_allowed_less_than_6_hours_defaults_to_6(
            self, mock_tz
    ):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 10, 0, tzinfo=timezone.utc
        )
        self.ticketed_event.payment_due_date = None
        self.ticketed_event.payment_time_allowed = 4
        self.ticketed_event.save()

        self.unpaid.date_booked = datetime(
            2015, 2, 11, 5, 0, tzinfo=timezone.utc
        )
        self.unpaid.warning_sent = False
        self.unpaid.save()
        # self.unpaid.date_booked is more than 4 but <6 hrs, so not cancelled
        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEquals(len(mail.outbox), 0)
        self.assertFalse(self.unpaid.cancelled)


        # set date booked to >6 hrs ago
        self.unpaid.date_booked = datetime(
            2015, 2, 11, 3, 59, tzinfo=timezone.utc
        )
        self.unpaid.save()
        # self.unpaid.date_booked is within 4 hrs, so not cancelled
        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEquals(len(mail.outbox), 2)
        self.assertTrue(self.unpaid.cancelled)
        # even though warning has not been sent
        self.assertFalse(self.unpaid.warning_sent)

    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_dont_cancel_for_events_in_the_past(self, mock_tz):
        """
        test don't cancel or send emails for past events
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 11, tzinfo=timezone.utc
        )
        self.assertFalse(self.unpaid.cancelled)
        self.assertFalse(self.paid.cancelled)

        # make date of event in the past
        self.ticketed_event.date = datetime(2015, 2, 9, tzinfo=timezone.utc)
        self.ticketed_event.save()
        self.assertTrue(timezone.now() > self.ticketed_event.date)

        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking and studio once
        # for all cancelled bookings
        self.unpaid.refresh_from_db()
        self.paid.refresh_from_db()
        self.assertEquals(len(mail.outbox), 0)
        self.assertFalse(self.unpaid.cancelled)
        self.assertFalse(self.paid.cancelled)

    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_dont_cancel_for_already_cancelled(self, mock_tz):
        """
        ignore already cancelled bookings
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 11, tzinfo=timezone.utc
        )
        self.unpaid.cancelled = True
        self.unpaid.save()

        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking and studio once
        # for all cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEquals(len(mail.outbox), 0)
        self.assertTrue(self.unpaid.cancelled)

    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_dont_cancel_for_cancelled_events(self, mock_tz):
        """
        ignore bookings for cancelled events
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 11, tzinfo=timezone.utc
        )
        self.ticketed_event.cancelled = True
        self.ticketed_event.save()
        self.assertFalse(self.unpaid.cancelled)

        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking and studio once
        # for all cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEquals(len(mail.outbox), 0)
        self.assertFalse(self.unpaid.cancelled)

    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_dont_cancel_bookings_created_within_past_6_hours(self, mock_tz):
        """
        Avoid immediately cancelling bookings made within the cancellation
        period to allow time for users to make payments
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 12, 0, tzinfo=timezone.utc
        )

        # self.ticketed_event payment due date 2015/2/11 23:59

        unpaid_within_6_hrs = mommy.make(
            TicketBooking,
            ticketed_event=self.ticketed_event,
            paid=False,
            date_booked=datetime(
                2015, 2, 11, 6, 30, tzinfo=timezone.utc
            ),
            warning_sent=True
        )
        unpaid_more_than_6_hrs = mommy.make(
            TicketBooking,
            ticketed_event=self.ticketed_event,
            paid=False,
            date_booked=datetime(
                2015, 2, 10, 5, 30, tzinfo=timezone.utc
            ),
            warning_sent=True
        )

        self.assertFalse(unpaid_within_6_hrs.cancelled)
        self.assertFalse(unpaid_more_than_6_hrs.cancelled)

        management.call_command('cancel_unpaid_ticket_bookings')
        unpaid_within_6_hrs.refresh_from_db()
        unpaid_more_than_6_hrs.refresh_from_db()
        self.assertFalse(unpaid_within_6_hrs.cancelled)
        self.assertTrue(unpaid_more_than_6_hrs.cancelled)

    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_only_send_one_email_to_studio(self, mock_tz):
        """
        users are emailed per booking, studio just receives one summary
        email
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 11, tzinfo=timezone.utc
        )
        for i in range(5):
            mommy.make(
                TicketBooking, ticketed_event=self.ticketed_event,
                cancelled=False, paid=False,
                user__email="unpaid_user{}@test.com".format(i),
                date_booked= datetime(
                    2015, 2, 9, tzinfo=timezone.utc
                ),
                warning_sent=True
            )
        for booking in TicketBooking.objects.all():
            mommy.make(Ticket, ticket_booking=booking)

        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking (6) (these 5 plus
        # self.unpaid) and studio once for all cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEquals(len(mail.outbox), 7)
        self.assertTrue(self.unpaid.cancelled)
        self.assertEquals(
            TicketBooking.objects.filter(cancelled=True).count(), 6
        )
        cancelled_booking_emails = [
            booking.user.email for booking
            in TicketBooking.objects.filter(cancelled=True)
        ]
        all_emails = cancelled_booking_emails + [settings.DEFAULT_STUDIO_EMAIL]

        self.assertEquals(
            sorted(all_emails),
            sorted([email.to[0] for email in mail.outbox])
        )

    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.send_mail')
    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_email_errors(self, mock_tz, mock_send):
        mock_send.side_effect = Exception('Error sending email')
        mock_tz.now.return_value = datetime(
            2015, 2, 11, tzinfo=timezone.utc
        )

        management.call_command('cancel_unpaid_ticket_bookings')
        # error emails are sent to user per cancelled booking (self.unpaid)
        # and studio
        self.unpaid.refresh_from_db()
        self.assertEquals(len(mail.outbox), 2)
        self.assertTrue(self.unpaid.cancelled)

        for email in mail.outbox:
            self.assertEquals(email.to, [settings.SUPPORT_EMAIL])

        self.assertEqual(
            mail.outbox[0].subject,
            '{} An error occurred! (Automatic cancel ticket booking job - '
            'cancelled email)'.format(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX )
        )

        self.assertEqual(
            mail.outbox[1].subject,
            '{} An error occurred! (Automatic cancel ticket booking job - '
            'studio email)'.format(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX)
        )

    @override_settings(SEND_ALL_STUDIO_EMAILS=False)
    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_no_email_to_studio_if_setting_not_on(self, mock_tz):
        """
        users are emailed per booking, studio only receives summary
        email if SEND_ALL_STUDIO_EMAILS setting is on
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 11, tzinfo=timezone.utc
        )
        for i in range(5):
            mommy.make(
                TicketBooking, ticketed_event=self.ticketed_event,
                cancelled=False, paid=False,
                user__email="unpaid_user{}@test.com".format(i),
                date_booked= datetime(
                    2015, 2, 9, tzinfo=timezone.utc
                ),
                warning_sent=True
            )
        for booking in TicketBooking.objects.all():
            mommy.make(Ticket, ticket_booking=booking)

        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking (6) (these 5 plus
        # self.unpaid); none to studio
        self.assertEquals(len(mail.outbox), 6)
        cancelled_booking_emails = [
            booking.user.email for booking
            in TicketBooking.objects.filter(cancelled=True)
        ]
        self.assertEquals(
            cancelled_booking_emails, [email.to[0] for email in mail.outbox]
        )

    @patch('booking.management.commands.delete_unconfirmed_ticket_bookings.timezone')
    def test_delete_unconfirmed_ticket_bookings_after_1_hr(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 12, 0, tzinfo=timezone.utc
        )
        unconfirmed_ticket_booking = mommy.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            date_booked=datetime(2015, 2, 11, 10, 0, tzinfo=timezone.utc),
            purchase_confirmed=False
        )
        unconfirmed_ticket_booking1 = mommy.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            date_booked=datetime(2015, 2, 11, 11, 30, tzinfo=timezone.utc),
            purchase_confirmed=False
        )
        for booking in TicketBooking.objects.all():
            mommy.make(Ticket, ticket_booking=booking)

        management.call_command('delete_unconfirmed_ticket_bookings')
        # only unconfirmed_ticket_booking has been deleted (booked >1 hr ago)
        self.assertEqual(
            TicketBooking.objects.filter(purchase_confirmed=False).count(),
            1
        )

        with self.assertRaises(TicketBooking.DoesNotExist):
            TicketBooking.objects.get(id=unconfirmed_ticket_booking.id)

        # confirm that associated tickets have also been deleted
        self.assertEqual(
            Ticket.objects.filter(
                ticket_booking__id=unconfirmed_ticket_booking.id
            ).count(),
            0
        )
        # unconfirmed_ticket_booking1 still has its ticket
        self.assertEqual(
            Ticket.objects.filter(
                ticket_booking__id=unconfirmed_ticket_booking1.id
            ).count(),
            1
        )

    @patch('booking.management.commands.delete_unconfirmed_ticket_bookings.timezone')
    def test_no_ticket_bookings_to_delete(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 12, 0, tzinfo=timezone.utc
        )
        self.unpaid.paid = True
        self.unpaid.save()

        unconfirmed_ticket_booking = mommy.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            date_booked=datetime(2015, 2, 11, 11, 30, tzinfo=timezone.utc),
            purchase_confirmed=False
        )
        mommy.make(Ticket, ticket_booking=unconfirmed_ticket_booking)

        # all ticket bookings are paid or booked within pasr hr

        management.call_command('delete_unconfirmed_ticket_bookings')

        # unconfirmed_ticket_booking still has its ticket
        self.assertEqual(
            Ticket.objects.filter(
                ticket_booking__id=unconfirmed_ticket_booking.id
            ).count(),
            1
        )

        self.assertEqual(
            self.output.getvalue(),
            'No unconfirmed ticket bookings to delete\n',
            self.output.getvalue()
        )


class BlockBookingsReportTests(TestCase):

    def setUp(self):
        """
        Users with active/inactive blocks
        Bookings for relevant classes not made with the active block but
        booked after it's start date
        Report unpaid/paid/paid with paypal
        Ignore free
        """
        self.user1 = mommy.make_recipe('booking.user')
        self.user2 = mommy.make_recipe('booking.user')

        self.event_type = mommy.make_recipe('booking.event_type_PC')

        self.user1_active_block = mommy.make_recipe(
            'booking.block_5', user=self.user1,
            start_date=timezone.now() - timedelta(10),
            block_type__event_type=self.event_type,
            paid=True
        )
        self.user2_active_block = mommy.make_recipe(
            'booking.block_5', user=self.user2,
            start_date=timezone.now() - timedelta(10),
            block_type__event_type=self.event_type, paid=True
        )

        user1_bookings_on_block = mommy.make_recipe(
            'booking.booking',
            user=self.user1,
            event__event_type=self.event_type,
            block=self.user1_active_block,
            date_booked=timezone.now() - timedelta(8),
            _quantity=2
        )
        self.user1_booking_not_on_block = mommy.make_recipe(
            'booking.booking',
            user=self.user1,
            event__event_type=self.event_type,
            date_booked=timezone.now() - timedelta(8)
        )
        user1_booking_old = mommy.make_recipe(
            'booking.booking',
            user=self.user1,
            event__event_type=self.event_type,
            date_booked=timezone.now() - timedelta(12)
        )
        user1_booking_free = mommy.make_recipe(
            'booking.booking',
            user=self.user1,
            event__event_type=self.event_type,
            free_class=True,
            date_booked=timezone.now() - timedelta(8)
        )

        # redirect stdout so we can test it
        self.output = StringIO()
        self.saved_stdout = sys.stdout
        sys.stdout = self.output

    def tearDown(self):
        self.output.close()
        sys.stdout = self.saved_stdout

    def test_block_booking_report(self):
        management.call_command('block_bookings_report')

        # user 1: one booking made on the active block in the right time
        # period which is not free
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            ActivityLog.objects.last().log,
            'Possible issues with bookings for user {}. Check bookings since '
            '{} block ({}) start that are not assigned to the block ('
            'support notified by email)'.format(
                self.user1.username,
                self.user1_active_block.block_type.event_type.subtype,
                self.user1_active_block.id
            )
        )
        self.assertEqual(
            self.output.getvalue(),
            'User {username} ({user_id}) has 1 booking made for class type '
            '{block_subtype} without using the active block {block_id}\n'
            '1 booking is unpaid or not marked as payment_confirmed '
            '(ids {unpaid_id})\n'.format(
                username=self.user1.username, user_id=self.user1.id,
                block_subtype=self.user1_active_block.block_type.event_type.subtype,
                block_id=self.user1_active_block.id,
                unpaid_id=self.user1_booking_not_on_block.id,
            )
        )

    def test_block_booking_report_with_paid(self):
        paid_booking = mommy.make_recipe(
            'booking.booking',
            user=self.user1,
            event__event_type=self.event_type,
            date_booked=timezone.now() - timedelta(8),
            paid=True, payment_confirmed=True
        )
        paid_by_pp_booking = mommy.make_recipe(
            'booking.booking',
            user=self.user1,
            event__event_type=self.event_type,
            date_booked=timezone.now() - timedelta(8),
            paid=True, payment_confirmed=True
        )
        mommy.make(
            PaypalBookingTransaction, booking=paid_by_pp_booking,
            invoice_id='inv', transaction_id='1'
        )

        management.call_command('block_bookings_report')
        # user 1: 3 bookings made on the active block in the right time
        # period which are not free (2 paid, 1 with pp, 1 unpaid)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            ActivityLog.objects.last().log,
            'Possible issues with bookings for user {}. Check bookings since '
            '{} block ({}) start that are not assigned to the block ('
            'support notified by email)'.format(
                self.user1.username,
                self.user1_active_block.block_type.event_type.subtype,
                self.user1_active_block.id
            )
        )
        self.assertEqual(
            self.output.getvalue(),
            'User {username} ({user_id}) has 3 bookings made for class type '
            '{block_subtype} without using the active block {block_id}\n'
            '1 booking is unpaid or not marked as payment_confirmed '
            '(ids {unpaid_id})\n'
            '2 bookings are paid (ids {paid1}, {paid2})\n'
            'Paid booking ids that have been paid directly with '
            'paypal: {paid2}\n'.format(
                username=self.user1.username, user_id=self.user1.id,
                block_subtype=self.user1_active_block.block_type.event_type.subtype,
                block_id=self.user1_active_block.id,
                unpaid_id=self.user1_booking_not_on_block.id,
                paid1=paid_booking.id, paid2=paid_by_pp_booking.id
            )
        )

    def test_block_booking_report_with_no_issues(self):
        self.user1_booking_not_on_block.delete()
        management.call_command('block_bookings_report')

        self.assertEqual(
            self.output.getvalue(),
            'No issues to report for users with blocks\n'
        )


class CreateSaleBlockTypesTests(TestCase):

    def test_makes_existing_blocktypes_standard_and_creates_sale_copy(self):
        pc_evtype = mommy.make(
            EventType, event_type="CL", subtype="Pole level class"
        )
        mommy.make_recipe('booking.blocktype5', event_type=pc_evtype)
        mommy.make_recipe('booking.blocktype10', event_type=pc_evtype)

        mommy.make_recipe(
            'booking.blocktypePP10', event_type__subtype="Pole practice"
        )
        for bt in BlockType.objects.all():
            self.assertIsNone(bt.identifier)
        management.call_command('create_sale_blocktypes')
        self.assertEqual(BlockType.objects.count(), 6)
        self.assertEqual(
            BlockType.objects.filter(identifier='standard').count(), 3
        )
        self.assertEqual(
            BlockType.objects.filter(identifier='sale').count(), 3
        )


class ActivateBlockTypeTests(TestCase):

    def test_activate_blocktypes(self):
        mommy.make_recipe(
            'booking.blocktype5', active=False, identifier='test', _quantity=5
        )
        self.assertEqual(
            BlockType.objects.filter(active=True).count(), 0
        )
        management.call_command(
            'activate_blocktypes', 'test', 'on'
        )
        self.assertEqual(
            BlockType.objects.filter(active=True).count(), 5
        )

    def test_deactivate_blocktypes(self):
        mommy.make_recipe(
            'booking.blocktype5', identifier='test', _quantity=5
        )
        self.assertEqual(
            BlockType.objects.filter(active=True).count(), 5
        )
        management.call_command(
            'activate_blocktypes', 'test', 'off'
        )
        self.assertEqual(
            BlockType.objects.filter(active=True).count(), 0
        )

    def test_activate_blocktypes_only_activates_by_identifier(self):
        mommy.make_recipe(
            'booking.blocktype5', active=False, identifier='test', _quantity=5
        )
        mommy.make_recipe(
            'booking.blocktype5', active=False, identifier='test1', _quantity=5
        )
        self.assertEqual(
            BlockType.objects.filter(active=True).count(), 0
        )
        management.call_command('activate_blocktypes', 'test', 'on')
        self.assertEqual(
            BlockType.objects.filter(active=True).count(), 5
        )

    def test_activate_multiple_identifiers(self):
        mommy.make_recipe(
            'booking.blocktype5', active=False, identifier='test', _quantity=5
        )
        mommy.make_recipe(
            'booking.blocktype5', active=False, identifier='test1', _quantity=5
        )
        inactive_blocktypes = mommy.make_recipe(
            'booking.blocktype5', active=False, identifier='test2', _quantity=5
        )
        self.assertEqual(
            BlockType.objects.filter(active=True).count(), 0
        )
        management.call_command('activate_blocktypes', 'test', 'test1', 'on')
        active_blocktypes = BlockType.objects.filter(active=True)
        self.assertEqual(active_blocktypes.count(), 10)
        for blocktype in inactive_blocktypes:
            self.assertTrue(blocktype not in active_blocktypes)

    def test_activate_blocktypes_emails_support(self):
        mommy.make_recipe(
            'booking.blocktype5', active=False, identifier='test', _quantity=5
        )
        self.assertEqual(
            BlockType.objects.filter(active=True).count(), 0
        )
        management.call_command(
            'activate_blocktypes', 'test', 'on'
        )
        self.assertEqual(
            BlockType.objects.filter(active=True).count(), 5
        )
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(
            email.subject,
            '{} Block types activated'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
            )
        )
        self.assertEqual(email.to, [settings.SUPPORT_EMAIL])

    def test_activate_blocktypes_with_unknown_identifier(self):
        mommy.make_recipe(
            'booking.blocktype5', active=False, identifier='test', _quantity=5
        )
        self.assertEqual(
            BlockType.objects.filter(active=True).count(), 0
        )
        management.call_command(
            'activate_blocktypes', 'unknown', 'on'
        )
        self.assertEqual(
            BlockType.objects.filter(active=True).count(), 0
        )
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(
            email.subject,
            '{} Block types activation attempt failed'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
            )
        )
        self.assertEqual(email.to, [settings.SUPPORT_EMAIL])

    def test_deactivate_blocktypes_with_unknown_identifier(self):
        mommy.make_recipe(
            'booking.blocktype5', active=True, identifier='test', _quantity=5
        )
        self.assertEqual(
            BlockType.objects.filter(active=True).count(), 5
        )
        management.call_command(
            'activate_blocktypes', 'unknown', 'off'
        )
        self.assertEqual(
            BlockType.objects.filter(active=True).count(), 5
        )
        email = mail.outbox[0]
        self.assertEqual(
            email.subject,
            '{} Block types deactivation attempt failed'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
            )
        )

    @patch('booking.management.commands.activate_blocktypes.send_mail')
    def test_activate_blocktypes_with_email_error(self, mock_send_emails):
        mock_send_emails.side_effect = Exception('Error sending mail')
        mommy.make_recipe('booking.blocktype5', active=False, identifier='test')

        self.assertEqual(BlockType.objects.filter(active=True).count(), 0)
        management.call_command('activate_blocktypes', 'test', 'on')

        self.assertEqual(
            BlockType.objects.filter(active=True).count(), 1
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [settings.SUPPORT_EMAIL])
        self.assertEqual(
            mail.outbox[0].subject,
            '{} An error occurred! (Activate blocktypes - '
            'support email)'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
            )
        )

    @patch('booking.management.commands.activate_blocktypes.send_mail')
    def test_fail_to_activate_blocktypes_with_email_error(self, mock_send_emails):
        mock_send_emails.side_effect = Exception('Error sending mail')
        mommy.make_recipe('booking.blocktype5', active=False, identifier='test')

        self.assertEqual(BlockType.objects.filter(active=True).count(), 0)
        management.call_command('activate_blocktypes', 'unknown', 'on')

        self.assertEqual(
            BlockType.objects.filter(active=True).count(), 0
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [settings.SUPPORT_EMAIL])
        self.assertEqual(
            mail.outbox[0].subject,
            '{} An error occurred! (Activate blocktypes - '
            'support email)'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
            )
        )


class ActivateSaleTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.pc_ev_type, _ = EventType.objects.get_or_create(
            event_type='CL', subtype='Pole level class'
        )
        cls.oc_ev_type, _ = EventType.objects.get_or_create(
            event_type='CL', subtype='Other class'
        )
        cls.pp_ev_type, _ = EventType.objects.get_or_create(
            event_type='CL', subtype='Pole practice'
        )

    def setUp(self):
        # redirect stdout so we can test it
        self.output = StringIO()
        self.saved_stdout = sys.stdout
        sys.stdout = self.output

        mommy.make(
           Event, date=timezone.now() + timedelta(1),
           cost=7.50, booking_open=False,
           payment_open=False, event_type=self.pc_ev_type,
           _quantity=5
        )
        mommy.make(
            Event, date=timezone.now() + timedelta(1),
            cost=7.50, booking_open=False,
            payment_open=False, event_type=self.oc_ev_type,
            _quantity=5
        )
        mommy.make(
            Event, date=timezone.now() + timedelta(1),
            cost=4, booking_open=False,
            payment_open=False, event_type=self.pp_ev_type,
            _quantity=5
        )

    def tearDown(self):
        self.output.close()
        sys.stdout = self.saved_stdout

    def test_activate_sale_prices(self):

        management.call_command('sale', 'on')

        classes = Event.objects.filter(event_type__subtype='Pole level class')
        other_classes = Event.objects.filter(event_type__subtype='Other class')
        practices = Event.objects.filter(event_type__subtype='Pole practice')

        self.assertEqual(classes.count(), 5)
        for pc in classes:
            self.assertEqual(pc.cost, 6)
            self.assertTrue(pc.booking_open)
            self.assertTrue(pc.payment_open)

        self.assertEqual(practices.count(), 5)
        for pp in practices:
            self.assertEqual(pp.cost, 2.75)
            self.assertTrue(pp.booking_open)
            self.assertTrue(pp.payment_open)

        self.assertEqual(other_classes.count(), 5)
        for oc in other_classes:
            self.assertEqual(oc.cost, 7.50)
            self.assertFalse(oc.booking_open)
            self.assertFalse(oc.payment_open)

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [settings.SUPPORT_EMAIL])

        management.call_command('sale', 'off')

        classes = Event.objects.filter(event_type__subtype='Pole level class')
        other_classes = Event.objects.filter(event_type__subtype='Other class')
        practices = Event.objects.filter(event_type__subtype='Pole practice')

        self.assertEqual(classes.count(), 5)
        for pc in classes:
            self.assertEqual(pc.cost, 7.50)
            self.assertTrue(pc.booking_open)
            self.assertTrue(pc.payment_open)

        self.assertEqual(practices.count(), 5)
        for pp in practices:
            self.assertEqual(pp.cost, 4.00)
            self.assertTrue(pp.booking_open)
            self.assertTrue(pp.payment_open)

        self.assertEqual(other_classes.count(), 5)
        for oc in other_classes:
            self.assertEqual(oc.cost, 7.50)
            self.assertFalse(oc.booking_open)
            self.assertFalse(oc.payment_open)

    @patch('booking.management.commands.sale.send_mail')
    def test_email_errors(self, mock_send):
        mock_send.side_effect = Exception("Error sending email")
        management.call_command('sale', 'on')

        classes = Event.objects.filter(event_type__subtype='Pole level class')
        other_classes = Event.objects.filter(event_type__subtype='Other class')
        practices = Event.objects.filter(event_type__subtype='Pole practice')

        self.assertEqual(classes.count(), 5)
        for pc in classes:
            self.assertEqual(pc.cost, 6)
            self.assertTrue(pc.booking_open)
            self.assertTrue(pc.payment_open)

        self.assertEqual(practices.count(), 5)
        for pp in practices:
            self.assertEqual(pp.cost, 2.75)
            self.assertTrue(pp.booking_open)
            self.assertTrue(pp.payment_open)

        self.assertEqual(other_classes.count(), 5)
        for oc in other_classes:
            self.assertEqual(oc.cost, 7.50)
            self.assertFalse(oc.booking_open)
            self.assertFalse(oc.payment_open)

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [settings.SUPPORT_EMAIL])
        self.assertEqual(
            email.subject,
            '{} An error occurred! '
            '(Activate class/practice sale - support email)'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
            )
        )

    def test_no_classes_to_change(self):
        Event.objects.all().delete()
        management.call_command('sale', 'on')
        self.assertEqual(
            'No classes/practices to activate\n',
            self.output.getvalue()
        )
        management.call_command('sale', 'off')
        self.assertEqual(
            'No classes/practices to activate\n'
            'No classes/practices to deactivate\n',
            self.output.getvalue()
        )


class CreateFreeMonthlyBlocksTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.event_type = mommy.make(
            EventType, event_type='CL', subtype='Pole level class'
        )

    def test_group_not_created(self):
        self.assertFalse(Block.objects.exists())
        management.call_command('create_free_monthly_blocks')
        email = mail.outbox[0]
        self.assertEqual(
            email.subject,
            '{} Free blocks creation failed'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
                )
        )
        self.assertEqual(
            email.body,
            "Error: Group named 'free_monthly_blocks' does not exist"
        )
        self.assertFalse(Block.objects.exists())

    def test_no_users_in_group(self):
        self.assertFalse(Block.objects.exists())
        Group.objects.create(name='free_monthly_blocks')
        management.call_command('create_free_monthly_blocks')
        email = mail.outbox[0]
        self.assertEqual(
            email.subject,
            '{} Free blocks creation failed'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
                )
        )
        self.assertEqual(
            email.body,
            'No users in free_monthly_blocks group'
        )
        self.assertFalse(Block.objects.exists())

    def test_create_free_blocks(self):
        self.assertFalse(Block.objects.exists())
        group = Group.objects.create(name='free_monthly_blocks')
        user1 = mommy.make(User, first_name='Test', last_name='User1')
        user2 = mommy.make(User, first_name='Test', last_name='User2')
        user3 = mommy.make(User, first_name='Test', last_name='User3')
        for user in [user1, user2]:
            user.groups.add(group)

        management.call_command('create_free_monthly_blocks')
        self.assertEqual(Block.objects.count(), 2)
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(
            email.subject,
            '{} Free blocks created'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
                )
        )
        self.assertEqual(
            email.body,
            'Free 5 class blocks created for Test User1, Test User2'
        )

    def test_dont_create_duplicate_free_blocks(self):
        self.assertFalse(Block.objects.exists())
        group = Group.objects.create(name='free_monthly_blocks')
        user1 = mommy.make(User, first_name='Test', last_name='User1')
        user2 = mommy.make(User, first_name='Test', last_name='User2')
        user3 = mommy.make(User, first_name='Test', last_name='User3')
        for user in [user1, user2]:
            user.groups.add(group)

        management.call_command('create_free_monthly_blocks')
        self.assertEqual(Block.objects.count(), 2)

        # call again; no new blocks created
        management.call_command('create_free_monthly_blocks')
        self.assertEqual(Block.objects.count(), 2)

        email = mail.outbox[-1]
        self.assertEqual(
            email.subject,
            '{} Free blocks not created'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
                )
        )
        self.assertEqual(
            email.body,
            'Free 5 class blocks not created for Test User1, Test User2 as '
            'active free block already exists'
        )

    def test_only_create_free_blocks_if_not_already_active(self):
        self.assertFalse(Block.objects.exists())
        group = Group.objects.create(name='free_monthly_blocks')
        user1 = mommy.make(User, first_name='Test', last_name='User1')
        user2 = mommy.make(User, first_name='Test', last_name='User2')
        user3 = mommy.make(User, first_name='Test', last_name='User3')

        for user in [user1, user2, user3]:
            user.groups.add(group)

        management.call_command('create_free_monthly_blocks')
        self.assertEqual(Block.objects.count(), 3)

        # user1's block has expired
        block1 = Block.objects.get(user=user1)
        block1.start_date = timezone.now() - timedelta(50)
        block1.save()

        # user2's block is full
        block2 = Block.objects.get(user=user2)
        mommy.make_recipe(
            'booking.booking', user=user2, block=block2, _quantity=5
        )

        block3 = Block.objects.get(user=user3)
        self.assertFalse(block1.active_block())
        self.assertFalse(block2.active_block())
        self.assertTrue(block3.active_block())

        # call again; new blocks created for only user1 and user2
        management.call_command('create_free_monthly_blocks')
        self.assertEqual(Block.objects.count(), 5)

        # 3 emails; 1 for first run when the blocks are created, 2 for second
        # run
        self.assertEqual(len(mail.outbox), 3)
        created_email = mail.outbox[1]
        self.assertEqual(
            created_email.subject,
            '{} Free blocks created'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
                )
        )
        self.assertEqual(
            created_email.body,
            'Free 5 class blocks created for Test User1, Test User2'
        )

        not_created_email = mail.outbox[2]
        self.assertEqual(
            not_created_email.subject,
            '{} Free blocks not created'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
                )
        )
        self.assertEqual(
            not_created_email.body,
            'Free 5 class blocks not created for Test User3 as '
            'active free block already exists'
        )

    def test_blocks_created_with_previous_day_start_date(self):
        """
        Check that we can create blocks on 1st of the month, and they will have
        expired on 1st of the next month
        """
        group = Group.objects.create(name='free_monthly_blocks')
        user1 = mommy.make(User, first_name='Test', last_name='User1')
        user2 = mommy.make(User, first_name='Test', last_name='User2')
        user3 = mommy.make(User, first_name='Test', last_name='User3')

        for user in [user1, user2, user3]:
            user.groups.add(group)

        # make blocks on 1st Jan
        with patch(
                'booking.management.commands.create_free_monthly_blocks'
                '.timezone.now',
                return_value=datetime(2016, 1, 1, tzinfo=timezone.utc)
            ):
            management.call_command('create_free_monthly_blocks')

        self.assertEqual(Block.objects.count(), 3)

        # make blocks on 1st Feb; previous blocks are now inactive, so new
        # blocks made
        with patch(
                'booking.management.commands.create_free_monthly_blocks'
                '.timezone.now',
                return_value=datetime(2016, 1, 1, tzinfo=timezone.utc)
            ):
            # blocks are not full, and are paid, so active unless expired
            self.assertEqual(
                [bl for bl in Block.objects.all() if bl.full], []
            )
            self.assertEqual(Block.objects.filter(paid=False).count(), 0)
            management.call_command('create_free_monthly_blocks')
        self.assertEqual(Block.objects.count(), 3)
