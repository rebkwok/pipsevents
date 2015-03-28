from django import template
from booking.models import Event


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
    # import ipdb; ipdb.set_trace()
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
        return "{} week{}, {} day{} and {} hour{}".format(weeks,
                                                       plural_format(weeks),
                                                       days,
                                                       plural_format(days),
                                                       hours,
                                                       plural_format(hours))

def plural_format(value):
    if value > 1 or value == 0:
        return "s"
    else:
        return ""