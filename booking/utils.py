import logging
import pytz
import time

from django.utils import timezone
from datetime import timedelta, datetime, date
from booking.models import Event
from timetable.models import Session
from activitylog.models import ActivityLog


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

        # create date in Europe/London, convert to UTC
        localtz = pytz.timezone('Europe/London')
        local_date = localtz.localize(
            datetime.combine(date_dict[session.day], session.time)
        )
        converted_date = local_date.astimezone(pytz.utc)

        cl, created = Event.objects.get_or_create(
            name=session.name,
            event_type=session.event_type,
            date=converted_date,
            description=session.description,
            max_participants=session.max_participants,
            location=session.location,
            contact_person=session.contact_person,
            contact_email=session.contact_email,
            cost=session.cost,
            payment_open=session.payment_open,
            advance_payment_required=session.advance_payment_required,
            booking_open=session.booking_open,
            payment_info=session.payment_info,
            cancellation_period=session.cancellation_period,
            external_instructor = session.external_instructor,
            email_studio_when_booked = session.email_studio_when_booked
            )
        if created:
            created_classes.append(cl)
        else:
            existing_classes.append(cl)

    if created_classes:
        ActivityLog.objects.create(
            log='Classes created from timetable for week beginning {}'.format(
                mon.strftime('%A %d %B %Y')
            )
        )
    return created_classes, existing_classes


def upload_timetable(start_date, end_date, user=None):

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

            # create date in Europe/London, convert to UTC
            localtz = pytz.timezone('Europe/London')
            local_date = localtz.localize(datetime.combine(d,
                session.time))
            converted_date = local_date.astimezone(pytz.utc)

            cl, created = Event.objects.get_or_create(
                name=session.name,
                event_type=session.event_type,
                date=converted_date,
                location=session.location
            )
            if created:
                cl.description=session.description
                cl.max_participants=session.max_participants
                cl.contact_person=session.contact_person
                cl.contact_email=session.contact_email
                cl.cost=session.cost
                cl.payment_open=session.payment_open
                cl.advance_payment_required=session.advance_payment_required
                cl.booking_open=session.booking_open
                cl.payment_info=session.payment_info
                cl.cancellation_period=session.cancellation_period
                cl.external_instructor = session.external_instructor
                cl.email_studio_when_booked = session.email_studio_when_booked
                cl.save()

                created_classes.append(cl)
            else:
                existing_classes.append(cl)
        d += delta

    if created_classes:
        ActivityLog.objects.create(
            log='Classes uploaded from timetable for {} to {} {}'.format(
                start_date.strftime('%a %d %B %Y'),
                end_date.strftime('%a %d %B %Y'),
                'by admin user {}'.format(user.username) if user else ''
            )
        )

    return created_classes, existing_classes
