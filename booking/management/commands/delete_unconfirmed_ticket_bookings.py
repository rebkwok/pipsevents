'''
Check for unpaid ticket bookings without 'purchase confirmed' and delete if
more than 1 hr since booking
No need to email users since this is just cleaning up aborted bookings
('confirm purchase' not clicked during booking process)
'''
import logging
from datetime import timedelta

from django.utils import timezone
from django.core.management.base import BaseCommand

from booking.models import TicketBooking
from common.management import write_command_name
from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Delete unpaid ticket bookings that are not marked as ' \
           '"purchase_confirmed" (i.e. "confirm purchase" button not clicked ' \
           'during booking process and booking aborted without using cancel ' \
           'button'

    def handle(self, *args, **options):
        write_command_name(self, __file__)
        # get relevant ticket_bookings
        bookings_to_delete = TicketBooking.objects.filter(
            purchase_confirmed=False,
            paid=False,
            date_booked__lt=timezone.now() - timedelta(hours=1),
        )

        for ticket_booking in bookings_to_delete:

            ticket_booking.delete()

            ActivityLog.objects.create(
                log='Aborted (purchase unconfirmed) ticket booking ref {} '
                    'for event {}, user {} automatically deleted '
                    'after 1 hr'.format(
                    ticket_booking.booking_reference,
                    ticket_booking.ticketed_event,
                    ticket_booking.user.username
                )
            )

        if bookings_to_delete:
            # send single mail to Studio
            self.stdout.write(
                'Aborted ticket booking refs {} deleted'.format(
                    ', '.join(
                        [str(booking.booking_reference)
                         for booking in bookings_to_delete]
                    )
                )
            )
        else:
            self.stdout.write('No unconfirmed ticket bookings to delete')
