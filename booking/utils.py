from django.utils import timezone
from datetime import time, timedelta, datetime, date
from booking.models import Event

def create_classes(week='this'):

        today = date.today()
        if week == 'next':
            today = date.today() + timedelta(7)

        mon = today - timedelta(days=today.weekday())
        tues = mon + timedelta(days=1)
        wed = mon + timedelta(days=2)
        thurs = mon + timedelta(days=3)
        fri = mon + timedelta(days=4)
        sat = mon + timedelta(days=5)
        sun = mon + timedelta(days=6)

        # Monday classes
        Event.objects.get_or_create(
            name="Pole Level 3",
            type=Event.POLE_CLASS,
            date=datetime.combine(mon, time(hour=17, minute=45, tzinfo=timezone.utc)),
            max_participants=15,
            cost=7,
            payment_open=True,
            advance_payment_required=False,
        )

        Event.objects.get_or_create(
            name="Pole Level 1",
            type=Event.POLE_CLASS,
            date=datetime.combine(mon, time(hour=19, minute=0, tzinfo=timezone.utc)),
            max_participants=15,
            cost=7,
            payment_open=True,
            advance_payment_required=False,
        )

        Event.objects.get_or_create(
            name="Pole practice",
            type=Event.OTHER_CLASS,
            date=datetime.combine(mon, time(hour=20, minute=10, tzinfo=timezone.utc)),
            max_participants=15,
            cost=3.50,
            payment_open=True,
            advance_payment_required=False,
        )

        # Tuesday classes
        Event.objects.get_or_create(
            name="Pole Level 2",
            type=Event.POLE_CLASS,
            date=datetime.combine(tues, time(hour=17, minute=45, tzinfo=timezone.utc)),
            max_participants=15,
            cost=7,
            payment_open=True,
            advance_payment_required=False,
        )

        Event.objects.get_or_create(
            name="Pole Level 4",
            type=Event.POLE_CLASS,
            date=datetime.combine(tues, time(hour=19, minute=0, tzinfo=timezone.utc)),
            max_participants=15,
            cost=7,
            payment_open=True,
            advance_payment_required=False,
        )

        Event.objects.get_or_create(
            name="Pole Level 1",
            type=Event.POLE_CLASS,
            date=datetime.combine(tues, time(hour=20, minute=10, tzinfo=timezone.utc)),
            max_participants=15,
            cost=7,
            payment_open=True,
            advance_payment_required=False,
        )

        # Wednesday classes
        Event.objects.get_or_create(
            name="Pole conditioning",
            type=Event.OTHER_CLASS,
            date=datetime.combine(wed, time(hour=19, minute=0, tzinfo=timezone.utc)),
            max_participants=15,
            cost=3.50,
            payment_open=True,
            advance_payment_required=False,
        )

        # Thursday classes
        Event.objects.get_or_create(
            name="Pole Mixed Levels",
            type=Event.POLE_CLASS,
            date=datetime.combine(thurs, time(hour=11, minute=0, tzinfo=timezone.utc)),
            max_participants=15,
            cost=7,
            payment_open=True,
            advance_payment_required=False,
        )

        Event.objects.get_or_create(
            name="Pole Level 2",
            type=Event.POLE_CLASS,
            date=datetime.combine(thurs, time(hour=20, minute=10, tzinfo=timezone.utc)),
            max_participants=15,
            cost=7,
            payment_open=True,
            advance_payment_required=False,
        )

        # Friday classes
        Event.objects.get_or_create(
            name="Pole Level 1",
            type=Event.POLE_CLASS,
            date=datetime.combine(fri, time(hour=17, minute=45, tzinfo=timezone.utc)),
            max_participants=15,
            cost=7,
            payment_open=True,
            advance_payment_required=False,
        )

        Event.objects.get_or_create(
            name="Pole Level 3",
            type=Event.POLE_CLASS,
            date=datetime.combine(fri, time(hour=19, minute=0, tzinfo=timezone.utc)),
            max_participants=15,
            cost=7,
            payment_open=True,
            advance_payment_required=False,
        )

        Event.objects.get_or_create(
            name="Pole practice",
            type=Event.OTHER_CLASS,
            date=datetime.combine(fri, time(hour=20, minute=10, tzinfo=timezone.utc)),
            max_participants=15,
            cost=3.50,
            payment_open=True,
            advance_payment_required=False,
        )