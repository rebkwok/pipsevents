'''
Check users with current active blocks and for each block, report any bookings
that:
- have the same event__event_type__subtype as the
  block__block_type__event_type__subtype
- have no block
Of those:
- bookings that are marked paid

Unlikely that users who have blocks will have booked without using the block
If unpaid, it may have been booked for an event that doesn't require advance
payment, in which case it won't be cancelled and won't count towards the block
which it probably should
If paid, check that it also has an associated paypal txn id; if not, it's likely
been unassigned by an unidentified bug
'''
from django.conf import settings
from django.core.mail import send_mail

from django.core.management.base import BaseCommand
from django.core import management

from booking.models import Block, Booking
from activitylog.models import ActivityLog
from payments.models import PaypalBookingTransaction

class Command(BaseCommand):
    help = 'run reports on users with active blocks'

    def handle(self, *args, **options):

        active_blocks = [
            block for block in Block.objects.all() if block.active_block()
        ]

        blocks_with_issues = []

        for block in active_blocks:
            block_subtype = block.block_type.event_type.subtype

            open_user_bookings_since_block_start = Booking.objects.filter(
                user=block.user, date_booked__gte=block.start_date,
                status='OPEN', event__event_type__subtype=block_subtype
            )

            bookings_without_block = [
                booking for booking in open_user_bookings_since_block_start if booking.block == None
            ]

            if bookings_without_block:
                blocks_with_issues.append(block.id)

                self.stdout.write(
                    'User {} ({}) has {} booking{} made for class '
                    'type {} without using the active block {}'.format(
                        block.user.username, block.user.id, len(bookings_without_block), '' if len(bookings_without_block) == 1 else 's',
                        block_subtype, block.id
                    )
                )

                unpaid_bookings = [
                    str(booking.id) for booking in bookings_without_block if \
                    not booking.paid or not booking.payment_confirmed
                ]
                paid_booking_ids = [
                    booking.id for booking in bookings_without_block if
                    booking.paid and not booking.free_class
                ]
                paid_bookings = [
                    str(id) for id in paid_booking_ids
                ]

                ppbs = PaypalBookingTransaction.objects.filter(
                    booking_id__in=paid_booking_ids
                )
                paid_with_paypal = [str(ppb.booking_id) for ppb in ppbs if ppb.transaction_id is not None]
                self.stdout.write(
                    '{} booking{} unpaid or not marked as '
                    'payment_confirmed (ids {})'.format(
                        len(unpaid_bookings),
                        ' is' if len(unpaid_bookings) == 1 else 's are',
                        ', '.join(unpaid_bookings)
                    )
                )
                self.stdout.write(
                    '{} booking{} paid (ids {})'.format(
                        len(paid_bookings),
                        ' is' if len(paid_bookings) == 1 else 's are',
                        ', '.join(paid_bookings)
                    )
                )
                if paid_with_paypal:
                    self.stdout.write(
                        'Paid booking ids that have been paid directly with '
                        'paypal: {}'.format(
                            ', '.join(paid_with_paypal)
                        )
                    )

                send_mail('{} Block issues report for user {}'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, block.user.username),
                    'Possible issues for user {block_user}: \n'
                    'Has block: {blockstr} (id {blockid})\n'
                    '{num_unpaid} unpaid/unconfirmed bookings booked since '
                    'the block start date but not using block: '
                    'ids {unpaid_ids}\n'
                    '{num_paid} paid bookings booked since the block start '
                    'date but not using block: ids {paid_ids}\n'
                    'Paid bookings that were paid directly with paypal: '
                    'ids {paypal_paid_ids}\n'
                    'Check bookings for the users associated with these '
                    ' blocks'.format(
                        block_user=block.user.username,
                        blockstr=block, blockid=block.id,
                        num_unpaid=len(unpaid_bookings),
                        unpaid_ids=',' .join(unpaid_bookings),
                        num_paid=len(paid_bookings),
                        paid_ids=', '.join(paid_bookings),
                        paypal_paid_ids=', '.join(paid_with_paypal)
                    ),
                    settings.DEFAULT_FROM_EMAIL,
                    [settings.SUPPORT_EMAIL],
                    fail_silently=True
                )


                ActivityLog.objects.create(
                    log='Possible issues with bookings for user {}. Check bookings since {} block ({}) start that are not assigned to the block (support notified by email)'.format(
                        block.user.username, block_subtype, block.id
                    )
                )

        if not blocks_with_issues:
            self.stdout.write('No issues to report for users with blocks')
