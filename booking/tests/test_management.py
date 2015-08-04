from django.test import TestCase
from django.conf import settings
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
    def test_dont_cancel_bookings_created_within_past_4_hours(self, mock_tz):
        """
        Avoid immediately cancelling bookings made within the cancellation
        period to allow time for users to make payments
        """
        mock_tz.now.return_value = datetime(
            2015, 2, 10, 18, 0, tzinfo=timezone.utc
        )
        self.unpaid.date_booked =  datetime(
            2015, 2, 10, 16, 0, tzinfo=timezone.utc
        )
        self.unpaid.save()
        self.assertEquals(
            self.unpaid.status, 'OPEN', self.unpaid.status
        )
        management.call_command('cancel_unpaid_bookings')
        # emails are sent to user per cancelled booking and studio once
        # for all cancelled bookings
        unpaid_booking = Booking.objects.get(id=self.unpaid.id)
        self.assertEquals(len(mail.outbox), 0)
        self.assertEquals(
            unpaid_booking.status, 'OPEN', unpaid_booking.status
        )

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
            all_emails, [email.to for email in mail.outbox]
        )

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
