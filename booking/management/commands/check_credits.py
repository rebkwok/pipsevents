# pragma: no cover
from datetime import datetime

from booking.models import Block

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'check reactivated credits'

    def handle(self, *args, **options):

        reactivated_blocks = Block.objects.filter(
            block_type__identifier="Reactivated", start_date__gte=datetime(2021, 9, 2)
        )
        total = sum([block.block_type.size for block in reactivated_blocks])
        still_left_to_use = sum(
            [(block.block_type.size - block.bookings_made()) for block in reactivated_blocks if block.active_block()]
        )
        self.stdout.write(f"{still_left_to_use} still left out of {total} reactivated")
