import sys

from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

from io import StringIO
from unittest.mock import patch
from model_bakery import baker

from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.conf import settings
from django.core import management
from django.core import mail
from django.db.models import Q
from django.contrib.auth.models import Group, User
from django.utils import timezone

from allauth.socialaccount.models import SocialApp

from paypal.standard.ipn.models import PayPalIPN
from paypal.standard.models import ST_PP_COMPLETED

from accounts.models import OnlineDisclaimer
from activitylog.models import ActivityLog
from booking.models import Event, Block, Booking, EventType, BlockType, \
    TicketBooking, Ticket
from common.tests.helpers import _add_user_email_addresses, PatchRequestMixin
from payments.models import PaypalBookingTransaction
from timetable.models import Session


class ManagementCommandsTests(PatchRequestMixin, TestCase):

    def setUp(self):
        super().setUp()
        # redirect stdout so we can test it
        self.output = StringIO()
        self.saved_stdout = sys.stdout
        sys.stdout = self.output

    def tearDown(self):
        super().tearDown()
        self.output.close()
        sys.stdout = self.saved_stdout

    def test_setup_fb(self):
        self.assertEqual(SocialApp.objects.all().count(), 0)
        management.call_command('setup_fb')
        self.assertEqual(SocialApp.objects.all().count(), 1)

    def test_load_users(self):
        self.assertEqual(User.objects.count(), 0)
        management.call_command('load_users')
        self.assertEqual(User.objects.count(), 6)
        # Disclaimers created for non superusers
        self.assertEqual(OnlineDisclaimer.objects.count(), 5)

        user_ids = list(
            User.objects.values_list('id', flat=True)
        )
        disclaimer_ids = list(
            OnlineDisclaimer.objects.values_list('id', flat=True)
        )

        # users and disclaimers are not overwritten
        management.call_command('load_users')
        new_user_ids = list(
            User.objects.values_list('id', flat=True)
        )
        new_disclaimer_ids = list(
            OnlineDisclaimer.objects.values_list('id', flat=True)
        )

        self.assertCountEqual(user_ids, new_user_ids)
        self.assertCountEqual(disclaimer_ids, new_disclaimer_ids)

    def test_load_users_existing_superuser(self):
        suser = baker.make_recipe(
            'booking.user', username='admin', email='admin@admin.com'
        )
        suser.is_superuser = True
        suser.save()
        self.assertEqual(User.objects.all().count(), 1)
        management.call_command('load_users')
        self.assertEqual(User.objects.all().count(), 6)

        self.assertEqual(
            'Create superuser...\n'
            'Superuser with username "admin" already exists\n'
            'Creating 5 test users\n'
            'Disclaimer created for user test_1\n'
            'Disclaimer created for user test_2\n'
            'Disclaimer created for user test_3\n'
            'Disclaimer created for user test_4\n'
            'Disclaimer created for user test_5\n',
             self.output.getvalue()
        )

    def test_create_events(self):
        self.assertEqual(Event.objects.all().count(), 0)
        management.call_command('create_events')
        self.assertEqual(Event.objects.all().count(), 5)

    @patch('booking.utils.date')
    def test_create_classes_with_manage_command(self, mock_date):
        """
        Create timetable sessions and add classes
        """
        mock_date.today.return_value = datetime(2015, 2, 10)

        self.assertEqual(Event.objects.all().count(), 0)
        management.call_command('create_classes')
        # check that there are now classes on the Monday of the mocked week
        # (mocked now is Wed 10 Feb 2015)
        mon_classes = Event.objects.filter(
            Q(date__gte=datetime(2015, 2, 10, tzinfo=dt_timezone.utc)) &
            Q(date__lte=datetime(2015, 2, 11, tzinfo=dt_timezone.utc))
        )
        self.assertTrue(mon_classes)
        # check that there are now classes on the Monday of the following week
        # (mocked now is Wed 10 Feb 2015)
        next_mon_classes = Event.objects.filter(
            Q(date__gte=datetime(2015, 2, 17, tzinfo=dt_timezone.utc)) &
            Q(date__lte=datetime(2015, 2, 18, tzinfo=dt_timezone.utc))
        )
        self.assertTrue(next_mon_classes)

    def test_create_bookings(self):
        """
        test that create_bookings creates 3 bookings per event
        """
        baker.make_recipe('booking.user', _quantity=3)
        baker.make_recipe('booking.future_EV', _quantity=2)
        self.assertEqual(Booking.objects.all().count(), 0)
        management.call_command('create_bookings')
        self.assertEqual(Booking.objects.all().count(), 6)

    def test_create_bookings_without_users(self):
        """
        test that create_bookings creates users if none exist
        """
        baker.make_recipe('booking.future_EV')
        self.assertEqual(Booking.objects.all().count(), 0)
        self.assertEqual(User.objects.all().count(), 0)
        management.call_command('create_bookings')
        self.assertEqual(Booking.objects.all().count(), 3)
        self.assertEqual(User.objects.all().count(), 6)

    def test_create_bookings_without_events(self):
        """
        test that create_bookings handles being called when there are no events
        """
        self.assertEqual(Booking.objects.all().count(), 0)

        management.call_command('create_bookings')
        # confirm no errors, and no booking are created
        self.assertEqual(Booking.objects.all().count(), 0)

    def test_create_events_and_blocktypes(self):
        """
        test that create_events_and_blocktypes creates the default types
        """
        self.assertEqual(EventType.objects.all().count(), 0)
        self.assertEqual(BlockType.objects.all().count(), 0)

        management.call_command('create_event_and_blocktypes')
        self.assertEqual(EventType.objects.all().count(), 10)
        self.assertEqual(BlockType.objects.all().count(), 7)

    def test_create_events_and_blocktypes_twice(self):
        """
        test that create_events_and_blocktypes does not create duplicates
        """
        self.assertEqual(EventType.objects.all().count(), 0)
        self.assertEqual(BlockType.objects.all().count(), 0)

        management.call_command('create_event_and_blocktypes')
        self.assertEqual(EventType.objects.all().count(), 10)
        self.assertEqual(BlockType.objects.all().count(), 7)

        management.call_command('create_event_and_blocktypes')
        self.assertEqual(EventType.objects.all().count(), 10)
        self.assertEqual(BlockType.objects.all().count(), 7)

    def test_setup_test_data(self):
        self.assertFalse(SocialApp.objects.exists())
        self.assertFalse(User.objects.exists())
        self.assertFalse(Group.objects.exists())
        self.assertFalse(EventType.objects.exists())
        self.assertFalse(BlockType.objects.exists())
        self.assertFalse(Event.objects.exists())
        self.assertFalse(Booking.objects.exists())
        self.assertFalse(Session.objects.exists())

        management.call_command('setup_test_data')

        self.assertEqual(SocialApp.objects.count(), 1)

        # create_groups creates instructors, free5 and free7 blocks;
        self.assertEqual(Group.objects.all().count(), 3)

        # This command just calls a bunch of othere; their content is tested
        # separately; just test relevent objects have been created
        self.assertTrue(User.objects.exists())
        self.assertTrue(OnlineDisclaimer.objects.exists())
        self.assertTrue(Group.objects.exists())
        self.assertTrue(EventType.objects.exists())
        self.assertTrue(BlockType.objects.exists())
        self.assertTrue(Event.objects.exists())
        self.assertTrue(Booking.objects.exists())
        self.assertTrue(Session.objects.exists())


