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
        pc_ext, _ = EventType.objects.get_or_create(
            event_type='CL',
            subtype='Pole level class - extended'
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

        ws_int = EventType.objects.get_or_create(
            event_type='EV',
            subtype='Workshop - in-house'
        )
        ws_ext = EventType.objects.get_or_create(
            event_type='EV',
            subtype='Workshop - external'
        )
        ev = EventType.objects.get_or_create(
            event_type='EV',
            subtype='Other event'
        )

        rh = EventType.objects.get_or_create(
            event_type='RH',
            subtype='Studio/room hire'
        )

        self.stdout.write("Creating block types")
        bt, created_bt = BlockType.objects.get_or_create(
            event_type=pc,
            size=5,
            cost=35.00,
            duration=2,
            identifier="standard",
        )
        if created_bt:
            bt.active=True
            bt.save()

        bt1, created_bt1 = BlockType.objects.get_or_create(
            event_type=pc,
            size=10,
            cost=68.00,
            duration=4,
            identifier="standard",
        )
        if created_bt1:
            bt1.active=True
            bt1.save()

        bt2, created_bt2 = BlockType.objects.get_or_create(
            event_type=pp,
            size=10,
            cost=36.00,
            duration=4,
            identifier="standard",
        )
        if created_bt2:
            bt2.active=True
            bt2.save()

        sale_bt, created_sale_bt = BlockType.objects.get_or_create(
            event_type=pc,
            size=5,
            cost=30.00,
            duration=2,
            identifier="sale",
        )
        if created_sale_bt:
            sale_bt.active=True
            sale_bt.save()
        sale_bt1, created_sale_bt1 = BlockType.objects.get_or_create(
            event_type=pc,
            size=10,
            cost=57.00,
            duration=4,
            identifier="sale",
        )
        if created_sale_bt1:
            sale_bt1.active=True
            sale_bt1.save()
        sale_bt2, created_sale_bt2 = BlockType.objects.get_or_create(
            event_type=pp,
            size=10,
            cost=25.00,
            duration=4,
            identifier="sale",
        )
        if created_sale_bt2:
            sale_bt2.active=True
            sale_bt2.save()

        # free class blocks should always be inactive so they don't come up in
        # the options for users to purchase
        free, _ = BlockType.objects.get_or_create(
            event_type=pc,
            size=1,
            cost=0,
            duration=1,
            identifier="free class"
        )
        free.active = False
        free.save()
