'''
Check for unpaid ticket bookings and cancel where:
ticketed_event.cancelled = False
ticketed event is not in the past
ticketed_event.advance_payment_required
ticketed_event.ticket_cost > 0

ticket_booking.cancelled = False
ticket_booking.paid = False
ticket_booking.warning_sent = True (only for payment due date)

ticketed_event.payment_due_date < now

ticket_booking.date_warning_sent is > 2 hrs ago
if not ticketed_event.payment_due_date:
    now > ticket_booking.date_booked + ticketed_event.payment_time_allowed
    (check the date_booked first; if payment_time_allowed is <6 hrs, default
    to 6)

Email user that their booking has been cancelled
'''
import logging
from datetime import timedelta
import pytz

from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import get_template
from django.core.management.base import BaseCommand

from booking.models import TicketedEvent
from booking.email_helpers import send_support_email
from activitylog.models import ActivityLog
from common.management import write_command_name


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Cancel unpaid ticket bookings that are past payment_due_date or payment time allowed'
    def handle(self, *args, **options):
        # only cancel between 9am and 10pm; warnings are sent from 7 so this allows a minimum of 2 hrs after warning
        # for payment before the next cancel job is run
        write_command_name(self, __file__)
        cancel_start_time = 9
        cancel_end_time = 22
        now = timezone.now().astimezone(pytz.timezone("Europe/London"))
        if cancel_start_time <= now.hour < cancel_end_time:
            self.cancel_ticket_bookings(now)
        else:
            self.stdout.write(f"Outside of valid auto-cancel time (09:00 - 22:00)")

    def get_ticket_bookings_to_cancel(self, now):
        checkout_buffer_seconds = 60 * 5
        warning_sent_buffer = now - timedelta(hours=2)
        # get relevant ticketed_events
        ticketed_events = TicketedEvent.objects.filter(
            date__gte=now,
            cancelled=False,
            ticket_cost__gt=0,
            advance_payment_required=True,
        )
        for event in ticketed_events:
            # get open unpaid ticket bookings, exclude those with either no warning sent date yet, 
            # or warning sent date < 2hrs ago
            ticket_bookings = event.ticket_bookings.filter(
                cancelled=False, paid=False
            ).exclude(
                date_warning_sent__gte=warning_sent_buffer
            ).exclude(
                # exclude bookings with checkout time within past 5 mins
                checkout_time__gte=timezone.now() - timedelta(seconds=checkout_buffer_seconds)
            )

            # if payment due date is past and warning has been sent, cancel
            if event.payment_due_date and event.payment_due_date < now:
                for bkg in ticket_bookings:
                    if bkg.warning_sent:
                        yield bkg

            elif event.payment_time_allowed:
                # if there's a payment time allowed, cancel bookings booked
                # longer ago than this
                # don't check for warning sent this time
                for bkg in ticket_bookings:
                    if bkg.date_booked < now - timedelta(hours=event.payment_time_allowed):
                        yield bkg

    def cancel_ticket_bookings(self, now):

        ticket_bookings_for_studio_email = [] if settings.SEND_ALL_STUDIO_EMAILS else None

        for ticket_booking in self.get_ticket_bookings_to_cancel(now):
            ctx = {
                  'ticket_booking': ticket_booking,
                  'ticketed_event': ticket_booking.ticketed_event,
            }
            # send mails to users
            try:
                send_mail('{} Ticket Booking ref {} cancelled'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                    ticket_booking.booking_reference
                ),
                    get_template(
                        'booking/email/ticket_booking_auto_cancelled.txt'
                    ).render(ctx),
                    settings.DEFAULT_FROM_EMAIL,
                    [ticket_booking.user.email],
                    html_message=get_template(
                        'booking/email/ticket_booking_auto_cancelled.html'
                        ).render(ctx),
                    fail_silently=False)
            except Exception as e:
                # send mail to tech support with Exception
                send_support_email(
                    e, __name__, "Automatic cancel ticket booking job - cancelled email"
                )
            ticket_booking.cancelled = True
            ticket_booking.save()

            ActivityLog.objects.create(
                log='Unpaid ticket booking ref {} for event {}, user {} '
                    'automatically cancelled'.format(
                    ticket_booking.booking_reference,
                    ticket_booking.ticketed_event,
                    ticket_booking.user.username
                )
            )

            if ticket_bookings_for_studio_email is not None:
                ticket_bookings_for_studio_email.append(ticket_booking)

        if ticket_bookings_for_studio_email:
            try:
                # send single mail to Studio
                send_mail('{} Ticket Booking{} been automatically cancelled'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                    ' has' if len(ticket_bookings_for_studio_email) == 1 else 's have'),
                    get_template(
                        'booking/email/ticket_booking_auto_cancelled_studio_email.txt'
                    ).render({'bookings': ticket_bookings_for_studio_email}),
                    settings.DEFAULT_FROM_EMAIL,
                    [settings.DEFAULT_STUDIO_EMAIL],
                    html_message=get_template(
                        'booking/email/ticket_booking_auto_cancelled_studio_email.html'
                        ).render({'bookings': ticket_bookings_for_studio_email}),
                    fail_silently=False)
                self.stdout.write(
                    'Cancellation emails sent for ticket booking refs {}'.format(
                        ', '.join(
                            [str(booking.booking_reference)
                             for booking in ticket_bookings_for_studio_email]
                        )
                    )
                )
            except Exception as e:
                # send mail to tech support with Exception
                send_support_email(
                    e, __name__,
                    "Automatic cancel ticket booking job - studio email"
                )
        else:
            self.stdout.write('No ticket bookings to cancel')


