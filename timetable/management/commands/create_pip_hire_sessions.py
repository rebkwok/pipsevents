# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import time
from timetable.models import Session
from booking.models import EventType


class Command(BaseCommand):

    def handle(self, *args, **options):

        """
        Create the pip room hire timetable sessions
        """
        self.stdout.write('Creating timetable sessions for pip room hire.')

        rh, _ = EventType.objects.get_or_create(
            event_type='RH', subtype='Studio/room hire'
        )

        name = 'Pip Room Hire'
        description = '<p>Small studio hire with pole</p><hr />' \
                      '<p>Studio hire form to be signed on arrival.&nbsp;</p>'
        cost = 12
        payment_info = "<p>&pound;5 added per any additional person. Enquire " \
                       "for invoice when booking for more than one " \
                       "person.&nbsp;</p>"
        external_instructor = False
        max_participants = 1

        sessions_to_add = [
            (Session.MON, time(hour=19, minute=0)),
            (Session.MON, time(hour=20, minute=10)),
            (Session.TUE, time(hour=19, minute=0)),
            (Session.TUE, time(hour=20, minute=10)),
            (Session.THU, time(hour=19, minute=0)),
            (Session.THU, time(hour=20, minute=10)),
            (Session.FRI, time(hour=19, minute=0)),
            (Session.FRI, time(hour=20, minute=10)),
        ]

        new = []
        existing = []

        for session in sessions_to_add:
            new_session, created = Session.objects.get_or_create(
                event_type=rh,
                name=name,
                description=description,
                cost=cost,
                payment_info=payment_info,
                day=session[0],
                time=session[1],
                external_instructor=external_instructor,
                max_participants=max_participants
            )
            if created:
                new.append(new_session)
            else:
                existing.append(new_session)

        if new:
            self.stdout.write(
                'Pip room hire timetable sessions created for {}.'.format(
                    ', '.join(["{} {}".format(s.day, s.time) for s in new])
                ))
        else:
            self.stdout.write('No new pip room hire sessions created.')

        if existing:
            self.stdout.write(
                'Pip room hire timetable sessions existed already '
                'for {}.'.format(
                    ', '.join(["{} {}".format(s.day, s.time) for s in existing])
                ))
