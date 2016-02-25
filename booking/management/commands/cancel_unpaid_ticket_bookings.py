'''
Check for unpaid ticket bookings and cancel where:
ticketed_event.cancelled = False
ticketed event is not in the past
ticketed_event.advance_payment_required
ticketed_event.ticket_cost > 0

ticket_booking.cancelled = False
ticket_booking.paid = False
ticket_booking.warning_sent = True (only for payment due date)

ticketed_event.payment_due_date < timezone.now()

ticket_booking.date_booked is > 6 hrs ago
if not ticketed_event.payment_due_date:
    now > ticket_booking.date_booked + ticketed_event.payment_time_allowed
    (check the date_booked first; if payment_time_allowed is <6 hrs, default
    to 6)

Email user that their booking has been cancelled
'''
import logging
from datetime import timedelta

from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import get_template
from django.core.management.base import BaseCommand
from django.core import management

from booking.models import TicketBooking, TicketedEvent
from booking.email_helpers import send_support_email, send_waiting_list_email
from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Cancel unpaid ticket bookings that are past payment_due_date or '
    'payment time allowed'
    def handle(self, *args, **options):

        # get relevant ticketed_events
        ticketed_events = TicketedEvent.objects.filter(
            date__gte=timezone.now(),
            cancelled=False,
            ticket_cost__gt=0,
            advance_payment_required=True,
        )

        bookings_to_cancel = []
        # import ipdb; ipdb.set_trace()
        for event in ticketed_events:
            # get open unpaid ticket bookings made > 6 hrs ago
            ticket_bookings = [
                bkg for bkg in event.ticket_bookings.all()
                if not bkg.cancelled and not bkg.paid
                and (bkg.date_booked < timezone.now() - timedelta(hours=6))
                ]

            # if payment due date is past and warning has been sent, cancel
            if event.payment_due_date and event.payment_due_date < timezone.now():
                for bkg in ticket_bookings:
                    if bkg.warning_sent:
                        bookings_to_cancel.append(bkg)

            elif event.payment_time_allowed:
                # if there's a payment time allowed, cancel bookings booked
                # longer ago than this (ticket_bookings already filtered out
                # any booked within 6 hrs)
                # don't check for warning sent this time
                for bkg in ticket_bookings:
                    if bkg.date_booked < timezone.now() \
                            - timedelta(hours=event.payment_time_allowed):
                        bookings_to_cancel.append(bkg)

        for ticket_booking in bookings_to_cancel:

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

        if bookings_to_cancel:
            if settings.SEND_ALL_STUDIO_EMAILS:
                try:
                    # send single mail to Studio
                    send_mail('{} Ticket Booking{} been automatically cancelled'.format(
                        settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                        ' has' if len(bookings_to_cancel) == 1 else 's have'),
                        get_template(
                            'booking/email/ticket_booking_auto_cancelled_studio_email.txt'
                        ).render({'bookings': bookings_to_cancel}),
                        settings.DEFAULT_FROM_EMAIL,
                        [settings.DEFAULT_STUDIO_EMAIL],
                        html_message=get_template(
                            'booking/email/ticket_booking_auto_cancelled_studio_email.html'
                            ).render({'bookings': bookings_to_cancel}),
                        fail_silently=False)
                    self.stdout.write(
                        'Cancellation emails sent for ticket booking refs {}'.format(
                            ', '.join(
                                [str(booking.booking_reference)
                                 for booking in bookings_to_cancel]
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


