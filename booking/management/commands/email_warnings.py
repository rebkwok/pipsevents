'''
Email warnings for unpaid bookings if booked/rebooked > 2hrs ago

Check for bookings where:
booking.status == OPEN
booking.payment_confirmed = False
booking.paid = False

Add warning_sent flags to booking model so
we don't keep sending
'''
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import get_template
from django.core.management.base import BaseCommand
from django.db.models import Q

from booking.models import Booking, Event
from activitylog.models import ActivityLog


class Command(BaseCommand):
    help = 'email warnings for unpaid bookings'

    def handle(self, *args, **options):
        # only send warnings between 7am and 10pm
        warnings_start_time = 7
        warnings_end_time = 22
        now = timezone.now()

        if warnings_start_time <= now.hour < warnings_end_time:
            warning_bookings = get_bookings()
            send_warning_email(self, warning_bookings)


def get_bookings():
    # Find ids of future events with payment required
    # Limit to only those with payment open - ones with payment closed are the ones that require
    # bank transfer and will have longer payment due date/ time allowed
    event_ids = Event.objects.filter(
        date__gte=timezone.now(), cost__gt=0, advance_payment_required=True, payment_open=True
    ).values_list("id", flat=True)

    rebooked = Q(date_rebooked__isnull=False)
    not_rebooked = Q(date_rebooked__isnull=True)
    rebooked_more_than_2hrs_ago= Q(date_rebooked__lte=timezone.now() - timedelta(hours=2))
    booked_more_than_2hrs_ago = Q(date_booked__lte=timezone.now() - timedelta(hours=2))

    return Booking.objects.filter(
        (rebooked & rebooked_more_than_2hrs_ago) | (not_rebooked & booked_more_than_2hrs_ago ),
        event_id__in=event_ids,
        status='OPEN',
        paid=False,
        payment_confirmed=False,
        warning_sent=False,
        )


def send_warning_email(self, upcoming_bookings):
    for booking in upcoming_bookings:
        ctx = {
              'booking': booking,
              'event': booking.event,
              'date': booking.event.date.strftime('%A %d %B'),
              'time': booking.event.date.strftime('%H:%M'),
              'ev_type': 'event' if
              booking.event.event_type.event_type == 'EV' else 'class',
        }

        send_mail('{} Reminder: {}'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event.name),
            get_template('booking/email/booking_warning.txt').render(ctx),
            settings.DEFAULT_FROM_EMAIL,
            [booking.user.email],
            html_message=get_template(
                'booking/email/booking_warning.html'
                ).render(ctx),
            fail_silently=False)

        ActivityLog.objects.create(
            log='Warning email sent for booking id {}, '
            'for event {}, user {}'.format(
                booking.id, booking.event, booking.user.username
            )
        )
    # Update the warning_sent flag on all selected bookings
    upcoming_bookings.update(warning_sent=True)

    if upcoming_bookings:
        self.stdout.write(
            'Warning emails sent for booking ids {}'.format(
                ', '.join([str(booking.id) for booking in upcoming_bookings])
            )
        )

    else:
        self.stdout.write('No warnings to send')
