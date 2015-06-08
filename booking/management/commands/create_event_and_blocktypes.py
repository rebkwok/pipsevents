from django.core.management.base import BaseCommand, CommandError
from booking.models import BlockType, EventType

class Command(BaseCommand):
    """
    Create block types; currently blocks are 5 or 10 classes
    pole class:
    5 classes = GBP 32, 10 classes = GBP 62
    5 classes expires in 2 months, 10 classes expires in 4 months
    pole practice:
    5 classes = GBP 16, 10 classes = GBP 31
    5 classes expires in 2 months, 10 classes expires in 4 months
    """
    def handle(self, *args, **options):

        self.stdout.write("Creating event types")
        pc, _ = EventType.objects.get_or_create(
            event_type='CL',
            subtype='Pole level class'
        )
        pp, _ = EventType.objects.get_or_create(
            event_type='CL',
            subtype='Pole practice'
        )
        cl, _ = EventType.objects.get_or_create(
            event_type='CL',
            subtype='Other class'
        )
        pv, _ = EventType.objects.get_or_create(
            event_type='CL',
            subtype='Private'
        )
        ex, _ = EventType.objects.get_or_create(
            event_type='CL',
            subtype='External instructor class'
        )

        ws = EventType.objects.get_or_create(
            event_type='EV',
            subtype='Workshop'
        )
        ev = EventType.objects.get_or_create(
            event_type='EV',
            subtype='Other event'
        )

        self.stdout.write("Creating block types")
        BlockType.objects.get_or_create(
            event_type=pc,
            size=5,
            cost=32.00,
            duration=2
        )

        BlockType.objects.get_or_create(
            event_type=pc,
            size=10,
            cost=62.00,
            duration=4
        )
        BlockType.objects.get_or_create(
            event_type=pp,
            size=5,
            cost=16.00,
            duration=2
        )

        BlockType.objects.get_or_create(
            event_type=pp,
            size=10,
            cost=31.00,
            duration=4
        )
