import logging

from django.utils import timezone
from datetime import time, timedelta, datetime, date
from booking.models import Event
from timetable.models import Session


logger = logging.getLogger(__name__)


def create_classes(week='this', input_date=None):
    """
    Creates a week's classes (mon-sun) from any given date.  Will create classes
    in the past if the date given is after Monday and week is "this".
    If no date is given, creates classes for the current week, or the next week.
    """
    if not input_date:
        input_date = date.today()
    if week == 'next':
        input_date = input_date + timedelta(7)

    mon = input_date - timedelta(days=input_date.weekday())
    tues = mon + timedelta(days=1)
    wed = mon + timedelta(days=2)
    thurs = mon + timedelta(days=3)
    fri = mon + timedelta(days=4)
    sat = mon + timedelta(days=5)
    sun = mon + timedelta(days=6)

    date_dict = {
        '01MON': mon,
        '02TUE': tues,
        '03WED': wed,
        '04THU': thurs,
        '05FRI': fri,
        '06SAT': sat,
        '07SUN': sun}

    timetable = Session.objects.all()

    created_classes = []
    existing_classes = []

    for session in timetable:
        cl, created = Event.objects.get_or_create(
            name=session.name,
            event_type=session.event_type,
            date=(datetime.combine(
                date_dict[session.day],
                session.time).replace(tzinfo=timezone.utc)),
            description=session.description,
            max_participants=session.max_participants,
            location=session.location,
            contact_person=session.contact_person,
            contact_email=session.contact_email,
            cost=session.cost,
            payment_open=session.payment_open,
            advance_payment_required=True,
            booking_open=session.booking_open,
            payment_info=session.payment_info,
            cancellation_period=session.cancellation_period,
            external_instructor = session.external_instructor,
        )
        if created:
            created_classes.append(cl)
        else:
            existing_classes.append(cl)

    if created_classes:
        logger.info('Classes created from timetable for week beginning {}'.format(
            mon.strftime('%A %d %B %Y')
        ))
    return created_classes, existing_classes


def upload_timetable(start_date, end_date):

    daylist = [
        '01MON',
        '02TUE',
        '03WED',
        '04THU',
        '05FRI',
        '06SAT',
        '07SUN'
        ]

    created_classes = []
    existing_classes = []

    d = start_date
    delta = timedelta(days=1)
    while d <= end_date:
        sessions_to_create = Session.objects.filter(day=daylist[d.weekday()])
        for session in sessions_to_create:
            cl, created = Event.objects.get_or_create(
                name=session.name,
                event_type=session.event_type,
                date=(datetime.combine(d,
                    session.time).replace(tzinfo=timezone.utc)),
                description=session.description,
                max_participants=session.max_participants,
                location=session.location,
                contact_person=session.contact_person,
                contact_email=session.contact_email,
                cost=session.cost,
                payment_open=session.payment_open,
                advance_payment_required=True,
                booking_open=session.booking_open,
                payment_info=session.payment_info,
                cancellation_period=session.cancellation_period,
                external_instructor = session.external_instructor,
            )
            if created:
                created_classes.append(cl)
            else:
                existing_classes.append(cl)
        d += delta

    if created_classes:
        logger.info('Classes uploaded from timetable for {} to {}'.format(
            start_date.strftime('%a %d %B %Y'), end_date.strftime('%a %d %B %Y')
        ))

    return created_classes, existing_classes