class EmailReminderAndWarningTests(TestCase):

    @patch('booking.management.commands.email_reminders.timezone')
    def test_email_reminders(self, mock_tz):
        """
        Email reminders 24 hours before cancellation period starts
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 10, 19, 0, tzinfo=dt_timezone.utc
            )

        # cancellation period starts 2015/2/11 18:00
        event = baker.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 12, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            cost=10,
            cancellation_period=24)
        # cancellation period starts 2015/2/12 18:00
        event1 = baker.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 13, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            cost=10,
            cancellation_period=24)
        baker.make_recipe(
            'booking.booking', event=event, _quantity=5,
            )
        baker.make_recipe(
            'booking.booking', event=event1, _quantity=5,
            )
        # add user emails
        _add_user_email_addresses(Booking)

        management.call_command('email_reminders')
        # emails are only sent for event1
        self.assertEqual(len(mail.outbox), 5)

    @patch('booking.management.commands.email_reminders.timezone')
    def test_email_reminders_not_sent_for_past_events(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 2, 10, 10, tzinfo=dt_timezone.utc
            )

        # cancellation period starts 2015/2/8 00:00
        event = baker.make_recipe(
            'booking.past_event',
            date=datetime(2015, 2, 9, tzinfo=dt_timezone.utc),
            payment_open=True,
            cost=10,
            cancellation_period=24)

        baker.make_recipe(
            'booking.booking', event=event, _quantity=5,
            )
        _add_user_email_addresses(Booking)
        management.call_command('email_reminders')
        self.assertEqual(len(mail.outbox), 0)

    @patch('booking.management.commands.email_reminders.timezone')
    def test_email_reminders_not_sent_twice(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 19, 0, tzinfo=dt_timezone.utc
            )

        # cancellation period starts 2015/2/12 18:00
        event = baker.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 13, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            cost=10,
            cancellation_period=24)
        baker.make_recipe(
            'booking.booking', event=event, _quantity=5,
            )
        _add_user_email_addresses(Booking)

        management.call_command('email_reminders')
        self.assertEqual(len(mail.outbox), 5)
        # emails are not sent again
        management.call_command('email_reminders')
        self.assertEqual(len(mail.outbox), 5)

    @patch('booking.management.commands.email_reminders.timezone')
    def test_email_reminders_set_flags(self, mock_tz):
        """
        Test that reminder_sent flag set
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 19, 0, tzinfo=dt_timezone.utc
            )

        # cancellation period starts 2015/2/12 18:00
        event = baker.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 13, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            cost=10,
            cancellation_period=24)
        baker.make_recipe(
            'booking.booking', event=event, paid=True, payment_confirmed=True,
            )
        _add_user_email_addresses(Booking)
        management.call_command('email_reminders')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            Booking.objects.filter(reminder_sent=True).count(), 1
            )

    @patch('booking.management.commands.email_reminders.timezone')
    def test_email_reminders_only_sent_for_open_bookings(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 2, 12, 19, 0, tzinfo=dt_timezone.utc
            )

        # cancellation period starts 2015/2/11 18:00
        event = baker.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 13, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            cost=10,
            cancellation_period=24)
        baker.make_recipe(
            'booking.booking', event=event, status='OPEN', _quantity=5
            )
        baker.make_recipe(
            'booking.booking', event=event, status='CANCELLED', _quantity=5
            )
        _add_user_email_addresses(Booking)
        management.call_command('email_reminders')
        self.assertEqual(len(mail.outbox), 5)
        for booking in Booking.objects.filter(status='OPEN'):
            self.assertTrue(booking.reminder_sent)
        for booking in Booking.objects.filter(status='CANCELLED'):
            self.assertFalse(booking.reminder_sent)

    @patch('booking.management.commands.email_warnings.timezone')
    def test_email_warnings(self, mock_tz):
        """
        test email warning is sent for any future events with advance payment required
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 10, 10, 0, tzinfo=dt_timezone.utc
            )

        # cancellation period starts 2015/2/14 17:00
        # payment_due_date 2015/2/11 23:59
        event = baker.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=dt_timezone.utc),
            cancellation_period=1)
        # cancellation period starts 2015/2/14 17:00
        # payment_due_date 2015/2/12 23:59
        event1 = baker.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            cost=10,
            payment_due_date=datetime(2015, 2, 12, tzinfo=dt_timezone.utc),
            cancellation_period=1)
        # no cost, no warnings sent
        event2 = baker.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            cost=0,
            cancellation_period=1)

        baker.make_recipe(
            'booking.booking', event=event, paid=False,
            payment_confirmed=False,
            date_booked=datetime(2015, 2, 9, 19, 30, tzinfo=dt_timezone.utc),
            _quantity=5,
            )
        # checkout time in past 5 mins, no warning sent
        baker.make_recipe(
            'booking.booking', event=event, paid=False,
            payment_confirmed=False,
            date_booked=datetime(2015, 2, 9, 19, 30, tzinfo=dt_timezone.utc),
            checkout_time=datetime(2015, 2, 10, 9, 57, tzinfo=dt_timezone.utc)
        )
        baker.make_recipe(
            'booking.booking', event=event1, paid=False,
            payment_confirmed=False,
            date_booked=datetime(2015, 2, 9, 19, 30, tzinfo=dt_timezone.utc),
            _quantity=5,
            )
        # checkout time in past 5 mins, no warning sent
        baker.make_recipe(
            'booking.booking', event=event1, paid=False,
            payment_confirmed=False,
            date_booked=datetime(2015, 2, 9, 19, 30, tzinfo=dt_timezone.utc),
            checkout_time=datetime(2015, 2, 10, 9, 58, tzinfo=dt_timezone.utc)
        )
        # checkout time more than 5 mins ago, warning sent
        baker.make_recipe(
            'booking.booking', event=event1, paid=False,
            payment_confirmed=False,
            date_booked=datetime(2015, 2, 9, 19, 30, tzinfo=dt_timezone.utc),
            checkout_time=datetime(2015, 2, 10, 9, 50, tzinfo=dt_timezone.utc)
        )
        # no cost for event 2, no warnings sent
        baker.make_recipe(
            'booking.booking', event=event2, paid=False,
            payment_confirmed=False,
            date_booked=datetime(2015, 2, 9, 21, 00, tzinfo=dt_timezone.utc),
            _quantity=5,
            )
        _add_user_email_addresses(Booking)
        management.call_command('email_warnings')
        self.assertEqual(len(mail.outbox), 11)

    @patch('booking.management.commands.email_warnings.timezone')
    def test_email_warnings_sent_if_no_payment_due_date(self, mock_tz):
        """
        test email warning is sent 48 hours before cancellation_period for
        events with no payment_due_date
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 19, 0, tzinfo=dt_timezone.utc
            )

        # cancellation period starts 2015/2/13 18:00
        # payment_due_date None
        event = baker.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            cost=10,
            payment_due_date=None,
            cancellation_period=24)

        baker.make_recipe(
            'booking.booking', event=event, paid=False,
            payment_confirmed=False,
            date_booked=datetime(2015, 2, 11, 14, 30, tzinfo=dt_timezone.utc),
            _quantity=5,
            )
        _add_user_email_addresses(Booking)
        management.call_command('email_warnings')
        self.assertEqual(len(mail.outbox), 5)

    @patch('booking.management.commands.email_warnings.timezone')
    def test_email_warnings_sent_for_booking_made_after_payment_due_date(
            self, mock_tz
    ):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 19, 0, tzinfo=dt_timezone.utc
            )

        # No cancellation period
        # payment_due_date is in the past
        # # SEND WARNING
        event = baker.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            cost=10,
            payment_due_date=datetime(2015, 2, 10, 18, 0, tzinfo=dt_timezone.utc),
            cancellation_period=0)

        baker.make_recipe(
            'booking.booking', event=event, paid=False,
            payment_confirmed=False,
            date_booked=datetime(2015, 2, 11, 14, 30, tzinfo=dt_timezone.utc),
            )

        # Has cancellation period starts 2015/2/13 18:00 (<48 hrs from now)
        # payment_due_date is in the past
        # SEND WARNING
        event1 = baker.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            cost=10,
            payment_due_date=datetime(2015, 2, 10, 18, 0, tzinfo=dt_timezone.utc),
            cancellation_period=24)
        baker.make_recipe(
            'booking.booking', event=event1, paid=False,
            payment_confirmed=False,
            date_booked=datetime(2015, 2, 11, 14, 30, tzinfo=dt_timezone.utc),
            )

        # Has cancellation period starts 2015/2/13 18:00 (>48 hrs from now)
        # payment_due_date is in the past
        # SEND WARNING (ignore cancellation period if payment due date)
        event2 = baker.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            cost=10,
            payment_due_date=datetime(2015, 2, 10, 18, 0, tzinfo=dt_timezone.utc),
            cancellation_period=24)
        baker.make_recipe(
            'booking.booking', event=event2, paid=False,
            payment_confirmed=False,
            date_booked=datetime(2015, 2, 11, 14, 30, tzinfo=dt_timezone.utc),
            )
        _add_user_email_addresses(Booking)
        
        management.call_command('email_warnings')
        self.assertEqual(len(mail.outbox), 3)

        for booking in Booking.objects.all():
            self.assertTrue(booking.warning_sent)

    @patch('booking.management.commands.email_warnings.timezone')
    def test_email_warnings_not_sent_twice(self, mock_tz):

        mock_tz.now.return_value = datetime(
            2015, 2, 10, 10, tzinfo=dt_timezone.utc
            )
        # cancellation period starts 2015/2/13 17:00
        # payment_due_date 2015/2/11 23:59
        event = baker.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 13, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=dt_timezone.utc),
            cancellation_period=1)
        baker.make_recipe(
            'booking.booking', event=event, paid=False,
            payment_confirmed=False,
            date_booked=datetime(2015, 2, 9, 19, 30, tzinfo=dt_timezone.utc),
            _quantity=5,
            )
        
        _add_user_email_addresses(Booking)
        management.call_command('email_warnings')
        self.assertEqual(len(mail.outbox), 5)
        for booking in Booking.objects.all():
            self.assertTrue(booking.warning_sent)

        # no additional emails sent on subsequent calls
        management.call_command('email_warnings')
        self.assertEqual(len(mail.outbox), 5)

    @patch('booking.management.commands.email_warnings.timezone')
    def test_email_warnings_not_sent_outside_hours(self, mock_tz):
        # cancellation period starts 2015/2/13 17:00
        # payment_due_date 2015/2/11 23:59
        event = baker.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 13, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=dt_timezone.utc),
            cancellation_period=1)
        baker.make_recipe(
            'booking.booking', event=event, paid=False,
            payment_confirmed=False,
            date_booked=datetime(2015, 2, 9, 19, 30, tzinfo=dt_timezone.utc),
            _quantity=5,
            )

        _add_user_email_addresses(Booking)

        # Before 7am warnings not sent
        mock_tz.now.return_value = datetime(2015, 2, 10, 6, 59, tzinfo=dt_timezone.utc)
        management.call_command('email_warnings')
        self.assertEqual(len(mail.outbox), 0)

        # After 10pm warnings not sent
        mock_tz.now.return_value = datetime(2015, 2, 10, 22, 1, tzinfo=dt_timezone.utc)
        management.call_command('email_warnings')
        self.assertEqual(len(mail.outbox), 0)

        mock_tz.now.return_value = datetime(2015, 2, 10, 9, 30, tzinfo=dt_timezone.utc)
        management.call_command('email_warnings')
        self.assertEqual(len(mail.outbox), 5)

    @patch('booking.management.commands.email_warnings.timezone')
    def test_email_warnings_only_sent_for_payment_not_confirmed(self, mock_tz):
        """
        test email warning is only sent for bookings that are not marked as
        payment_confirmed
        """
        mock_tz.now.return_value = datetime(2015, 2, 10, 10, tzinfo=dt_timezone.utc)
        # cancellation period starts 2015/2/13 17:00
        # payment_due_date 2015/2/11 23:59
        event = baker.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 13, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=dt_timezone.utc),
            cancellation_period=1)
        baker.make_recipe(
            'booking.booking', event=event, paid=False,
            payment_confirmed=False,
            date_booked=datetime(2015, 2, 9, 19, 30, tzinfo=dt_timezone.utc),
            _quantity=3,
            )
        baker.make_recipe(
            'booking.booking', event=event, paid=True,
            payment_confirmed=True,
            date_booked=datetime(2015, 2, 9, 19, 30, tzinfo=dt_timezone.utc),
            _quantity=3,
            )
        _add_user_email_addresses(Booking)
        
        management.call_command('email_warnings')
        self.assertEqual(len(mail.outbox), 3)
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
            2015, 2, 10, 10, tzinfo=dt_timezone.utc
            )
        event = baker.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 13, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=dt_timezone.utc),
            cancellation_period=1)
        baker.make_recipe(
            'booking.booking', event=event, paid=False,
            payment_confirmed=False, status='OPEN',
            date_booked=datetime(2015, 2, 9, 19, 30, tzinfo=dt_timezone.utc),
            _quantity=3,
            )
        baker.make_recipe(
            'booking.booking', event=event, paid=False,
            payment_confirmed=False, status='CANCELLED',
            date_booked=datetime(2015, 2, 9, 19, 30, tzinfo=dt_timezone.utc),
            _quantity=3,
            )
        _add_user_email_addresses(Booking)
        
        management.call_command('email_warnings')
        self.assertEqual(len(mail.outbox), 3)
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
            2015, 2, 9, 21, 45, tzinfo=dt_timezone.utc
            )
        event = baker.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 13, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=dt_timezone.utc),
            cancellation_period=1)
        booking1 = baker.make_recipe(
            'booking.booking', event=event, paid=False,
            payment_confirmed=False, status='OPEN',
            date_booked=datetime(2015, 2, 9, 19, 30, tzinfo=dt_timezone.utc)
            )
        booking2 = baker.make_recipe(
            'booking.booking', event=event, paid=False,
            payment_confirmed=False, status='OPEN',
            date_booked=datetime(2015, 2, 9, 20, 30, tzinfo=dt_timezone.utc)
            )
        _add_user_email_addresses(Booking)
        management.call_command('email_warnings')
        self.assertEqual(len(mail.outbox), 1)
        booking1.refresh_from_db()
        booking2.refresh_from_db()
        self.assertTrue(booking1.warning_sent)
        self.assertFalse(booking2.warning_sent)

    @patch('booking.management.commands.email_warnings.timezone')
    def test_email_warnings_paypal_paid_bookings(self, mock_tz):
        """
        test email warning is sent for any future events with advance payment required
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 10, 10, 0, tzinfo=dt_timezone.utc
            )

        # cancellation period starts 2015/2/14 17:00
        # payment_due_date 2015/2/11 23:59
        event = baker.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=dt_timezone.utc),
            cancellation_period=1)

        baker.make_recipe(
            'booking.booking', event=event, paid=False,
            payment_confirmed=False,
            date_booked=datetime(2015, 2, 9, 19, 30, tzinfo=dt_timezone.utc),
            _quantity=5,
            )
        # bookings which are actually paid but for whatever reason haven't been marked so
        booking_paid_by_paypal = baker.make_recipe(
            'booking.booking', event=event, paid=False,
            payment_confirmed=False, paypal_pending=True,
            date_booked=datetime(2015, 2, 9, 19, 30, tzinfo=dt_timezone.utc),
        )
        pptrans = baker.make(PaypalBookingTransaction, booking=booking_paid_by_paypal, invoice_id="test")
        baker.make(PayPalIPN, invoice="test", txn_id="test", payment_status=ST_PP_COMPLETED)

        booking_paid_by_block = baker.make_recipe(
            'booking.booking', event=event, paid=False,
            payment_confirmed=False,
            date_booked=datetime(2015, 2, 9, 19, 30, tzinfo=dt_timezone.utc),
        )
        block = baker.make_recipe("booking.block")
        # use update to add the block, to bypass the save method
        Booking.objects.filter(id=booking_paid_by_block.id).update(block=block)

        # assert these paid bookings are currently marked as unpaid
        booking_paid_by_block.refresh_from_db()
        booking_paid_by_paypal.refresh_from_db()
        assert booking_paid_by_block.paid is False
        assert booking_paid_by_paypal.paid is False

        _add_user_email_addresses(Booking)
        management.call_command('email_warnings')
        # only the 5 truely unpaid bookings get emails
        self.assertEqual(len(mail.outbox), 5)

        # bookings are now marked as paid
        for booking in [booking_paid_by_paypal, booking_paid_by_block]:
            booking.refresh_from_db()
            assert booking.paid is True
            assert booking.payment_confirmed is True
            assert booking.paypal_pending is False
        pptrans.refresh_from_db()
        assert pptrans.transaction_id == "test"


class CancelUnpaidBookingsTests(TestCase):

    def setUp(self):
        self.event = baker.make_recipe(
            'booking.future_EV',
            date=datetime(2015, 2, 13, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            cost=10,
            payment_due_date=datetime(2015, 2, 9, tzinfo=dt_timezone.utc),
            advance_payment_required=True,
            cancellation_period=1)
        self.unpaid = baker.make_recipe(
            'booking.booking', event=self.event, paid=False,
            payment_confirmed=False, status='OPEN',
            user__email="unpaid@test.com",
            date_booked=datetime(
                2015, 2, 9, 18, 0, tzinfo=dt_timezone.utc
            ),
            warning_sent=True,
            date_warning_sent = datetime(2015, 2, 9, 20, 0, tzinfo=dt_timezone.utc)
        )
        self.paid = baker.make_recipe(
            'booking.booking', event=self.event, paid=True,
            payment_confirmed=True, status='OPEN',
            user__email="paid@test.com",
            date_booked= datetime(
                2015, 2, 9, 18, 0, tzinfo=dt_timezone.utc
            )
        )

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_cancel_unpaid_bookings(self, mock_tz):
        """
        test unpaid bookings are cancelled
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 10, 10, tzinfo=dt_timezone.utc
        )
        self.assertEqual(
            self.unpaid.status, 'OPEN', self.unpaid.status
        )
        self.assertEqual(
            self.paid.status, 'OPEN', self.paid.status
        )
        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        unpaid_booking = Booking.objects.get(id=self.unpaid.id)
        paid_booking = Booking.objects.get(id=self.paid.id)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(
            unpaid_booking.status, 'CANCELLED', unpaid_booking.status
        )
        self.assertEqual(
            paid_booking.status, 'OPEN', paid_booking.status
        )

        # auto_cancelled set to True on cancelled bookings
        self.assertTrue(unpaid_booking.auto_cancelled)
        self.assertFalse(paid_booking.auto_cancelled)

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_cancel_unpaid_bookings_no_autocanceling(self, mock_tz):
        """
        test unpaid bookings are cancelled
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 10, 10, tzinfo=dt_timezone.utc
        )
        with override_settings(ENFORCE_AUTO_CANCELLATION=False):
            management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        unpaid_booking = Booking.objects.get(id=self.unpaid.id)
        paid_booking = Booking.objects.get(id=self.paid.id)
        self.assertEqual(len(mail.outbox), 2)
        assert unpaid_booking.status == 'CANCELLED'
        assert paid_booking.status == 'OPEN'

        # no auto_cancelled set as per setting
        assert not unpaid_booking.auto_cancelled
        assert not paid_booking.auto_cancelled

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_only_cancel_unpaid_bookings_within_day_hours(self, mock_tz):
        """
        test unpaid bookings are cancelled only between 9am and 10pm
        """
        self.assertEqual(
            self.unpaid.status, 'OPEN', self.unpaid.status
        )

        mock_tz.now.return_value = datetime(2015, 2, 10, 8, 59, tzinfo=dt_timezone.utc)
        management.call_command('cancel_unpaid_bookings')
        self.unpaid.refresh_from_db()
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(self.unpaid.status, 'OPEN', self.unpaid.status)

        mock_tz.now.return_value = datetime(2015, 2, 10, 22, 00, tzinfo=dt_timezone.utc)
        management.call_command('cancel_unpaid_bookings')
        self.unpaid.refresh_from_db()
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(self.unpaid.status, 'OPEN', self.unpaid.status)


        mock_tz.now.return_value = datetime(2015, 2, 10, 9, 10, tzinfo=dt_timezone.utc)
        management.call_command('cancel_unpaid_bookings')
        self.unpaid.refresh_from_db()
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(self.unpaid.status, 'CANCELLED', self.unpaid.status)

        # auto_cancelled set to True on cancelled bookings
        self.assertTrue(self.unpaid.auto_cancelled)

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_dont_cancel_if_advance_payment_not_required(self, mock_tz):
        """
        test unpaid bookings are not cancelled if advance payment not required
        for event
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 10, 10, tzinfo=dt_timezone.utc
        )
        # set payment_due_date to None, otherwise advance_payment_required is
        # automatically set to True
        self.event.payment_due_date = None
        self.event.advance_payment_required = False
        self.event.save()
        self.assertEqual(
            self.unpaid.status, 'OPEN', self.unpaid.status
        )
        self.assertEqual(
            self.paid.status, 'OPEN', self.paid.status
        )
        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        unpaid_booking = Booking.objects.get(id=self.unpaid.id)
        paid_booking = Booking.objects.get(id=self.paid.id)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(
            unpaid_booking.status, 'OPEN', unpaid_booking.status
        )
        self.assertEqual(
            paid_booking.status, 'OPEN', paid_booking.status
        )
        # auto_cancelled set to True only on cancelled bookings
        self.assertFalse(unpaid_booking.auto_cancelled)
        self.assertFalse(paid_booking.auto_cancelled)

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_dont_cancel_for_events_with_no_cost(self, mock_tz):
        """
        test unpaid bookings are not cancelled if advance payment not required
        for event
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 10, 10, tzinfo=dt_timezone.utc
        )
        self.event.cost = 0
        self.event.save()
        self.assertEqual(
            self.unpaid.status, 'OPEN', self.unpaid.status
        )
        self.assertEqual(
            self.paid.status, 'OPEN', self.paid.status
        )
        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        unpaid_booking = Booking.objects.get(id=self.unpaid.id)
        paid_booking = Booking.objects.get(id=self.paid.id)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(
            unpaid_booking.status, 'OPEN', unpaid_booking.status
        )
        self.assertEqual(
            paid_booking.status, 'OPEN', paid_booking.status
        )

        # auto_cancelled set to True only on cancelled bookings
        self.assertFalse(unpaid_booking.auto_cancelled)
        self.assertFalse(paid_booking.auto_cancelled)

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_dont_cancel_for_events_in_the_past(self, mock_tz):
        """
        test don't cancel or send emails for past events
        """
        mock_tz.now.return_value = datetime(
            2016, 2, 10, 10, tzinfo=dt_timezone.utc
        )
        self.assertEqual(
            self.unpaid.status, 'OPEN', self.unpaid.status
        )
        self.assertEqual(
            self.paid.status, 'OPEN', self.paid.status
        )
        self.assertTrue(timezone.now() > self.event.date)
        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking and studio once
        # for all cancelled bookings
        unpaid_booking = Booking.objects.get(id=self.unpaid.id)
        paid_booking = Booking.objects.get(id=self.paid.id)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(
            unpaid_booking.status, 'OPEN', unpaid_booking.status
        )
        self.assertEqual(
            paid_booking.status, 'OPEN', paid_booking.status
        )

        # auto_cancelled set to True only on cancelled bookings
        self.assertFalse(unpaid_booking.auto_cancelled)
        self.assertFalse(paid_booking.auto_cancelled)

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_dont_cancel_for_already_cancelled(self, mock_tz):
        """
        ignore already cancelled bookings
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 10, 10, tzinfo=dt_timezone.utc
        )
        self.unpaid.status = 'CANCELLED'
        self.unpaid.save()
        self.assertEqual(
            self.unpaid.status, 'CANCELLED', self.unpaid.status
        )
        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking and studio once
        # for all cancelled bookings
        unpaid_booking = Booking.objects.get(id=self.unpaid.id)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(
            unpaid_booking.status, 'CANCELLED', unpaid_booking.status
        )

        # auto_cancelled set to True only on cancelled bookings
        self.assertFalse(unpaid_booking.auto_cancelled)
        self.assertFalse(self.paid.auto_cancelled)

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_dont_cancel_bookings_within_cancellation_period_without_warning_sent(self, mock_tz):
        """
        Only cancel bookings made within the cancellation period if a warning has been sent
        """
        mock_tz.now.return_value = datetime(2015, 2, 10, 18, 0, tzinfo=dt_timezone.utc)
        # reset warning flags
        self.unpaid.warning_sent = False
        self.unpaid.date_warning_sent = None
        self.unpaid.save()

        self.assertEqual(self.unpaid.status, 'OPEN')
        self.assertFalse(self.unpaid.warning_sent)
        self.assertIsNone(self.unpaid.date_warning_sent)
        management.call_command('cancel_unpaid_bookings')
        self.unpaid.refresh_from_db()
        # still open
        self.assertEqual(self.unpaid.status, 'OPEN')

        # set the warning sent flag to < 2hrs ago
        self.unpaid.warning_sent = True
        self.unpaid.date_warning_sent = datetime(2015, 2, 10, 17, 0, tzinfo=dt_timezone.utc)
        self.unpaid.save()
        management.call_command('cancel_unpaid_bookings')
        self.unpaid.refresh_from_db()
        # still open
        self.assertEqual(self.unpaid.status, 'OPEN')

        # set the warning sent flag to > 2hrs ago
        self.unpaid.warning_sent = True
        self.unpaid.date_warning_sent = datetime(2015, 2, 10, 15, 0, tzinfo=dt_timezone.utc)
        self.unpaid.save()
        management.call_command('cancel_unpaid_bookings')
        self.unpaid.refresh_from_db()
        # now cancelled
        self.assertEqual(self.unpaid.status, 'CANCELLED')

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_dont_cancel_unpaid_bookings_with_checkout_time_in_past_5_mins(self, mock_tz):
        """
        test unpaid bookings are not cancelled if checkout out in past 5 mins
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 10, 10, tzinfo=dt_timezone.utc
        )
        self.unpaid.checkout_time =  datetime(
            2015, 2, 10, 9, 56, tzinfo=dt_timezone.utc
        )
        self.unpaid.save()
        self.assertEqual(
            self.unpaid.status, 'OPEN', self.unpaid.status
        )
        self.assertEqual(
            self.paid.status, 'OPEN', self.paid.status
        )
        management.call_command('cancel_unpaid_bookings')
        # no emails are sent
        unpaid_booking = Booking.objects.get(id=self.unpaid.id)
        paid_booking = Booking.objects.get(id=self.paid.id)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(
            unpaid_booking.status, 'OPEN', unpaid_booking.status
        )
        self.assertEqual(
            paid_booking.status, 'OPEN', paid_booking.status
        )

        self.assertFalse(unpaid_booking.auto_cancelled)
        self.assertFalse(paid_booking.auto_cancelled)

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_only_send_one_email_to_studio(self, mock_tz):
        """
        users are emailed per booking, studio just receives one summary
        email
        """
        mock_tz.now.return_value = datetime(2015, 2, 10, 10, tzinfo=dt_timezone.utc)
        for i in range(5):
            baker.make_recipe(
                'booking.booking', event=self.event,
                status='OPEN', paid=False,
                payment_confirmed=False,
                user__email="unpaid_user{}@test.com".format(i),
                date_booked= datetime(2015, 2, 9, tzinfo=dt_timezone.utc),
                warning_sent=True,
                date_warning_sent= datetime(2015, 2, 9, 2, tzinfo=dt_timezone.utc),
            )

        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking (6) and studio once
        # for all cancelled bookings
        unpaid_booking = Booking.objects.get(id=self.unpaid.id)
        self.assertEqual(len(mail.outbox), 7)
        self.assertEqual(
            unpaid_booking.status, 'CANCELLED', unpaid_booking.status
        )
        self.assertEqual(
            Booking.objects.filter(status='CANCELLED').count(), 6
        )
        cancelled_booking_emails = [
            [booking.user.email] for booking
            in Booking.objects.filter(status='CANCELLED')
        ]
        all_emails = cancelled_booking_emails + [[settings.DEFAULT_STUDIO_EMAIL]]
        self.assertEqual(
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
        mock_tz.now.return_value = datetime(2015, 2, 10, 10, tzinfo=dt_timezone.utc)
        for i in range(5):
            baker.make_recipe(
                'booking.booking', event=self.event,
                status='OPEN', paid=False,
                payment_confirmed=False,
                user__email="unpaid_user{}@test.com".format(i),
                date_booked= datetime(2015, 2, 9, tzinfo=dt_timezone.utc),
                warning_sent=True,
                date_warning_sent= datetime(2015, 2, 9, 2, tzinfo=dt_timezone.utc),
            )

        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking (6); none to studio
        self.assertEqual(len(mail.outbox), 6)
        cancelled_booking_emails = [
            [booking.user.email] for booking
            in Booking.objects.filter(status='CANCELLED')
        ]
        self.assertEqual(
            sorted(cancelled_booking_emails),
            sorted([email.to for email in mail.outbox])
        )

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_cancelling_for_full_event_emails_waiting_list(self, mock_tz):
        """
        Test that automatically cancelling a booking for a full event emails
        any users on the waiting list
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 13, 17, 15, tzinfo=dt_timezone.utc
        )

        # make full event (setup has one paid and one unpaid)
        # cancellation period =1, date = 2015, 2, 13, 18, 0
        self.event.max_participants = 2
        self.event.save()

        # make some waiting list users
        for i in range(3):
            baker.make_recipe(
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
    def test_cancelling_more_than_once_only_emails_once(self, mock_tz):
        """
        Test that the waiting list is only emailed once if more than one
        booking is cancelled
        """
        mock_tz.now.return_value = datetime(2015, 2, 13, 17, 15, tzinfo=dt_timezone.utc)

        # make full event (setup has one paid and one unpaid)
        # cancellation period =1, date = 2015, 2, 13, 18, 0
        self.event.max_participants = 3
        self.event.save()

        # make another booking that will be cancelled
        baker.make_recipe(
            'booking.booking', event=self.event, paid=False,
            payment_confirmed=False, status='OPEN',
            user__email="unpaid@test.com",
            date_booked=datetime(2015, 2, 9, 18, 0, tzinfo=dt_timezone.utc),
            warning_sent=True,
            date_warning_sent=datetime(2015, 2, 9, 20, 0, tzinfo=dt_timezone.utc),
        )

        # make some waiting list users
        for i in range(3):
            baker.make_recipe(
                'booking.waiting_list_user', event=self.event,
                user__email='test{}@test.com'.format(i)
            )

        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking (2) and
        # one email with bcc to waiting list (1) and studio (1)
        # waiting list email sent after the two user emails
        self.assertEqual(len(mail.outbox), 4)
        self.assertEqual(
            sorted(mail.outbox[2].bcc),
            ['test0@test.com', 'test1@test.com', 'test2@test.com']
        )
        for email in [mail.outbox[0], mail.outbox[1], mail.outbox[3]]:
            self.assertEqual(email.bcc, [])

        self.assertEqual(Booking.objects.filter(status='CANCELLED').count(), 2)

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_cancelling_not_full_event_emails_waiting_list(self, mock_tz):
        """
        Test that the waiting list is still emailed if event not full
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 13, 17, 15, tzinfo=dt_timezone.utc
        )

        # make full event (setup has one paid and one unpaid)
        # cancellation period =1, date = 2015, 2, 13, 18, 0
        self.event.max_participants = 3
        self.event.save()

        # make some waiting list users
        for i in range(3):
            baker.make_recipe(
                'booking.waiting_list_user', event=self.event,
                user__email='test{}@test.com'.format(i)
            )

        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking (1) studio (1) and waitinglist (1, with bcc)
        self.assertEqual(len(mail.outbox), 3)

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_dont_cancel_rebookings_within_cancellation_period_without_warning_sent(self, mock_tz):
        """
        Only cancel bookings made within the cancellation period if a warning has been sent
        """
        mock_tz.now.return_value = datetime(2015, 2, 10, 18, 0, tzinfo=dt_timezone.utc)
        # cancel booking to reset warning flags
        self.unpaid.status = "CANCELLED"
        self.unpaid.save()
        # rebook
        self.unpaid.status = "OPEN"
        self.unpaid.date_rebooked = datetime(2015, 2, 10, 12, 30, tzinfo=dt_timezone.utc)
        self.unpaid.save()

        self.assertEqual(self.unpaid.status, 'OPEN')
        self.assertFalse(self.unpaid.warning_sent)
        self.assertIsNone(self.unpaid.date_warning_sent)
        management.call_command('cancel_unpaid_bookings')
        self.unpaid.refresh_from_db()
        # still open
        self.assertEqual(self.unpaid.status, 'OPEN')

        # set the warning sent flag to < 2hrs ago
        self.unpaid.warning_sent = True
        self.unpaid.date_warning_sent = datetime(2015, 2, 10, 17, 0, tzinfo=dt_timezone.utc)
        self.unpaid.save()
        management.call_command('cancel_unpaid_bookings')
        self.unpaid.refresh_from_db()
        # still open
        self.assertEqual(self.unpaid.status, 'OPEN')

        # set the warning sent flag to > 2hrs ago
        self.unpaid.warning_sent = True
        self.unpaid.date_warning_sent = datetime(2015, 2, 10, 15, 0, tzinfo=dt_timezone.utc)
        self.unpaid.save()
        management.call_command('cancel_unpaid_bookings')
        self.unpaid.refresh_from_db()
        # now cancelled
        self.assertEqual(self.unpaid.status, 'CANCELLED')

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_cancel_bookings_over_payment_time_allowed_without_warnings(
            self, mock_tz
    ):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 10, 0, tzinfo=dt_timezone.utc
        )
        self.event.payment_due_date = None
        self.event.payment_time_allowed = 8
        self.event.save()

        self.unpaid.date_booked = datetime(
            2015, 2, 11, 3, 0, tzinfo=dt_timezone.utc
        )
        self.unpaid.warning_sent = False
        self.unpaid.save()
        # self.unpaid.date_booked is within 8 hrs, so not cancelled
        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(self.unpaid.status, "OPEN")


        # set date booked to >8 hrs ago
        self.unpaid.date_booked = datetime(
            2015, 2, 11, 1, 59, tzinfo=dt_timezone.utc
        )
        self.unpaid.save()
        # self.unpaid.date_booked is within 4 hrs, so not cancelled
        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(self.unpaid.status, "CANCELLED")
        # even though warning has not been sent
        self.assertFalse(self.unpaid.warning_sent)

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_free_class_requested_allows_24_hrs_after_booking(
            self, mock_tz
    ):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 10, 0, tzinfo=dt_timezone.utc
        )
        self.event.payment_due_date = None
        self.event.payment_time_allowed = 6
        self.event.save()

        self.unpaid.date_booked = datetime(
            2015, 2, 11, 3, 0, tzinfo=dt_timezone.utc
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
            2015, 2, 10, 9, 59, tzinfo=dt_timezone.utc
        )
        self.unpaid.save()
        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(self.unpaid.status, "CANCELLED")
        # even though warning has not been sent
        self.assertFalse(self.unpaid.warning_sent)

    @patch('booking.management.commands.cancel_unpaid_bookings.timezone')
    def test_free_class_requested_allows_24_hrs_after_rebooking(
            self, mock_tz
    ):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 10, 0, tzinfo=dt_timezone.utc
        )
        self.event.payment_due_date = None
        self.event.payment_time_allowed = 6
        self.event.save()

        self.unpaid.date_booked = datetime(
            2015, 2, 9, 3, 0, tzinfo=dt_timezone.utc
        )
        self.unpaid.date_rebooked = datetime(
            2015, 2, 11, 3, 0, tzinfo=dt_timezone.utc
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
            2015, 2, 10, 9, 59, tzinfo=dt_timezone.utc
        )
        self.unpaid.save()
        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEqual(len(mail.outbox), 2)
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
            2015, 2, 11, 10, 0, tzinfo=dt_timezone.utc
            )

        # payment_due_date 2015/2/11 23:59 (within 24hrs - warnings sent)
        ticketed_event = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            ticket_cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=dt_timezone.utc),
        )
        # advance payment not required - warnings not sent
        ticketed_event1 = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            ticket_cost=10,
            advance_payment_required=False
        )

        baker.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=dt_timezone.utc),
            _quantity=5,
            )
        # checkout time in past 5 mins, not sent
        baker.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=dt_timezone.utc),
            checkout_time=datetime(
                2015, 2, 11, 9, 56, tzinfo=dt_timezone.utc
            )
            )
        baker.make(
            TicketBooking,  ticketed_event=ticketed_event1, paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=dt_timezone.utc),
            _quantity=5,
            )

        _add_user_email_addresses(TicketBooking)

        for ticket_booking in TicketBooking.objects.all():
            baker.make(Ticket, ticket_booking=ticket_booking)

        management.call_command('email_ticket_booking_warnings')
        self.assertEqual(len(mail.outbox), 5)

    @patch('booking.management.commands.email_ticket_booking_warnings.timezone')
    def test_email_warnings_not_sent_out_of_hours(self, mock_tz):
        """
        test email warnings only sent between 7am and 10pm
        """
        # payment_due_date 2015/2/11 23:59 (within 24hrs - warnings sent)
        ticketed_event = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            ticket_cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=dt_timezone.utc),
        )

        baker.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=dt_timezone.utc),
            _quantity=5,
            )

        _add_user_email_addresses(TicketBooking)

        for ticket_booking in TicketBooking.objects.all():
            baker.make(Ticket, ticket_booking=ticket_booking)

        mock_tz.now.return_value = datetime(2015, 2, 11, 6, 59, tzinfo=dt_timezone.utc)
        management.call_command('email_ticket_booking_warnings')
        self.assertEqual(len(mail.outbox), 0)

        mock_tz.now.return_value = datetime(2015, 2, 11, 22, 5, tzinfo=dt_timezone.utc)
        management.call_command('email_ticket_booking_warnings')
        self.assertEqual(len(mail.outbox), 0)

        mock_tz.now.return_value = datetime(2015, 2, 11, 21, 59, tzinfo=dt_timezone.utc)
        management.call_command('email_ticket_booking_warnings')
        self.assertEqual(len(mail.outbox), 5)


    @patch('booking.management.commands.email_ticket_booking_warnings.timezone')
    def test_email_warnings_sent_if_both_due_date_and_time_allowed(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 10, 0, tzinfo=dt_timezone.utc
            )

        # payment_due_date 2015/2/11 23:59 (within 24hrs - warnings sent)
        # payment_time_allowed is set
        ticketed_event = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            ticket_cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=dt_timezone.utc),
            payment_time_allowed=4,
        )

        baker.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=dt_timezone.utc),
            _quantity=5,
            )
        _add_user_email_addresses(TicketBooking)

        for ticket_booking in TicketBooking.objects.all():
            baker.make(Ticket, ticket_booking=ticket_booking)

        management.call_command('email_ticket_booking_warnings')
        self.assertEqual(len(mail.outbox), 5)

    @patch('booking.management.commands.email_ticket_booking_warnings.timezone')
    def test_email_warnings_not_sent_twice(self, mock_tz):

        mock_tz.now.return_value = datetime(
            2015, 2, 11, 10, 0, tzinfo=dt_timezone.utc
            )

        # payment_due_date 2015/2/11 23:59 (within 24hrs - warnings sent)
        ticketed_event = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            ticket_cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=dt_timezone.utc),
        )

        baker.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=dt_timezone.utc),
            _quantity=5,
            )
        _add_user_email_addresses(TicketBooking)

        for ticket_booking in TicketBooking.objects.all():
            baker.make(Ticket, ticket_booking=ticket_booking)

        management.call_command('email_ticket_booking_warnings')
        self.assertEqual(len(mail.outbox), 5)
        for ticket_booking in TicketBooking.objects.all():
            self.assertTrue(ticket_booking.warning_sent)

        # no additional emails sent on subsequent calls
        management.call_command('email_ticket_booking_warnings')
        self.assertEqual(len(mail.outbox), 5)

    @patch('booking.management.commands.email_ticket_booking_warnings.timezone')
    def test_email_warnings_only_sent_for_unpaid(self, mock_tz):
        """
        test email warning is only sent for bookings that are not marked as
        payment_confirmed
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 10, 0, tzinfo=dt_timezone.utc
            )

        # payment_due_date 2015/2/11 23:59 (within 24hrs - warnings sent)
        ticketed_event = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            ticket_cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=dt_timezone.utc),
        )

        baker.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=dt_timezone.utc),
            _quantity=5,
            )
        baker.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=True,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=dt_timezone.utc),
            _quantity=5,
            )
        _add_user_email_addresses(TicketBooking)
        for ticket_booking in TicketBooking.objects.all():
            baker.make(Ticket, ticket_booking=ticket_booking)

        management.call_command('email_ticket_booking_warnings')
        self.assertEqual(len(mail.outbox), 5)
        for ticket_booking in TicketBooking.objects.filter(paid=False):
            self.assertTrue(ticket_booking.warning_sent)
        for ticket_booking in TicketBooking.objects.filter(paid=True):
            self.assertFalse(ticket_booking.warning_sent)

    @patch('booking.management.commands.email_ticket_booking_warnings.timezone')
    def test_email_warnings_only_sent_for_open_bookings(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 10, 0, tzinfo=dt_timezone.utc
            )

        # payment_due_date 2015/2/11 23:59 (within 24hrs - warnings sent)
        ticketed_event = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            ticket_cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=dt_timezone.utc),
        )

        baker.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=dt_timezone.utc),
            _quantity=5,
            )
        baker.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=False,
            cancelled=True,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=dt_timezone.utc),
            _quantity=5,
            )
        _add_user_email_addresses(TicketBooking)
        for ticket_booking in TicketBooking.objects.all():
            baker.make(Ticket, ticket_booking=ticket_booking)

        management.call_command('email_ticket_booking_warnings')
        self.assertEqual(len(mail.outbox), 5)
        for ticket_booking in TicketBooking.objects.filter(cancelled=False):
            self.assertTrue(ticket_booking.warning_sent)
        for ticket_booking in TicketBooking.objects.filter(cancelled=True):
            self.assertFalse(ticket_booking.warning_sent)

    @patch('booking.management.commands.email_ticket_booking_warnings.timezone')
    def test_email_warnings_only_sent_for_open_events(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 10, 0, tzinfo=dt_timezone.utc
            )

        # payment_due_date 2015/2/11 23:59 (within 24hrs - warnings sent)
        ticketed_event = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            ticket_cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=dt_timezone.utc),
        )
        ticketed_event_cancelled = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            ticket_cost=10,
            cancelled=True,
            payment_due_date=datetime(2015, 2, 11, tzinfo=dt_timezone.utc),
        )
        baker.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=dt_timezone.utc),
            _quantity=5,
            )
        baker.make(
            TicketBooking,  ticketed_event=ticketed_event_cancelled,
            paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=dt_timezone.utc),
            _quantity=5,
            )
        _add_user_email_addresses(TicketBooking)
        for ticket_booking in TicketBooking.objects.all():
            baker.make(Ticket, ticket_booking=ticket_booking)

        management.call_command('email_ticket_booking_warnings')
        self.assertEqual(len(mail.outbox), 5)
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
            2015, 2, 11, 10, 0, tzinfo=dt_timezone.utc
            )

        # payment_due_date 2015/2/11 23:59 (within 24hrs - warnings sent)
        ticketed_event = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            ticket_cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=dt_timezone.utc),
        )
        baker.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=dt_timezone.utc),
            _quantity=5,
            )
        _add_user_email_addresses(TicketBooking)
        for ticket_booking in TicketBooking.objects.all()[0:5]:
            baker.make(Ticket, ticket_booking=ticket_booking)

        management.call_command('email_ticket_booking_warnings')
        self.assertEqual(len(mail.outbox), 5)
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
            2015, 2, 11, 10, 0, tzinfo=dt_timezone.utc
            )

        # payment_due_date 2015/2/11 23:59 (within 24hrs - warnings sent)
        ticketed_event = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            ticket_cost=10,
            payment_due_date=datetime(2015, 2, 11, tzinfo=dt_timezone.utc),
        )
        booking1 = baker.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=dt_timezone.utc),
            )
        booking2 = baker.make(
            TicketBooking,  ticketed_event=ticketed_event, paid=False,
            date_booked=datetime(2015, 2, 11, 8, 5, tzinfo=dt_timezone.utc),
            )
        _add_user_email_addresses(TicketBooking)
        for ticket_booking in TicketBooking.objects.all():
            baker.make(Ticket, ticket_booking=ticket_booking)

        management.call_command('email_ticket_booking_warnings')
        self.assertEqual(len(mail.outbox), 1)
        booking1.refresh_from_db()
        booking2.refresh_from_db()
        self.assertTrue(booking1.warning_sent)
        self.assertFalse(booking2.warning_sent)


