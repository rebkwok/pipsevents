from django.test import TestCase
from django.core import management
from django.core import mail
from django.db.models import Q
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import datetime, timedelta
from allauth.socialaccount.models import SocialApp
from mock import patch
from model_mommy import mommy

from booking.models import Event, Booking, EventType, BlockType
from booking.utils import create_classes
from timetable.models import Session


class ManagementCommandsTests(TestCase):

    def test_setup_fb(self):
        self.assertEquals(SocialApp.objects.all().count(), 0)
        management.call_command('setup_fb')
        self.assertEquals(SocialApp.objects.all().count(), 1)

    def test_load_users(self):
        self.assertEquals(User.objects.all().count(), 0)
        management.call_command('load_users')
        self.assertEquals(User.objects.all().count(), 6)

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
        self.assertEquals(EventType.objects.all().count(), 7)
        self.assertEquals(BlockType.objects.all().count(), 4)

    def test_create_events_and_blocktypes_twice(self):
        """
        test that create_events_and_blocktypes does not create duplicates
        """
        self.assertEquals(EventType.objects.all().count(), 0)
        self.assertEquals(BlockType.objects.all().count(), 0)

        management.call_command('create_event_and_blocktypes')
        self.assertEquals(EventType.objects.all().count(), 7)
        self.assertEquals(BlockType.objects.all().count(), 4)

        management.call_command('create_event_and_blocktypes')
        self.assertEquals(EventType.objects.all().count(), 7)
        self.assertEquals(BlockType.objects.all().count(), 4)


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
            payment_confirmed=False, _quantity=5
            )
        mommy.make_recipe(
            'booking.booking', event=event1, paid=False,
            payment_confirmed=False, _quantity=5
            )

        management.call_command('email_warnings')
        self.assertEquals(len(mail.outbox), 5)

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
            payment_confirmed=False, _quantity=5
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
            payment_confirmed=False, _quantity=3
            )
        mommy.make_recipe(
            'booking.booking', event=event, paid=True,
            payment_confirmed=True, _quantity=3
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
            payment_confirmed=False, status='OPEN', _quantity=3
            )
        mommy.make_recipe(
            'booking.booking', event=event, paid=False,
            payment_confirmed=False, status='CANCELLED', _quantity=3
            )
        management.call_command('email_warnings')
        self.assertEquals(len(mail.outbox), 3)
        for booking in Booking.objects.filter(status='OPEN'):
            self.assertTrue(booking.warning_sent)
        for booking in Booking.objects.filter(status='CANCELLED'):
            self.assertFalse(booking.warning_sent)


class CancelUnpaidBookingsTests(TestCase):
    pass
