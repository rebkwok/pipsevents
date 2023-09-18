'''
Email warnings for unpaid bookings if booked/rebooked > 2hrs ago

Check for bookings where:
booking.status == OPEN
booking.payment_confirmed = False
booking.paid = False

Add warning_sent flags to booking model so
we don't keep sending

BUT excluding bookings with a checkout_time in the past 5 mins
(checkout_time is set when user clicks button to pay with stripe)
'''
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import get_template
from django.core.management.base import BaseCommand
from django.db.models import Q

from paypal.standard.ipn.models import PayPalIPN
from paypal.standard.models import ST_PP_COMPLETED

from booking.models import Booking, Event
from activitylog.models import ActivityLog
from payments.models import PaypalBookingTransaction


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
    cutoff = timezone.now() - timedelta(hours=2)
    checkout_cutoff = timezone.now() - timedelta(seconds=5*60)
    rebooked_more_than_2hrs_ago = Q(date_rebooked__lte=cutoff)
    booked_more_than_2hrs_ago = Q(date_booked__lte=cutoff)

    return Booking.objects.filter(
        (rebooked & rebooked_more_than_2hrs_ago) | (not_rebooked & booked_more_than_2hrs_ago ),
        event_id__in=event_ids,
        status='OPEN',
        paid=False,
        payment_confirmed=False,
        warning_sent=False,
        ).exclude(checkout_time__gte=checkout_cutoff)


def send_warning_email(self, upcoming_bookings):
    # First double-check each booking hasn't been paid by PayPal now
    bookings_to_warn = check_paypal(upcoming_bookings)

    for booking in bookings_to_warn:
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
        booking.warning_sent = True
        booking.save()

    if bookings_to_warn:
        self.stdout.write(
            f"Warning emails sent for booking ids {', '.join(str(bk.id) for bk in bookings_to_warn)}"
        )

    else:
        self.stdout.write('No warnings to send')

    already_paid = set(upcoming_bookings) - set(bookings_to_warn)
    if already_paid:
        self.stdout.write(f"Bookings set to paid: {', '.join(str(bk.id) for bk in already_paid)}")


def _make_paid(booking):
    booking.payment_confirmed = True
    booking.paid = True
    booking.paypal_pending = False
    booking.save()


def check_paypal(bookings):
    bookings_to_warn = []
    for booking in bookings:
        if booking.block:
            # this should never happen because the model save method should always make
            # bookings with blocks paid
            _make_paid(booking)
        else:
            pptxns = PaypalBookingTransaction.objects.filter(booking=booking)
            if not pptxns.exists():
                # all bookings that went through paypal should have a transaction associated
                # but if it doesn't, we definitely need to warn
                bookings_to_warn.append(booking)
            else:
                pptxn = pptxns.order_by("-transaction_id").first()
                # It has at least one matching completed PayPalIPN associated
                ppipns = PayPalIPN.objects.filter(invoice=pptxn.invoice_id, payment_status=ST_PP_COMPLETED)
                if ppipns.exists():
                    ppipn = ppipns.first()
                    _make_paid(booking)
                    # ensure the transaction ID is set
                    pptxn.transaction_id = ppipn.txn_id
                    pptxn.save()
                else:
                    bookings_to_warn.append(booking)
    return bookings_to_warn
