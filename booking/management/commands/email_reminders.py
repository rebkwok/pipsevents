'''
Email reminders for upcoming events
Check for events with date within:
24 hrs before cancellation_period ends
Email all users on event.bookings where booking.status == 'OPEN'
Add reminder_sent flag to booking model so we don't keep sending
'''
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
    help = 'email reminders for upcoming bookings'

    def handle(self, *args, **options):
        events = [
            event for event in Event.objects.all() if
            event.date >= timezone.now() and
            (event.date - timedelta(hours=(event.cancellation_period + 24)))
            <= timezone.now()
        ]

        upcoming_bookings = Booking.objects.filter(
            event__in=events,
            status='OPEN',
            reminder_sent=False
            )

        for booking in upcoming_bookings:
            ctx = Context({
                  'booking': booking,
                  'event': booking.event,
                  'date': booking.event.date.strftime('%A %d %B'),
                  'time': booking.event.date.strftime('%I:%M %p'),
                  'paid': booking.paid,
                  'cost': booking.event.cost,
                  'payment_confirmed': booking.payment_confirmed,
                  'ev_type': 'event' if
                  booking.event.event_type.event_type == 'EV' else 'class',
                  'cancellation_period': format_cancellation(
                        booking.event.cancellation_period
                        )
            })
            send_mail('{} Reminder: {}'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event.name),
                get_template('booking/email/booking_reminder.txt').render(ctx),
                settings.DEFAULT_FROM_EMAIL,
                [booking.user.email],
                html_message=get_template(
                    'booking/email/booking_reminder.html'
                    ).render(ctx),
                fail_silently=False)
            booking.reminder_sent = True
            booking.save()

            ActivityLog.objects.create(
                log='Reminder email sent for booking id {} for event {}, '
                'user {}'.format(
                    booking.id, booking.event, booking.user.username
                )
            )

        if upcoming_bookings:
            self.stdout.write(
                'Reminder emails sent for booking ids {}'.format(
                    ', '.join([str(booking.id) for booking in upcoming_bookings])
                )
            )

        else:
            self.stdout.write('No reminders to send')
            ActivityLog.objects.create(
                log='email_reminders job run; no reminders to send'
            )
