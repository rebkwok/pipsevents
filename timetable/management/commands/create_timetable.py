# -*- coding: utf-8 -*-
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
        pp, _ = EventType.objects.get_or_create(event_type='CL', subtype='Pole practice')
        pv, _ = EventType.objects.get_or_create(event_type='CL', subtype='Private')
        ex, _ = EventType.objects.get_or_create(event_type='CL', subtype='External instructor class')

        # Monday classes
        Session.objects.get_or_create(
            name="Pole Level 3",
            day=Session.MON,
            event_type=pc,
            time=time(hour=17, minute=45),
            external_instructor=False,
        )

        Session.objects.get_or_create(
            name="Pole Level 1",
            day=Session.MON,
            event_type=pc,
            max_participants=15,
            time=time(hour=19, minute=0),
            external_instructor=False,
        )

        Session.objects.get_or_create(
            name="Private (1 or more students)",
            day=Session.MON,
            event_type=pv,
            time=time(hour=20, minute=10),
            external_instructor=False,
            cost=30,
            email_studio_when_booked=True,
            max_participants=1,
            payment_info="Privates are charged at £30 per person. Additional "
                         "people are £15 per hour.  Reserve your private "
                         "by making your initial payment; if you wish to add "
                         "additional people to the booking, please contact "
                         "the studio to arrange the additional payments."
        )

        # Tuesday classes
        Session.objects.get_or_create(
            name="Pole Level 2",
            day=Session.TUE,
            event_type=pc,
            time=time(hour=17, minute=45),
            external_instructor=False,
        )

        Session.objects.get_or_create(
            name="Pole Level 4",
            day=Session.TUE,
            event_type=pc,
            time=time(hour=19, minute=0),
            external_instructor=False,
        )

        Session.objects.get_or_create(
            name="Pole Level 1",
            day=Session.TUE,
            event_type=pc,
            max_participants=15,
            time=time(hour=20, minute=10),
            external_instructor=False,

        )

        # Thursday classes
        Session.objects.get_or_create(
            name="Mixed Pole Levels",
            day=Session.THU,
            event_type=pc,
            time=time(hour=11, minute=0),
            external_instructor=False,
        )

        Session.objects.get_or_create(
            name="Pole Level 1",
            day=Session.THU,
            event_type=pc,
            max_participants=15,
            time=time(hour=17, minute=45),
            external_instructor=False,
        )

        Session.objects.get_or_create(
            name="Pole Level 2",
            day=Session.THU,
            event_type=pc,
            time=time(hour=20, minute=10),
            external_instructor=False,
        )

        # Friday classes
        Session.objects.get_or_create(
            name="Private (1 or more students)",
            day=Session.FRI,
            event_type=pv,
            time=time(hour=17, minute=45),
            external_instructor=False,
            cost=30,
            email_studio_when_booked=True,
            max_participants=1,
            payment_info="Privates are charged at £30 per person. Additional "
                         "people are £15 per hour.  Reserve your private "
                         "by making your initial payment; if you wish to add "
                         "additional people to the booking, please contact "
                         "the studio to arrange the additional payments."
        )

        Session.objects.get_or_create(
            name="Pole Level 4",
            day=Session.FRI,
            event_type=pc,
            time=time(hour=17, minute=45),
            max_participants=15,
            external_instructor=False,
        )

        Session.objects.get_or_create(
            name="Pole Level 3",
            day=Session.FRI,
            event_type=pc,
            time=time(hour=19, minute=0),
            external_instructor=False,
        )

        Session.objects.get_or_create(
            name="Pole practice",
            day=Session.FRI,
            event_type=pp,
            time=time(hour=20, minute=10),
            max_participants=15,
            cost=3.50,
            external_instructor=False,
        )

        # SUN CLASSES
        Session.objects.get_or_create(
            name="Pole practice",
            day=Session.SUN,
            event_type=pp,
            time=time(hour=17, minute=45),
            max_participants=15,
            cost=3.50,
            external_instructor=False,
        )
