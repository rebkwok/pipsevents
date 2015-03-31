from django.core.management.base import BaseCommand, CommandError
from booking.models import BlockType, EventType

class Command(BaseCommand):
    """
    Create block types; currently blocks are 5 or 10 classes
    default event type = poleclass
    5 classes = GBP 32, 10 classes = GBP 62
    5 classes expires in 2 months, 10 classes expires in 4 months
    """
    def handle(self, *args, **options):

        self.stdout.write("Creating event types")
        pc, _ = EventType.objects.get_or_create(
            type='CL',
            subtype = 'Pole level class'
        )
        cl, _ = EventType.objects.get_or_create(
            type='CL',
            subtype = 'Other class'
        )

        ws = EventType.objects.get_or_create(
            type='EV',
            subtype = 'Workshop'
        )
        ev = EventType.objects.get_or_create(
            type='EV',
            subtype = 'Other event'
        )

        self.stdout.write("Creating block types")
        BlockType.objects.get_or_create(
            event_type=pc,
            size=5,
            cost = 32.00,
            duration = 2
        )

        BlockType.objects.get_or_create(
            event_type=pc,
            size=10,
            cost = 62.00,
            duration = 4
        )