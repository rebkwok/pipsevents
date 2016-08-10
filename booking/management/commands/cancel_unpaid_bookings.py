'''
Check for unpaid bookings and cancel where:
booking.status = OPEN
paid = False
advance_payment_required = True
Booking date booked OR booking date rebooked > 6 hrs ago
AND
(payment_due_date < timezone.now()
OR
date - cancellation_period < timezone.now()
OR
timezone.now() - date_booked/rebooked > payment_time_allowed
)
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

from booking.models import Booking, WaitingListUser
from booking.email_helpers import send_support_email, send_waiting_list_email
from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Cancel unpaid bookings that are past payment_due_date, ' \
           'payment_time_allowed or cancellation_period'

    def handle(self, *args, **options):

        bookings = []
        for booking in Booking.objects.filter(
            event__date__gte=timezone.now(),
            event__advance_payment_required=True,
            status='OPEN',
            paid=False,
            payment_confirmed=False,
            date_booked__lte=timezone.now() - timedelta(hours=6)):

            # ignore any which have been rebooked in the past 6 hrs
            if booking.date_rebooked and \
                    (booking.date_rebooked >=
                         (timezone.now() - timedelta(hours=6))):
                pass
            elif booking.event.date - timedelta(
                    hours=booking.event.cancellation_period
            ) < timezone.now() and booking.warning_sent:
                bookings.append(booking)
            elif booking.event.payment_due_date and booking.warning_sent:
                if booking.event.payment_due_date < timezone.now():
                    bookings.append(booking)
            elif booking.event.payment_time_allowed:
                # if there's a payment time allowed, cancel bookings booked
                # longer ago than this (bookings already filtered out
                # any booked or rebooked within 6 hrs)
                # don't check for warning sent this time
                # for free class requests, always allow them 24 hrs so admin
                # have time to mark classes as free (i.e.paid)
                last_booked_date = booking.date_rebooked \
                        if booking.date_rebooked else booking.date_booked
                if booking.free_class_requested:
                    if last_booked_date < timezone.now() - timedelta(hours=24):
                        bookings.append(booking)
                elif last_booked_date < timezone.now() \
                        - timedelta(hours=booking.event.payment_time_allowed):
                        bookings.append(booking)

        for booking in bookings:
            event_was_full = booking.event.spaces_left == 0

            ctx = {
                  'booking': booking,
                  'event': booking.event,
                  'date': booking.event.date.strftime('%A %d %B'),
                  'time': booking.event.date.strftime('%I:%M %p'),
            }
            # send mails to users
            try:
                send_mail('{} Booking cancelled: {}'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event.name),
                    get_template(
                        'booking/email/booking_auto_cancelled.txt'
                    ).render(ctx),
                    settings.DEFAULT_FROM_EMAIL,
                    [booking.user.email],
                    html_message=get_template(
                        'booking/email/booking_auto_cancelled.html'
                        ).render(ctx),
                    fail_silently=False)
            except Exception as e:
                # send mail to tech support with Exception
                send_support_email(
                    e, __name__, "Automatic cancel job - cancelled email"
                )
            booking.status = 'CANCELLED'
            booking.block = None
            booking.save()
            ActivityLog.objects.create(
                log='Unpaid booking id {} for event {}, user {} '
                    'automatically cancelled'.format(
                        booking.id, booking.event, booking.user
                )
            )
            if event_was_full:
                waiting_list_users = WaitingListUser.objects.filter(
                    event=booking.event
                )
                try:
                    send_waiting_list_email(
                        booking.event, [user.user for user in waiting_list_users]
                    )
                    ActivityLog.objects.create(
                        log='Waiting list email sent to user(s) {} for '
                        'event {}'.format(
                            ', '.join(
                                [wluser.user.username for \
                                    wluser in waiting_list_users]
                            ),
                            booking.event
                        )
                    )
                except Exception as e:
                    # send mail to tech support with Exception
                    send_support_email(
                        e, __name__, "Automatic cancel job - waiting list email"
                    )

        if bookings:
            if settings.SEND_ALL_STUDIO_EMAILS:
                # send single mail to Studio
                try:
                    send_mail('{} Booking{} been automatically cancelled'.format(
                        settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                        ' has' if len(bookings) == 1 else 's have'),
                        get_template(
                            'booking/email/booking_auto_cancelled_studio_email.txt'
                        ).render({'bookings': bookings}),
                        settings.DEFAULT_FROM_EMAIL,
                        [settings.DEFAULT_STUDIO_EMAIL],
                        html_message=get_template(
                            'booking/email/booking_auto_cancelled_studio_email.html'
                            ).render({'bookings': bookings}),
                        fail_silently=False)
                    self.stdout.write(
                        'Cancellation emails sent for booking ids {}'.format(
                            ', '.join([str(booking.id) for booking in bookings])
                        )
                    )
                except Exception as e:
                    # send mail to tech support with Exception
                    send_support_email(
                        e, __name__, "Automatic cancel job - studio email"
                    )
        else:
            self.stdout.write('No bookings to cancel')
