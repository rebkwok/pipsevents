import pytz

from django import template

from booking.models import Booking

register = template.Library()

HOURS_CONVERSION = {
    'weeks': 7 * 24,
    'days': 24,
}


@register.filter
def format_cancellation(value):
    """
    Convert cancellation period in hours into formatted text
    """
    weeks = value // HOURS_CONVERSION['weeks']
    weeks_remainder = value % HOURS_CONVERSION['weeks']
    days = weeks_remainder // HOURS_CONVERSION['days']
    hours = weeks_remainder % HOURS_CONVERSION['days']

    if value <= 24:
        return "{} hour{}".format(value, plural_format(value))
    elif weeks == 0 and hours == 0:
        return "{} day{}".format(days, plural_format(days))
    elif days == 0 and hours == 0:
        return "{} week{}".format(weeks, plural_format(weeks))
    else:
        return "{} week{}, {} day{} and {} hour{}".format(
            weeks,
            plural_format(weeks),
            days,
            plural_format(days),
            hours,
            plural_format(hours)
        )


def plural_format(value):
    if value > 1 or value == 0:
        return "s"
    else:
        return ""


@register.filter
def get_range(value):
    return range(value)


@register.filter
def get_index_open(event, extraline_index):
    spaces_left = event.spaces_left()
    open_bookings = [booking for booking in event.bookings.all() if booking.status=='OPEN']
    return len(open_bookings) + 1 + extraline_index

@register.filter
def get_index_all(event, extraline_index):
    spaces_left = event.spaces_left()
    return event.bookings.count() + 1 + extraline_index

@register.filter
def bookings_count(event):
    return len(Booking.objects.filter(event=event, status='OPEN'))

@register.filter
def format_datetime(date):
    date = date.value()
    return date.strftime("%d %b %Y %H:%M")

@register.filter
def format_field_name(field):
    return field.replace('_', ' ').title()

@register.filter
def formatted_uk_date(date):
    """
    return UTC date in uk time
    """
    uk=pytz.timezone('Europe/London')
    return date.astimezone(uk).strftime("%d %b %Y %H:%M")

@register.filter
def is_regular_student(user):
    return user.has_perm('booking.is_regular_student')