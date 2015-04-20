from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import time
from timetable.models import Session
from booking.models import EventType

class Command(BaseCommand):

    def handle(self, *args, **options):

        """
        Create the default timetable sessions
        """
        self.stdout.write('Creating timetable sessions.')

        pc, _ = EventType.objects.get_or_create(event_type='CL', subtype='Pole level class')
        cl, _ = EventType.objects.get_or_create(event_type='CL', subtype='Other class')
        ex, _ = EventType.objects.get_or_create(event_type='CL', subtype='External instructor')

        # Monday classes
        Session.objects.get_or_create(
            name="Pole Level 3",
            day=Session.MON,
            event_type=pc,
            time=time(hour=17, minute=45),
        )

        Session.objects.get_or_create(
            name="Pole Level 1",
            day=Session.MON,
            event_type=pc,
            max_participants=15,
            time=time(hour=19, minute=0),
        )

        Session.objects.get_or_create(
            name="Pole practice",
            day=Session.MON,
            event_type=cl,
            time=time(hour=20, minute=10),
        )

        # Tuesday classes
        Session.objects.get_or_create(
            name="Pole Level 2",
            day=Session.TUE,
            event_type=pc,
            time=time(hour=17, minute=45),
        )

        Session.objects.get_or_create(
            name="Pole Level 4",
            day=Session.TUE,
            event_type=pc,
            time=time(hour=19, minute=0),
        )

        Session.objects.get_or_create(
            name="Pole Level 1",
            day=Session.TUE,
            event_type=pc,
            max_participants=15,
            time=time(hour=20, minute=10),
        )

        # Wednesday classes
        Session.objects.get_or_create(
            name="Flexibility (with Alicia)",
            day=Session.WED,
            event_type=ex,
            time=time(hour=19, minute=00),
            booking_open=False,
            payment_open=False,
            payment_info="For further information and to book, please contact " \
                         "Alicia"
        )
        Session.objects.get_or_create(
            name="Flexibility (with Alicia)",
            day=Session.WED,
            event_type=ex,
            time=time(hour=20, minute=10),
            booking_open=False,
            payment_open=False,
            payment_info="For further information and to book, please contact " \
                         "Alicia"
        )
        # Thursday classes
        Session.objects.get_or_create(
            name="Pole Mixed Levels",
            day=Session.THU,
            event_type=pc,
            time=time(hour=11, minute=0),
        )

        Session.objects.get_or_create(
            name="Pole - advanced (with Polefit Starlet)",
            day=Session.THU,
            event_type=ex,
            time=time(hour=19, minute=10),
            booking_open=False,
            payment_open=False,
            payment_info="For further information and to book, please contact " \
                         "Polefit Starlet"
        )

        Session.objects.get_or_create(
            name="Pole Level 2",
            day=Session.THU,
            event_type=pc,
            time=time(hour=20, minute=10),
        )

        # Friday classes
        Session.objects.get_or_create(
            name="Pole Level 1",
            day=Session.FRI,
            event_type=pc,
            max_participants=15,
            time=time(hour=17, minute=45),
        )

        Session.objects.get_or_create(
            name="Pole Level 3",
            day=Session.FRI,
            event_type=pc,
            time=time(hour=19, minute=0),
        )

        Session.objects.get_or_create(
            name="Pole practice",
            day=Session.FRI,
            event_type=cl,
            time=time(hour=20, minute=10),
            max_participants=15,
            cost=3.50,
        )
