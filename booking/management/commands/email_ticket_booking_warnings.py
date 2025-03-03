'''
Email warnings for unpaid bookings booked > 2 hrs ago

BUT excluding bookings with a checkout_time in the past 5 mins
(checkout_time is set when user clicks button to pay with stripe)
'''
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import get_template
from django.core.management.base import BaseCommand

from booking.models import TicketedEvent, TicketBooking
from activitylog.models import ActivityLog
from common.management import write_command_name


class Command(BaseCommand):
    help = 'email warnings for unpaid ticket bookings'

    def handle(self, *args, **options):
        write_command_name(self, __file__)
        # only send warnings between 7am and 10pm
        warnings_start_time = 7
        warnings_end_time = 22
        now = timezone.now()
        if warnings_start_time <= now.hour < warnings_end_time:
            warning_bookings = get_bookings()
            send_warning_email(self, warning_bookings)
        else:
            self.stdout.write(f"Outside of valid auto-cancel time (09:00 - 22:00)")


def get_bookings():
    # get relevant ticketed_events
    ticketed_event_ids = TicketedEvent.objects.filter(
        date__gte=timezone.now(),
        cancelled=False,
        ticket_cost__gt=0,
        advance_payment_required=True,
        payment_open=True,
    ).values_list("id", flat=True)

    checkout_cutoff = timezone.now() - timedelta(seconds=5*60)
    return TicketBooking.objects.filter(
        ticketed_event__in=ticketed_event_ids,
        cancelled=False,
        paid=False,
        warning_sent=False,
        date_booked__lte=timezone.now() - timedelta(hours=2)
        ).exclude(checkout_time__gte=checkout_cutoff)


def send_warning_email(self, upcoming_bookings):
    for ticket_booking in upcoming_bookings:
        ctx = {
              'ticket_booking': ticket_booking,
              'event': ticket_booking.ticketed_event,
        }

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

        ActivityLog.objects.create(
            log='Warning email sent for booking ref {}, '
            'for event {}, user {}'.format(
                ticket_booking.booking_reference,
                ticket_booking.ticketed_event, ticket_booking.user.username
            )
        )

    # Do this before updaing the upcoming bookings otherwise the update makes it None
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

    upcoming_bookings.update(warning_sent=True)
