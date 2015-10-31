'''
Email warnings for unpaid bookings 24 hrs prior to payment_due_date

ticketed_event.cancelled = False
ticketed_event is not in the past
ticketed_event.advance_payment_required
ticketed_event.ticket_cost > 0

ticket_booking.cancelled = False
ticket_booking.paid = False
ticket_booking.warning_sent = False

ticketed_event.payment_due_date < timezone.now() + 24 hrs

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
from booking.models import TicketedEvent, TicketBooking
from activitylog.models import ActivityLog


class Command(BaseCommand):
    help = 'email warnings for unpaid ticket bookings'

    def handle(self, *args, **options):
        # send warning 2 days prior to cancellation period or payment due
        # date
        warning_bookings = get_bookings(24)
        send_warning_email(self, warning_bookings)


def get_bookings(num_hrs):

    # get relevant ticketed_events
    ticketed_events = TicketedEvent.objects.filter(
        date__gte=timezone.now(),
        cancelled=False,
        ticket_cost__gt=0,
        advance_payment_required=True,
    )

    events_payment_due_soon = [
        event for event in ticketed_events if
        event.payment_due_date and
        (event.payment_due_date - timedelta(hours=num_hrs)) <= timezone.now()
    ]

    return TicketBooking.objects.filter(
        ticketed_event__in=events_payment_due_soon,
        cancelled=False,
        paid=False,
        warning_sent=False,
        date_booked__lte=timezone.now() - timedelta(hours=2)
        )


def send_warning_email(self, upcoming_bookings):
    for ticket_booking in upcoming_bookings:
        uk_tz = pytz.timezone('Europe/London')
        due_datetime = ticket_booking.ticketed_event.payment_due_date
        due_datetime = due_datetime.astimezone(uk_tz)

        ctx = Context({
              'ticket_booking': ticket_booking,
              'event': ticket_booking.ticketed_event,
              'due_datetime': due_datetime.strftime('%A %d %B %H:%M'),
        })

        send_mail('{} Reminder: Ticket booking ref {} is not yet paid'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
            ticket_booking.booking_reference
        ),
            get_template('booking/email/ticket_booking_warning.txt').render(ctx),
            settings.DEFAULT_FROM_EMAIL,
            [ticket_booking.user.email],
            html_message=get_template(
                'booking/email/ticket_booking_warning.html'
                ).render(ctx),
            fail_silently=False)
        ticket_booking.warning_sent = True
        ticket_booking.save()

        ActivityLog.objects.create(
            log='Warning email sent for booking ref {}, '
            'for event {}, user {}'.format(
                ticket_booking.booking_reference,
                ticket_booking.ticketed_event, ticket_booking.user.username
            )
        )

    if upcoming_bookings:
        self.stdout.write(
            'Warning emails sent for booking refs {}'.format(
                ', '.join(
                    [str(ticket_booking.booking_reference)
                     for ticket_booking in upcoming_bookings]
                )
            )
        )

    else:
        self.stdout.write('No warnings to send')
        ActivityLog.objects.create(
            log='email_ticket_booking_warnings job run; '
                'no unpaid booking warnings to send'
        )
