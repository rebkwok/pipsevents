'''
Email warnings for unpaid bookings 48 hrs prior to payment_due_date or
cancellation_period
Check for bookings where:
event.payment_open == True
booking.status == OPEN
booking.payment_confirmed = False

Add warning_sent flags to booking model so
we don't keep sending
'''
import pytz
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import get_template
from django.template import Context
from django.core.management.base import BaseCommand
from django.core import management

from booking.templatetags.bookingtags import format_cancellation
from booking.models import Booking, Event
from activitylog.models import ActivityLog


class Command(BaseCommand):
    help = 'email warnings for unpaid bookings'

    def handle(self, *args, **options):
        # send warning 2 days prior to cancellation period or payment due
        # date
        warning_bookings = get_bookings(48)
        send_warning_email(self, warning_bookings)


def get_bookings(num_hrs):
    events_cancellation_period_soon = [
        event for event in Event.objects.all() if
        event.date >= timezone.now() and
        (event.date - timedelta(hours=(event.cancellation_period + num_hrs)))
        <= timezone.now()
    ]

    events_with_payment_due_dates = [
        event for event in Event.objects.all() if event.payment_due_date]
    events_payment_due_soon = [
        event for event in events_with_payment_due_dates if
        event.date >= timezone.now() and
        (event.payment_due_date - timedelta(hours=num_hrs)) <= timezone.now()
    ]
    events = list(
        set(events_payment_due_soon) | set(events_cancellation_period_soon)
        )

    return Booking.objects.filter(
        event__in=events,
        status='OPEN',
        event__cost__gt=0,
        event__payment_open=True,
        payment_confirmed=False,
        warning_sent=False,
        date_booked__lte=timezone.now() - timedelta(hours=2)
        )


def send_warning_email(self, upcoming_bookings):
    for booking in upcoming_bookings:
        uk_tz = pytz.timezone('Europe/London')
        due_datetime = booking.event.date - timedelta(hours=(booking.event.cancellation_period))
        if booking.event.payment_due_date and booking.event.payment_due_date < due_datetime:
            due_datetime = booking.event.payment_due_date
        due_datetime = due_datetime.astimezone(uk_tz)

        ctx = Context({
              'booking': booking,
              'event': booking.event,
              'date': booking.event.date.strftime('%A %d %B'),
              'time': booking.event.date.strftime('%H:%M'),
              'ev_type': 'event' if
              booking.event.event_type.event_type == 'EV' else 'class',
              'cancellation_period': format_cancellation(
                    booking.event.cancellation_period
                    ),
              'advance_payment_required':
              booking.event.advance_payment_required,
              'payment_due_date': booking.event.payment_due_date.strftime(
                    '%A %d %B'
                    ) if booking.event.payment_due_date else None,
              'due_datetime': due_datetime.strftime('%A %d %B %H:%M'),
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
        booking.warning_sent = True
        booking.save()

        ActivityLog.objects.create(
            log='Warning email sent for booking id {}, '
            'for event {}, user {}'.format(
                booking.id, booking.event, booking.user.username
            )
        )

    if upcoming_bookings:
        self.stdout.write(
            'Warning emails sent for booking ids {}'.format(
                ', '.join([str(booking.id) for booking in upcoming_bookings])
            )
        )

    else:
        self.stdout.write('No warnings to send')
        ActivityLog.objects.create(
            log='email_warnings job run; no unpaid booking warnings to send'
        )
