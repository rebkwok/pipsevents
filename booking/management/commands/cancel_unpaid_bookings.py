'''
Check for unpaid bookings and cancel where:
booking.status = OPEN
paid = False
advance_payment_required = True
warning sent > 2 hrs ago (warning job already allowed a min 2hrs since booking, so this gives at least 4 hrs before cancelling)
AND
(payment_due_date < now
OR
date - cancellation_period < now
OR
now - date_booked/rebooked > payment_time_allowed
)
Email user that their booking has been cancelled

BUT excluding bookings with a checkout_time in the past 5 mins
(checkout_time is set when user clicks button to pay with stripe)
'''
import logging
from datetime import timedelta
import pytz

from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import get_template
from django.core.management.base import BaseCommand

from booking.models import Booking, WaitingListUser
from booking.email_helpers import send_support_email, send_waiting_list_email
from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Cancel unpaid bookings that are past payment_due_date, ' \
           'payment_time_allowed or cancellation_period'

    def handle(self, *args, **options):
        # only cancel between 9am and 10pm; warnings are sent from 7 so this allows a minimum of 2 hrs after warning
        # for payment before the next cancel job is run
        cancel_start_time = 9
        cancel_end_time = 22
        now = timezone.now().astimezone(pytz.timezone("Europe/London"))
        if cancel_start_time <= now.hour < cancel_end_time:
            self.cancel_bookings(now)

    def get_bookings_to_cancel(self, now):
        checkout_buffer_seconds = 60 * 5
        warning_time_buffer = now - timedelta(hours=2)
        bookings_qset = Booking.objects.filter(
            event__date__gte=now,
            event__advance_payment_required=True,
            status='OPEN',
            no_show=False,
            paid=False,
            payment_confirmed=False,
            paypal_pending=False,
        ).exclude(
            # exclude bookings with warning send within past 2 hrs
            date_warning_sent__gte=warning_time_buffer # doesn't exclude date_warning_sent==None
        ).exclude(
            # exclude bookings with checkout time within past 5 mins
            checkout_time__gte=timezone.now() - timedelta(seconds=checkout_buffer_seconds)
        )
        for booking in bookings_qset:
            if (booking.event.date - timedelta(hours=booking.event.cancellation_period)) < now:
                if booking.warning_sent:
                    yield booking
            if booking.event.payment_due_date and booking.warning_sent:
                if booking.event.payment_due_date < now:
                    yield booking
            if booking.event.payment_time_allowed:
                # if there's a payment time allowed, cancel bookings booked longer ago than this
                # don't check for warning sent this time
                # for free class requests, always allow them 24 hrs so admin
                # have time to mark classes as free (i.e.paid)
                last_booked_date = booking.date_rebooked if booking.date_rebooked else booking.date_booked
                if booking.free_class_requested:
                    if last_booked_date < now - timedelta(hours=24):
                        yield booking
                elif last_booked_date < (now - timedelta(hours=booking.event.payment_time_allowed)):
                    yield booking

    def cancel_bookings(self, now):
        bookings_for_studio_email = []
        send_waiting_list = set()
        for booking in self.get_bookings_to_cancel(now):
            ctx = {
                  'booking': booking,
                  'event': booking.event,
                  'date': booking.event.date.strftime('%A %d %B'),
                  'time': booking.event.date.strftime('%I:%M %p'),
            }
            # send mails to users
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
            booking.status = 'CANCELLED'
            booking.block = None
            booking.auto_cancelled = True
            booking.save()
            ActivityLog.objects.create(
                log='Unpaid booking id {} for event {}, user {} '
                    'automatically cancelled'.format(
                        booking.id, booking.event, booking.user
                )
            )
            if settings.SEND_ALL_STUDIO_EMAILS:
                bookings_for_studio_email.append(booking)
            send_waiting_list.add(booking.event)

        for event in send_waiting_list:
            waiting_list_users = WaitingListUser.objects.filter(event=event)
            if waiting_list_users.exists():
                try:
                    send_waiting_list_email(
                        event, [user.user for user in waiting_list_users]
                    )
                    ActivityLog.objects.create(
                        log='Waiting list email sent to user(s) {} for '
                        'event {}'.format(
                            ', '.join(
                                [wluser.user.username for wluser in waiting_list_users]
                            ),
                            event
                        )
                    )
                except Exception as e:
                    # send mail to tech support with Exception
                    send_support_email(
                        e, __name__, "Automatic cancel job - waiting list email"
                    )

        if bookings_for_studio_email:
            # send single mail to Studio
            try:
                send_mail('{} Booking{} been automatically cancelled'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                    ' has' if len(bookings_for_studio_email) == 1 else 's have'),
                    get_template(
                        'booking/email/booking_auto_cancelled_studio_email.txt'
                    ).render({'bookings': bookings_for_studio_email}),
                    settings.DEFAULT_FROM_EMAIL,
                    [settings.DEFAULT_STUDIO_EMAIL],
                    html_message=get_template(
                        'booking/email/booking_auto_cancelled_studio_email.html'
                        ).render({'bookings': bookings_for_studio_email}),
                    fail_silently=False)
                self.stdout.write(
                    'Cancellation emails sent for booking ids {}'.format(
                        ', '.join([str(booking.id) for booking in bookings_for_studio_email])
                    )
                )
            except Exception as e:
                # send mail to tech support with Exception
                send_support_email(
                    e, __name__, "Automatic cancel job - studio email"
                )
