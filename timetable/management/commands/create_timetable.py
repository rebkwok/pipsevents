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

        pc, _ = EventType.objects.get_or_create(type='CL', subtype='Pole level class')
        cl, _ = EventType.objects.get_or_create(type='CL', subtype='Other class')

        # Monday classes
        Session.objects.get_or_create(
            name="Pole Level 3",
            day=Session.MON,
            type=pc,
            time=time(hour=17, minute=45),
        )

        Session.objects.get_or_create(
            name="Pole Level 1",
            day=Session.MON,
            type=pc,
            time=time(hour=19, minute=0),
        )

        Session.objects.get_or_create(
            name="Pole practice",
            day=Session.MON,
            type=cl,
            time=time(hour=20, minute=10),
        )

        # Tuesday classes
        Session.objects.get_or_create(
            name="Pole Level 2",
            day=Session.TUE,
            type=pc,
            time=time(hour=17, minute=45),
        )

        Session.objects.get_or_create(
            name="Pole Level 4",
            day=Session.TUE,
            type=pc,
            time=time(hour=19, minute=0),
        )

        Session.objects.get_or_create(
            name="Pole Level 1",
            day=Session.TUE,
            type=pc,
            time=time(hour=20, minute=10),
        )

        # Wednesday classes
        Session.objects.get_or_create(
            name="Pole conditioning",
            day=Session.WED,
            type=cl,
            time=time(hour=19, minute=0),
            max_participants=15,
            cost=3.50,
        )

        # Thursday classes
        Session.objects.get_or_create(
            name="Pole Mixed Levels",
            day=Session.THU,
            type=pc,
            time=time(hour=11, minute=0),
        )

        Session.objects.get_or_create(
            name="Pole Level 2",
            day=Session.THU,
            type=pc,
            time=time(hour=20, minute=10),
        )

        # Friday classes
        Session.objects.get_or_create(
            name="Pole Level 1",
            day=Session.FRI,
            type=pc,
            time=time(hour=17, minute=45),
        )

        Session.objects.get_or_create(
            name="Pole Level 3",
            day=Session.FRI,
            type=pc,
            time=time(hour=19, minute=0),
        )

        Session.objects.get_or_create(
            name="Pole practice",
            day=Session.FRI,
            type=cl,
            time=time(hour=20, minute=10),
            max_participants=15,
            cost=3.50,
        )
