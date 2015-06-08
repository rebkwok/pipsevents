#TODO
'''
Email warnings for unpaid bookings 2 days prior to payment_due_date or cancellation_period
Check for bookings where:
event.payment_open == True
booking.status == OPEN
booking.payment_confirmed = False

event.date - event.payment_due_date is less than a certain amount
OR
event.date - cancellation_period is less than a certain amount

Add first_warning_sent and second_warning_sent flags to booking model so
we don't keep sending
'''
from datetime import timedelta
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import get_template
from django.template import Context
from django.core.management.base import BaseCommand
from django.core import management

from booking.templatetags.bookingtags import format_cancellation


class Command(BaseCommand):
    help = 'email warnings for unpaid bookings'

    def handle(self, *args, **options):
        # send first warning 2 days prior to cancellation period or payment due
        # date, second warning 1 day prior
        first_warning_bookings = get_bookings(
            2, first_warning_sent=False, second_warning_sent=False
            )
        second_warning_bookings = get_bookings(
            1, first_warning_sent=True, second_warning_sent=False
            )

        for booking in first_warning_bookings:
            send_warning_email(first_warning_bookings)
            booking.first_warning_sent = True
        self.stdout.write(
            'First warning emails sent for booking ids {}'.format(
            ', '.join([booking.id for booking in first_warning_bookings])
            )
        )

        for booking in second_warning_bookings:
            send_warning_email(second_warning_bookings)
            booking.first_warning_sent = True
            booking.second_warning_sent = True
        self.stdout.write(
            'Second warning emails sent for booking ids {}'.format(
            ', '.join([booking.id for booking in second_warning_bookings])
            )
        )


def get_bookings(num_days):
    events_payment_due_soon = [
        event for event in Events.objects.filter(
            date__gte(timezone.now() - timedelta(
                event.cancellation_period + num_days
                )
            )
        ]
    events_cancellation_period_soon = [
        event for event in Events.objects.all() if event.payment_due_date >= timezone.now() - timedelta(num_days)
        ]
    events = list(
        set(events_payment_due_soon) | set(events_cancellation_period_soon)
        )

    upcoming_bookings = Booking.objects.filter(
        event__in=events,
        status='OPEN',
        event__payment_open=True,
        payment_confirmed=False,
        first_warning_sent=first_warning_sent,
        second_warning_sent=second_warning_sent
        )


def send_warning_email(upcoming_bookings):
    for booking in upcoming_bookings:
        ctx = Context({
              'host': host,
              'booking': booking,
              'event': booking.event,
              'date': booking.event.date.strftime('%A %d %B'),
              'time': booking.event.date.strftime('%I:%M %p'),
              'ev_type': 'event' if
              booking.event.event_type.event_type == 'EV' else 'class',
              'cancellation_period': format_cancellation(
                    booking.event.cancellation_period
                    ),
              'payment_due_date': booking.event.payment_due_date.strftime('%A %d %B') if booking.payment_due_date else None,

        })
        send_mail('{} Reminder: {}'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event.name),
            get_template('booking/email/booking_warning.txt').render(ctx),
            settings.DEFAULT_FROM_EMAIL,
            [booking.user.email],
            html_message=get_template(
                'booking/email/booking_warning.html'
                ).render(ctx),
            fail_silently=False)
        booking.reminder_sent = True
