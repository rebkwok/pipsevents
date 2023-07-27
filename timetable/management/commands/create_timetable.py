# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand, CommandError
from datetime import time
from timetable.models import Session
from booking.models import EventType, FilterCategory

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

        cat3, _ = FilterCategory.objects.get_or_create(category="Level 3")
        cat1, _ = FilterCategory.objects.get_or_create(category="Level 1")
        catpriv, _ = FilterCategory.objects.get_or_create(category="Private")
        cat2, _ = FilterCategory.objects.get_or_create(category="Level 2")
        cat4, _ = FilterCategory.objects.get_or_create(category="Level 4")
        catall, _ = FilterCategory.objects.get_or_create(category="All levels")

        # hour, min, event_type, max_participants, external_instructor, categories
        # sessions = {
        #     "mon": [
        #         ("Pole Level 3", 17, 45, pc, None, False),
        #         ("Pole Level 1", 19, 0, pc, 15, False),
        #         ("Private (1 or more students)", )

        #     }
        # }

        # Monday classes
        sess, _ = Session.objects.get_or_create(
            name="Pole Level 3",
            day=Session.MON,
            event_type=pc,
            time=time(hour=17, minute=45),
            external_instructor=False,
        )
        sess.categories.add(cat3)
        

        sess, _ = Session.objects.get_or_create(
            name="Pole Level 1",
            day=Session.MON,
            event_type=pc,
            max_participants=15,
            time=time(hour=19, minute=0),
            external_instructor=False,
        )
        sess.categories.add(cat1)

        sess, _ = Session.objects.get_or_create(
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
        sess.categories.add(catpriv)

        # Tuesday classes
        sess, _ = Session.objects.get_or_create(
            name="Pole Level 2",
            day=Session.TUE,
            event_type=pc,
            time=time(hour=17, minute=45),
            external_instructor=False,
        )
        sess.categories.add(cat2)

        sess, _ = Session.objects.get_or_create(
            name="Pole Level 4",
            day=Session.TUE,
            event_type=pc,
            time=time(hour=19, minute=0),
            external_instructor=False,
        )
        sess.categories.add(cat4)

        sess, _ = Session.objects.get_or_create(
            name="Pole Level 1",
            day=Session.TUE,
            event_type=pc,
            max_participants=15,
            time=time(hour=20, minute=10),
            external_instructor=False,
        )
        sess.categories.add(cat1)

        # Thursday classes
        sess, _ = Session.objects.get_or_create(
            name="Mixed Pole Levels",
            day=Session.THU,
            event_type=pc,
            time=time(hour=11, minute=0),
            external_instructor=False,
        )
        sess.categories.add(catall)

        sess, _ = Session.objects.get_or_create(
            name="Pole Level 1",
            day=Session.THU,
            event_type=pc,
            max_participants=15,
            time=time(hour=17, minute=45),
            external_instructor=False,
        )
        sess.categories.add(cat1)

        sess, _ = Session.objects.get_or_create(
            name="Pole Level 2",
            day=Session.THU,
            event_type=pc,
            time=time(hour=20, minute=10),
            external_instructor=False,
        )
        sess.categories.add(cat2)

        # Friday classes
        sess, _ = Session.objects.get_or_create(
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

        sess, _ = Session.objects.get_or_create(
            name="Pole Level 4",
            day=Session.FRI,
            event_type=pc,
            time=time(hour=17, minute=45),
            max_participants=15,
            external_instructor=False,
        )

        sess, _ = Session.objects.get_or_create(
            name="Pole Level 3",
            day=Session.FRI,
            event_type=pc,
            time=time(hour=19, minute=0),
            external_instructor=False,
        )

        sess, _ = Session.objects.get_or_create(
            name="Pole practice",
            day=Session.FRI,
            event_type=pp,
            time=time(hour=20, minute=10),
            max_participants=15,
            cost=3.50,
            external_instructor=False,
        )

        # SUN CLASSES
        sess, _ = Session.objects.get_or_create(
            name="Pole practice",
            day=Session.SUN,
            event_type=pp,
            time=time(hour=17, minute=45),
            max_participants=15,
            cost=3.50,
            external_instructor=False,
        )
