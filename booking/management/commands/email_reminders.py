'''
Email reminders for upcoming events
Check for events with date within:
2 days before cancellation_period ends?
Email all users on event.bookings where booking.status == 'OPEN'
Add reminder_sent flag to booking model so we don't keep sending
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
        events = [
            event for event in Events.objects.filter(
                date__gte(timezone.now() - timedelta(event.cancellation_period + 2)
                )
            ]

        upcoming_bookings = Booking.objects.filter(
            event__in=events,
            status='OPEN',
            reminder_sent=False
            )

        for booking in upcoming_bookings:
            ctx = Context({
                  'host': host,
                  'booking': booking,
                  'event': booking.event,
                  'date': booking.event.date.strftime('%A %d %B'),
                  'time': booking.event.date.strftime('%I:%M %p'),
                  'paid': booking.paid,
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
            if not booking.payment_confirmed:
                # avoid sending the payment warning in this reminder and the warning
                # email
                first_warning_sent = True

        self.stdout.write(
            'Reminder emails sent for booking ids {}'.format(
            ', '.join([booking.id for booking in upcoming_bookings])
            )
        )
