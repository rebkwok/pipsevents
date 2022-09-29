'''
Check for unpaid bookings with paypal_pending and ensure they haven't actually been paid
'''
import logging
from datetime import timedelta
from pickle import POP_MARK
import pytz

from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import get_template
from django.core.management.base import BaseCommand

from paypal.standard.ipn.models import PayPalIPN
from paypal.standard.models import ST_PP_COMPLETED

from booking.models import Block, Booking
from booking.email_helpers import send_support_email, send_waiting_list_email
from activitylog.models import ActivityLog

from payments.models import PaypalBookingTransaction, PaypalBlockTransaction


logger = logging.getLogger(__name__)


class Command(BaseCommand):

    def handle(self, *args, **options):

        unpaid_pending_bookings = Booking.objects.filter(
            status="OPEN", paypal_pending=True, paid=False
        )
        unpaid_pending_blocks = Block.objects.filter(
            paypal_pending=True, paid=False
        )
        fixed_bookings = []
        for booking in unpaid_pending_bookings:
            booking_pp_trans = PaypalBookingTransaction.objects.filter(
                booking=booking, transaction_id__isnull=False
            )
            if booking_pp_trans.exists():
                pp_ipns = PayPalIPN.objects.filter(
                    txn_id=booking_pp_trans.first().transaction_id, payment_status=ST_PP_COMPLETED
                )
                if pp_ipns.exists():
                    pp_ipn = pp_ipns.first()
                    booking.paid = True
                    booking.payment_confirmed = True
                    booking.save()
                    fixed_bookings.append({"id": booking.id, "txn_id": pp_ipn.txn_id})
                    ActivityLog.objects.create(
                        log=f"Booking id {booking.id} with paypal_pending has completed txn {pp_ipn.txn_id} auto-updated to paid"
                    )
        
        fixed_blocks = []
        for block in unpaid_pending_blocks:
            block_pp_trans = PaypalBlockTransaction.objects.filter(
                block=block, transaction_id__isnull=False
            )
            if block_pp_trans.exists():
                pp_ipns = PayPalIPN.objects.filter(
                    txn_id=block_pp_trans.first().transaction_id, payment_status=ST_PP_COMPLETED
                )
                if pp_ipns.exists():
                    pp_ipn = pp_ipns.first()
                    block.paid = True
                    block.save()
                    fixed_blocks.append({"id": block.id, "txn_id": pp_ipn.txn_id})
                    ActivityLog.objects.create(
                        log=f"Block id {block.id} with paypal_pending has completed txn {pp_ipn.txn_id} auto-updated to paid"
                    )

        if fixed_bookings or fixed_blocks:
            ctx = {
                "fixed_bookings": fixed_bookings,
                "fixed_blocks": fixed_blocks
            }
            send_mail(
                subject=f'{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Item payment status updated',
                message=get_template(
                    'payments/email/payment_status_autoupdated.txt'
                ).render(ctx),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.SUPPORT_EMAIL],
                fail_silently=False
            )

        booking_ids = ",".join(str(item["id"]) for item in fixed_bookings)
        block_ids = ",".join(str(item["id"]) for item in fixed_blocks)
        if booking_ids or block_ids:
            return f"booking_ids: {booking_ids}, block_ids: {block_ids}"
        return "No booking or blocks to update"