class CancelUnpaidTicketBookingsTests(TestCase):

    def setUp(self):
        # payment_due_date 2015/2/10 23:59
        self.ticketed_event = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=datetime(2015, 2, 14, 18, 0, tzinfo=dt_timezone.utc),
            payment_open=True,
            ticket_cost=10,
            advance_payment_required=True,
            payment_due_date=datetime(2015, 2, 10, tzinfo=dt_timezone.utc),
        )
        self.paid = baker.make(
            TicketBooking,  ticketed_event=self.ticketed_event, paid=True,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=dt_timezone.utc),
            warning_sent=True,
            user__email='paid@test.com', purchase_confirmed=True
            )
        self.unpaid = baker.make(
            TicketBooking,  ticketed_event=self.ticketed_event, paid=False,
            date_booked=datetime(2015, 2, 1, 0, 0, tzinfo=dt_timezone.utc),
            warning_sent=True,
            user__email='unpaid@test.com', purchase_confirmed=True,
            date_warning_sent = datetime(2015, 2, 1, 2, 0, tzinfo=dt_timezone.utc)
            )
        for booking in [self.paid, self.unpaid]:
            baker.make(Ticket, ticket_booking=booking)
        _add_user_email_addresses(TicketBooking)

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
            2015, 2, 11, 10, tzinfo=dt_timezone.utc
        )

        self.assertFalse(self.unpaid.cancelled)
        self.assertFalse(self.paid.cancelled)

        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.paid.refresh_from_db()
        self.assertEqual(len(mail.outbox), 2)
        self.assertTrue(self.unpaid.cancelled)
        self.assertFalse(self.paid.cancelled)

    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_only_cancel_unpaid_bookings_in_day_hours(self, mock_tz):
        """
        test unpaid bookings are cancelled between 9am and 10om only
        """
        self.assertFalse(self.unpaid.cancelled)

        mock_tz.now.return_value = datetime(2015, 2, 12, 8, 59, tzinfo=dt_timezone.utc)
        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(self.unpaid.cancelled)

        mock_tz.now.return_value = datetime(2015, 2, 12, 22, 00, tzinfo=dt_timezone.utc)
        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(self.unpaid.cancelled)

        mock_tz.now.return_value = datetime(2015, 2, 12, 9, 5, tzinfo=dt_timezone.utc)
        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEqual(len(mail.outbox), 2)
        self.assertTrue(self.unpaid.cancelled)


    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_dont_cancel_if_advance_payment_not_required(self, mock_tz):
        """
        test unpaid bookings are not cancelled if advance payment not required
        for event
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 10, tzinfo=dt_timezone.utc
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
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(self.unpaid.cancelled)
        self.assertFalse(self.paid.cancelled)

    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_dont_cancel_for_events_with_no_cost(self, mock_tz):
        """
        test unpaid bookings are not cancelled if no cost for event
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 10, tzinfo=dt_timezone.utc
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
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(self.unpaid.cancelled)
        self.assertFalse(self.paid.cancelled)

    @patch('booking.management.commands.email_ticket_booking_warnings.timezone')
    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_only_cancel_with_payment_due_date_if_warning_sent(
            self, cancel_mock_tz, warn_mock_tz
    ):
        cancel_mock_tz.now.return_value = datetime(
            2015, 2, 11, 10, tzinfo=dt_timezone.utc
        )
        warn_mock_tz.now.return_value = datetime(
            2015, 2, 11, 10, tzinfo=dt_timezone.utc
        )
        self.assertFalse(self.unpaid.cancelled)
        self.unpaid.warning_sent = False
        self.unpaid.save()

        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEqual(len(mail.outbox), 0)
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

        self.assertEqual(len(mail.outbox), 3)
        warning_email = mail.outbox[0]
        cancel_email_to_user = mail.outbox[1]
        cancel_email_to_studio = mail.outbox[2]
        self.assertEqual(
            warning_email.subject,
            '{} Reminder: Ticket booking ref {} is not yet paid'.format(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, self.unpaid.booking_reference)
        )
        self.assertEqual(warning_email.to[0], self.unpaid.user.email)
        self.assertEqual(
            cancel_email_to_user.subject,
            '{} Ticket Booking ref {} cancelled'.format(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, self.unpaid.booking_reference)
        )
        self.assertEqual(cancel_email_to_user.to[0], self.unpaid.user.email)
        self.assertEqual(
            cancel_email_to_studio.subject,
            '{} Ticket Booking has been automatically cancelled'.format(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX)
        )
        self.assertEqual(cancel_email_to_studio.to[0], settings.DEFAULT_STUDIO_EMAIL)
        self.assertTrue(self.unpaid.cancelled)

    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_cancel_ticket_bookings_over_payment_time_allowed_without_warnings(
            self, mock_tz
    ):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 10, 0, tzinfo=dt_timezone.utc
        )
        self.ticketed_event.payment_due_date = None
        self.ticketed_event.payment_time_allowed = 8
        self.ticketed_event.save()

        self.unpaid.date_booked = datetime(
            2015, 2, 11, 3, 0, tzinfo=dt_timezone.utc
        )
        self.unpaid.warning_sent = False
        self.unpaid.save()
        # self.unpaid.date_booked is within 8 hrs, so not cancelled
        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(self.unpaid.cancelled)


        # set date booked to >8 hrs ago
        self.unpaid.date_booked = datetime(
            2015, 2, 11, 1, 59, tzinfo=dt_timezone.utc
        )
        self.unpaid.save()
        # self.unpaid.date_booked is within 4 hrs, so not cancelled
        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking and studio once for all
        # cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEqual(len(mail.outbox), 2)
        self.assertTrue(self.unpaid.cancelled)
        # even though warning has not been sent
        self.assertFalse(self.unpaid.warning_sent)

    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_dont_cancel_for_events_in_the_past(self, mock_tz):
        """
        test don't cancel or send emails for past events
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 10, tzinfo=dt_timezone.utc
        )
        self.assertFalse(self.unpaid.cancelled)
        self.assertFalse(self.paid.cancelled)

        # make date of event in the past
        self.ticketed_event.date = datetime(2015, 2, 9, tzinfo=dt_timezone.utc)
        self.ticketed_event.save()
        self.assertTrue(timezone.now() > self.ticketed_event.date)

        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking and studio once
        # for all cancelled bookings
        self.unpaid.refresh_from_db()
        self.paid.refresh_from_db()
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(self.unpaid.cancelled)
        self.assertFalse(self.paid.cancelled)

    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_dont_cancel_for_already_cancelled(self, mock_tz):
        """
        ignore already cancelled bookings
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 10, tzinfo=dt_timezone.utc
        )
        self.unpaid.cancelled = True
        self.unpaid.save()

        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking and studio once
        # for all cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(self.unpaid.cancelled)

    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_dont_cancel_for_cancelled_events(self, mock_tz):
        """
        ignore bookings for cancelled events
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 10, tzinfo=dt_timezone.utc
        )
        self.ticketed_event.cancelled = True
        self.ticketed_event.save()
        self.assertFalse(self.unpaid.cancelled)

        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking and studio once
        # for all cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(self.unpaid.cancelled)

    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_dont_cancel_bookings_in_cancellation_period_if_warning_not_sent(self, mock_tz):
        """
        Avoid immediately cancelling bookings made within the cancellation
        period - don't cancel unless warned at least 2 hrs ago
        """
        mock_tz.now.return_value = datetime(2015, 2, 11, 12, 0, tzinfo=dt_timezone.utc)

        # self.ticketed_event payment due date 2015/2/11 23:59

        unpaid_no_warning = baker.make(
            TicketBooking,
            ticketed_event=self.ticketed_event,
            paid=False,
            date_booked=datetime(2015, 2, 10, 5, 30, tzinfo=dt_timezone.utc),
            warning_sent=False
        )
        unpaid_warning_within_2_hrs = baker.make(
            TicketBooking,
            ticketed_event=self.ticketed_event,
            paid=False,
            date_booked=datetime(2015, 2, 10, 5, 30, tzinfo=dt_timezone.utc),
            warning_sent=True,
            date_warning_sent=datetime(2015, 2, 11, 10, 30, tzinfo=dt_timezone.utc),
        )
        unpaid_warning_more_than_2_hrs_ago = baker.make(
            TicketBooking,
            ticketed_event=self.ticketed_event,
            paid=False,
            date_booked=datetime(2015, 2, 10, 5, 30, tzinfo=dt_timezone.utc),
            warning_sent=True,
            date_warning_sent=datetime(2015, 2, 11, 9, 30, tzinfo=dt_timezone.utc),
        )

        self.assertFalse(unpaid_no_warning.cancelled)
        self.assertFalse(unpaid_warning_within_2_hrs.cancelled)
        self.assertFalse(unpaid_warning_more_than_2_hrs_ago.cancelled)

        management.call_command('cancel_unpaid_ticket_bookings')
        unpaid_no_warning.refresh_from_db()
        unpaid_warning_within_2_hrs.refresh_from_db()
        unpaid_warning_more_than_2_hrs_ago.refresh_from_db()
        self.assertFalse(unpaid_no_warning.cancelled)
        self.assertFalse(unpaid_warning_within_2_hrs.cancelled)
        self.assertTrue(unpaid_warning_more_than_2_hrs_ago.cancelled)

    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_dont_cancel_unpaid_bookings_with_checkout_in_past_5_mins(self, mock_tz):
        """
        test unpaid bookings are not cancelled if checkout in past 5 mins
        """
        # one min after payment due date
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 10, tzinfo=dt_timezone.utc
        )

        self.assertFalse(self.unpaid.cancelled)
        self.assertFalse(self.paid.cancelled)
        self.unpaid.checkout_time = datetime(2015, 2, 11, 9, 56, tzinfo=dt_timezone.utc)
        self.unpaid.save()
        management.call_command('cancel_unpaid_ticket_bookings')
        
        self.unpaid.refresh_from_db()
        self.paid.refresh_from_db()
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(self.unpaid.cancelled)
        self.assertFalse(self.paid.cancelled)

        # checkout more than 5 mins ago
        self.unpaid.checkout_time = datetime(2015, 2, 11, 9, 54, tzinfo=dt_timezone.utc)
        self.unpaid.save()
        management.call_command('cancel_unpaid_ticket_bookings')
        self.unpaid.refresh_from_db()
        self.paid.refresh_from_db()
        # emails to studio and user
        self.assertEqual(len(mail.outbox), 2)
        self.assertTrue(self.unpaid.cancelled)
        self.assertFalse(self.paid.cancelled)
        

    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_only_send_one_email_to_studio(self, mock_tz):
        """
        users are emailed per booking, studio just receives one summary
        email
        """
        mock_tz.now.return_value = datetime(2015, 2, 11, 10, tzinfo=dt_timezone.utc)
        for i in range(5):
            baker.make(
                TicketBooking, ticketed_event=self.ticketed_event,
                cancelled=False, paid=False,
                user__email="unpaid_user{}@test.com".format(i),
                date_booked= datetime(2015, 2, 9, tzinfo=dt_timezone.utc),
                warning_sent=True,
                date_warning_sent=datetime(2015, 2, 9, 2, tzinfo=dt_timezone.utc),
            )
        for booking in TicketBooking.objects.all():
            baker.make(Ticket, ticket_booking=booking)

        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking (6) (these 5 plus
        # self.unpaid) and studio once for all cancelled bookings
        self.unpaid.refresh_from_db()
        self.assertEqual(len(mail.outbox), 7)
        self.assertTrue(self.unpaid.cancelled)
        self.assertEqual(
            TicketBooking.objects.filter(cancelled=True).count(), 6
        )
        cancelled_booking_emails = [
            booking.user.email for booking
            in TicketBooking.objects.filter(cancelled=True)
        ]
        all_emails = cancelled_booking_emails + [settings.DEFAULT_STUDIO_EMAIL]

        self.assertEqual(
            sorted(all_emails),
            sorted([email.to[0] for email in mail.outbox])
        )

    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.send_mail')
    @patch('booking.management.commands.cancel_unpaid_ticket_bookings.timezone')
    def test_email_errors(self, mock_tz, mock_send):
        mock_send.side_effect = Exception('Error sending email')
        mock_tz.now.return_value = datetime(2015, 2, 11, 10, tzinfo=dt_timezone.utc)

        management.call_command('cancel_unpaid_ticket_bookings')
        # error emails are sent to user per cancelled booking (self.unpaid)
        # and studio
        self.unpaid.refresh_from_db()
        self.assertEqual(len(mail.outbox), 2)
        self.assertTrue(self.unpaid.cancelled)

        for email in mail.outbox:
            self.assertEqual(email.to, [settings.SUPPORT_EMAIL])

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
        mock_tz.now.return_value = datetime(2015, 2, 11, 10, tzinfo=dt_timezone.utc)
        for i in range(5):
            baker.make(
                TicketBooking, ticketed_event=self.ticketed_event,
                cancelled=False, paid=False,
                user__email="unpaid_user{}@test.com".format(i),
                date_booked= datetime(2015, 2, 9, tzinfo=dt_timezone.utc),
                warning_sent=True,
                date_warning_sent= datetime(2015, 2, 9, tzinfo=dt_timezone.utc),
            )
        for booking in TicketBooking.objects.all():
            baker.make(Ticket, ticket_booking=booking)

        management.call_command('cancel_unpaid_ticket_bookings')
        # emails are sent to user per cancelled booking (6) (these 5 plus
        # self.unpaid); none to studio
        self.assertEqual(len(mail.outbox), 6)
        cancelled_booking_emails = [
            booking.user.email for booking
            in TicketBooking.objects.filter(cancelled=True)
        ]
        self.assertEqual(
            cancelled_booking_emails, [email.to[0] for email in mail.outbox]
        )

    @patch('booking.management.commands.delete_unconfirmed_ticket_bookings.timezone')
    def test_delete_unconfirmed_ticket_bookings_after_1_hr(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 2, 11, 12, 0, tzinfo=dt_timezone.utc
        )
        unconfirmed_ticket_booking = baker.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            date_booked=datetime(2015, 2, 11, 10, 0, tzinfo=dt_timezone.utc),
            purchase_confirmed=False
        )
        unconfirmed_ticket_booking1 = baker.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            date_booked=datetime(2015, 2, 11, 11, 30, tzinfo=dt_timezone.utc),
            purchase_confirmed=False
        )
        for booking in TicketBooking.objects.all():
            baker.make(Ticket, ticket_booking=booking)

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
            2015, 2, 11, 12, 0, tzinfo=dt_timezone.utc
        )
        self.unpaid.paid = True
        self.unpaid.save()

        unconfirmed_ticket_booking = baker.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            date_booked=datetime(2015, 2, 11, 11, 30, tzinfo=dt_timezone.utc),
            purchase_confirmed=False
        )
        baker.make(Ticket, ticket_booking=unconfirmed_ticket_booking)

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


class BlockBookingsReportTests(PatchRequestMixin, TestCase):

    def setUp(self):
        """
        Users with active/inactive blocks
        Bookings for relevant classes not made with the active block but
        booked after it's start date
        Report unpaid/paid/paid with paypal
        Ignore free
        """
        super(BlockBookingsReportTests, self).setUp()
        self.user1 = baker.make_recipe('booking.user')
        self.user2 = baker.make_recipe('booking.user')

        self.event_type = baker.make_recipe('booking.event_type_PC')

        self.user1_active_block = baker.make_recipe(
            'booking.block_5', user=self.user1,
            start_date=timezone.now() - timedelta(10),
            block_type__event_type=self.event_type,
            paid=True
        )
        self.user2_active_block = baker.make_recipe(
            'booking.block_5', user=self.user2,
            start_date=timezone.now() - timedelta(10),
            block_type__event_type=self.event_type, paid=True
        )

        user1_bookings_on_block = baker.make_recipe(
            'booking.booking',
            user=self.user1,
            event__event_type=self.event_type,
            block=self.user1_active_block,
            date_booked=timezone.now() - timedelta(8),
            _quantity=2
        )
        self.user1_booking_not_on_block = baker.make_recipe(
            'booking.booking',
            user=self.user1,
            event__event_type=self.event_type,
            date_booked=timezone.now() - timedelta(8)
        )
        user1_booking_old = baker.make_recipe(
            'booking.booking',
            user=self.user1,
            event__event_type=self.event_type,
            date_booked=timezone.now() - timedelta(12)
        )
        user1_booking_free = baker.make_recipe(
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
        super(BlockBookingsReportTests, self).tearDown()

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
        paid_booking = baker.make_recipe(
            'booking.booking',
            user=self.user1,
            event__event_type=self.event_type,
            date_booked=timezone.now() - timedelta(8),
            paid=True, payment_confirmed=True
        )
        paid_by_pp_booking = baker.make_recipe(
            'booking.booking',
            user=self.user1,
            event__event_type=self.event_type,
            date_booked=timezone.now() - timedelta(8),
            paid=True, payment_confirmed=True
        )
        baker.make(
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
        pc_evtype = baker.make(
            EventType, event_type="CL", subtype="Pole level class"
        )
        baker.make_recipe('booking.blocktype5', event_type=pc_evtype)
        baker.make_recipe('booking.blocktype10', event_type=pc_evtype)

        baker.make_recipe(
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
        baker.make_recipe(
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
        baker.make_recipe(
            'booking.blocktype5', identifier='test', _quantity=5
        )
        management.call_command(
            'activate_blocktypes', 'test', 'off'
        )
        self.assertEqual(
            BlockType.objects.filter(active=True).count(), 0
        )

    def test_activate_blocktypes_only_activates_by_identifier(self):
        baker.make_recipe(
            'booking.blocktype5', active=False, identifier='test', _quantity=5
        )
        baker.make_recipe(
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
        baker.make_recipe(
            'booking.blocktype5', active=False, identifier='test', _quantity=5
        )
        baker.make_recipe(
            'booking.blocktype5', active=False, identifier='test1', _quantity=5
        )
        inactive_blocktypes = baker.make_recipe(
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
        baker.make_recipe(
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
        baker.make_recipe(
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
        baker.make_recipe(
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
        baker.make_recipe('booking.blocktype5', active=False, identifier='test')

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
        baker.make_recipe('booking.blocktype5', active=False, identifier='test')

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

        baker.make(
           Event, date=timezone.now() + timedelta(1),
           cost=7.50, booking_open=False,
           payment_open=False, event_type=self.pc_ev_type,
           _quantity=5
        )
        baker.make(
            Event, date=timezone.now() + timedelta(1),
            cost=7.50, booking_open=False,
            payment_open=False, event_type=self.oc_ev_type,
            _quantity=5
        )
        baker.make(
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


class CreateFreeMonthlyBlocksTests(PatchRequestMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.event_type = baker.make(
            EventType, event_type='CL', subtype='Pole level class'
        )

    def test_no_groups_and_blocktypes_created(self):
        assert Block.objects.exists() is False
        assert Group.objects.exists() is False
        assert BlockType.objects.exists() is False

        management.call_command('create_free_monthly_blocks')
        assert Block.objects.exists() is False
        assert Group.objects.exists() is False
        assert BlockType.objects.exists() is False

        # One email
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.subject == f'{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Free monthly blocks creation'
        assert email.body == "No free monthly groups found"

    def test_no_users_in_group(self):
        Group.objects.create(name='free_5monthly_blocks')
        Group.objects.create(name='free_7monthly_blocks')
        management.call_command('create_free_monthly_blocks')

        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.subject == f'{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Free monthly blocks creation'
        assert email.body == "Group: free_5monthly_blocks\n" \
                             "No users in this group\n" \
                             "=====================\n\n" \
                             "Group: free_7monthly_blocks\n" \
                             "No users in this group\n" \
                             "=====================\n\n"
        assert Block.objects.exists() is False

    @patch("booking.management.commands.create_free_monthly_blocks.timezone.now")
    def test_create_free_blocks(self, mock_now):
        mock_now.return_value = datetime(2020, 6, 7, 10, 30, tzinfo=dt_timezone.utc)
        assert Block.objects.exists() is False

        group5 = Group.objects.create(name='free_5monthly_blocks')
        group7 = Group.objects.create(name='free_7monthly_blocks')
        user1 = baker.make(User, first_name='Test', last_name='User1')
        user2 = baker.make(User, first_name='Test', last_name='User2')
        user3 = baker.make(User, first_name='Test', last_name='User3')

        user1.groups.add(group5)
        user2.groups.add(group7)

        management.call_command('create_free_monthly_blocks')
        assert Block.objects.count() == 2

        user1block = Block.objects.get(user=user1)
        user2block = Block.objects.get(user=user2)
        assert user1block.block_type.identifier == 'Free - 5 classes'
        assert user1block.block_type.size == 5
        assert user1block.block_type.active is False
        assert user2block.block_type.identifier == 'Free - 7 classes'
        assert user2block.block_type.size == 7
        assert user2block.block_type.active is False

        # start/end set to 1st and last of the month
        for block in [user1block, user2block]:
            assert block.start_date.date() == date(2020, 6, 1)
            assert block.expiry_date.date() == date(2020, 6, 30)

        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.subject == f'{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Free monthly blocks creation'
        assert email.body == "Group: free_5monthly_blocks\n" \
                             "Free class blocks created for Test User1\n" \
                             "=====================\n\n" \
                             "Group: free_7monthly_blocks\n" \
                             "Free class blocks created for Test User2\n" \
                             "=====================\n\n"

    def test_dont_create_duplicate_free_blocks(self):
        assert Block.objects.exists() is False
        group5 = Group.objects.create(name='free_5monthly_blocks')
        group7 = Group.objects.create(name='free_7monthly_blocks')
        user1 = baker.make(User, first_name='Test', last_name='User1')
        user2 = baker.make(User, first_name='Test', last_name='User2')
        user3 = baker.make(User, first_name='Test', last_name='User3')
        user1.groups.add(group5)
        user2.groups.add(group7)

        management.call_command('create_free_monthly_blocks')
        assert Block.objects.count() == 2

        user1block = Block.objects.get(user=user1)
        user2block = Block.objects.get(user=user2)

        assert user1block.block_type.identifier == 'Free - 5 classes'
        assert user2block.block_type.identifier == 'Free - 7 classes'

        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.subject == f'{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Free monthly blocks creation'
        assert email.body == "Group: free_5monthly_blocks\n" \
                             "Free class blocks created for Test User1\n" \
                             "=====================\n\n" \
                             "Group: free_7monthly_blocks\n" \
                             "Free class blocks created for Test User2\n" \
                             "=====================\n\n"


        # call again; no new blocks created
        management.call_command('create_free_monthly_blocks')
        assert Block.objects.count() == 2

        blockids = Block.objects.all().values_list('id', flat=True)
        self.assertCountEqual(blockids, [user1block.id, user2block.id])

        user1block = Block.objects.get(user=user1)
        user2block = Block.objects.get(user=user2)
        assert user1block.block_type.identifier == 'Free - 5 classes'
        assert user2block.block_type.identifier == 'Free - 7 classes'

        assert len(mail.outbox) == 2
        email = mail.outbox[1]
        assert email.subject == f'{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Free monthly blocks creation'
        assert email.body == "Group: free_5monthly_blocks\n" \
                             "Free block for this month already exists for Test User1\n" \
                             "=====================\n\n" \
                             "Group: free_7monthly_blocks\n" \
                             "Free block for this month already exists for Test User2\n" \
                             "=====================\n\n"

    def test_blocks_created_with_current_month_start_date(self):
        """
        Check that we can create blocks on 1st of the month, and they will have
        expired on 1st of the next month
        """
        group = Group.objects.create(name='free_5monthly_blocks')
        user1 = baker.make(User, first_name='Test', last_name='User1')
        user2 = baker.make(User, first_name='Test', last_name='User2')
        user3 = baker.make(User, first_name='Test', last_name='User3')

        for user in [user1, user2, user3]:
            user.groups.add(group)

        # make blocks on 1st Jan
        with patch(
                'booking.management.commands.create_free_monthly_blocks'
                '.timezone.now',
                return_value=datetime(2016, 1, 15, tzinfo=dt_timezone.utc)
            ):
            management.call_command('create_free_monthly_blocks')

        assert Block.objects.count() == 3
        for block in Block.objects.all():
            assert block.start_date.date() == date(2016, 1, 1)

        # make blocks on 1st Feb
        with patch(
                'booking.management.commands.create_free_monthly_blocks'
                '.timezone.now',
                return_value=datetime(2016, 2, 1, tzinfo=dt_timezone.utc)
            ):
            # blocks are not full, and are paid, so active unless expired
            assert [bl for bl in Block.objects.all() if bl.full] == []
            assert Block.objects.filter(paid=True).count() == 3
            assert [bl for bl in Block.objects.all() if bl.active_block()] == []
            management.call_command('create_free_monthly_blocks')
        # 3 new blocks created
        assert Block.objects.count() == 6


class TestDeactivateRegularStudents(TestCase):

    @classmethod
    def setUpTestData(cls):
        event_type = baker.make_recipe("booking.event_type_PC")
        cls.pole_class = baker.make(Event, event_type=event_type)
        cls.pole_class1 = baker.make(Event, event_type=event_type)
        cls.pole_practice_event_type = baker.make_recipe("booking.event_type_PP")
        cls.pole_practice = baker.make(Event, event_type=cls.pole_practice_event_type)

    @patch('booking.management.commands.deactivate_regular_students.timezone')
    def test_regular_students_with_class_bookings_more_than_8_months_ago_deactivated(self, mocktz):
        mocktz.now.return_value = datetime(2018, 10, 3, tzinfo=dt_timezone.utc)
        user = baker.make(User)
        self.pole_practice_event_type.add_permission_to_book(user)
        baker.make(
            Booking, user=user, event=self.pole_class,
            date_booked=datetime(2018, 2, 1, tzinfo=dt_timezone.utc)
        )
        management.call_command("deactivate_regular_students")
        assert not self.pole_practice_event_type.has_permission_to_book(user)

    @patch('booking.management.commands.deactivate_regular_students.timezone')
    def test_regular_students_with_class_bookings_in_past_8_months_not_deactivated(self, mocktz):
        mocktz.now.return_value = datetime(2018, 10, 3, tzinfo=dt_timezone.utc)
        user = baker.make(User)
        self.pole_practice_event_type.add_permission_to_book(user)
        # one booking longer ago than 8 months
        baker.make(
            Booking, user=user, event=self.pole_class,
            date_booked=datetime(2018, 2, 1, tzinfo=dt_timezone.utc)
        )
        baker.make(
            Booking, user=user, event=self.pole_class1,
            date_booked=datetime(2018, 4, 1, tzinfo=dt_timezone.utc)
        )
        management.call_command("deactivate_regular_students")
        assert self.pole_practice_event_type.has_permission_to_book(user)

    @patch('booking.management.commands.deactivate_regular_students.timezone')
    def test_regular_students_with_no_class_bookings_deactivated(self, mocktz):
        mocktz.now.return_value = datetime(2018, 10, 3, tzinfo=dt_timezone.utc)
        user = baker.make(User)
        self.pole_practice_event_type.add_permission_to_book(user)
        management.call_command("deactivate_regular_students")
        user.refresh_from_db()
        assert not self.pole_practice_event_type.has_permission_to_book(user)

    @override_settings(REGULAR_STUDENT_WHITELIST_IDS=[2, 3, 4])
    @patch('booking.management.commands.deactivate_regular_students.timezone')
    def test_regular_students_whitelist(self, mocktz):
        mocktz.now.return_value = datetime(2018, 10, 3, tzinfo=dt_timezone.utc)
        whitelist_user = baker.make(User, email='foo@test.com', id=3)
        normal_user = baker.make(User, email='bar@test.com', id=9)
        for user in [whitelist_user, normal_user]:
            self.pole_practice_event_type.add_permission_to_book(user)
        management.call_command("deactivate_regular_students")
        assert self.pole_practice_event_type.has_permission_to_book(whitelist_user)
        assert not self.pole_practice_event_type.has_permission_to_book(normal_user)

    @patch('booking.management.commands.deactivate_regular_students.timezone')
    def test_do_not_deactivate_superuser(self, mocktz):
        mocktz.now.return_value = datetime(2018, 10, 3, tzinfo=dt_timezone.utc)
        super_user = baker.make(User, email='super@test.com', is_superuser=True)
        staff_user = baker.make(User, email='staff@test.com', is_staff=True)
        normal_user = baker.make(User, email='normal@test.com')
        for user in [super_user, staff_user, normal_user]:
            self.pole_practice_event_type.add_permission_to_book(user)
        management.call_command("deactivate_regular_students")
        assert self.pole_practice_event_type.has_permission_to_book(super_user)
        assert self.pole_practice_event_type.has_permission_to_book(staff_user)
        assert not self.pole_practice_event_type.has_permission_to_book(normal_user)


class TestFindNoShows(TestCase):

    def test_find_no_shows_defaults(self):
        now = timezone.now()
        user = baker.make(User)
        user1 = baker.make(User)
        baker.make(
            Booking, user=user, event__date=now - timedelta(3),
            status="OPEN", no_show=True, instructor_confirmed_no_show=True, paid=True
        )
        management.call_command("find_no_shows")
        assert len(mail.outbox) == 1
        assert "No repeated no-shows found" in mail.outbox[0].body

        # not no-shows
        baker.make(
            Booking, user=user1, event__date=now - timedelta(3),
            status="OPEN", no_show=False, paid=True, _quantity=4,
        )
        # no-shows, not confirmed by instructor (late cancellations)
        baker.make(
            Booking, user=user1, event__date=now - timedelta(4),
            status="OPEN", no_show=True, instructor_confirmed_no_show=False,
            paid=True, _quantity=4
        )
        # no-shows, confirmed by instructor
        baker.make(
            Booking, user=user, event__date=now - timedelta(4),
            status="OPEN", no_show=True, instructor_confirmed_no_show=True,
            paid=True, _quantity=2
        )
        management.call_command("find_no_shows")
        assert len(mail.outbox) == 2
        assert f"{3}: {user.first_name} {user.last_name} - (id {user.id})" in mail.outbox[1].body
        assert f"{user1.first_name} {user1.last_name} - (id {user1.id})" not in mail.outbox[1].body
