import os
import pytz

from datetime import datetime

from django.contrib.auth.models import Group
from django import template
from django.utils import timezone
from django.utils.safestring import mark_safe

from accounts.models import OnlineDisclaimer, PrintDisclaimer

from booking.models import Booking

from studioadmin.utils import int_str, chaffify


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
    open_bookings = [
        booking for booking in event.bookings.all() if booking.status == 'OPEN'
        ]
    return len(open_bookings) + 1 + extraline_index


@register.filter
def bookings_count(event):
    return Booking.objects.filter(
        event=event, status='OPEN', no_show=False
    ).count()


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


@register.filter
def total_ticket_cost(ticket_booking):
    num_tickets = ticket_booking.tickets.count()
    return ticket_booking.ticketed_event.ticket_cost * num_tickets


@register.filter
def abbr_ref(ref):
    return "{}...".format(ref[:5])

@register.filter
def abbr_username(user):
    if len(user) > 15:
        return mark_safe("{}-</br>{}".format(user[:12], user[12:]))
    return user

@register.filter
def abbr_name(name):
    if len(name) > 8 and '-' in name:
        split_name = name.split('-')
        return mark_safe(
            "{}-</br>{}".format(split_name[0], '-'.join(split_name[1:]))
        )
    if len(name) > 12:
        return mark_safe("{}-</br>{}".format(name[:8], name[8:]))
    return name

@register.filter
def abbr_email(email):
    if len(email) > 25:
        return "{}...".format(email[:22])
    return email

@register.inclusion_tag('booking/sale.html')
def sale_text():
    now = timezone.now()
    sale_start = os.environ.get('SALE_ON')
    sale_end = os.environ.get('SALE_OFF')
    if sale_start and sale_end:
        sale_start = datetime.strptime(sale_start, '%d-%b-%Y').replace(
            tzinfo=timezone.utc
        )
        sale_end = datetime.strptime(sale_end, '%d-%b-%Y').replace(
            hour=23, minute=59, tzinfo=timezone.utc
        )
        if now > sale_start and now < sale_end:
            return {
                'is_sale_period': True,
                'sale_start': sale_start,
                'sale_end': sale_end
            }
    return {'is_sale_period': False}


@register.filter(name='in_group')
def in_group(user, group_name):
    group = Group.objects.get(name=group_name)
    return True if group in user.groups.all() else False

@register.filter
def format_block(block):
    return "{} ({}/{} left); expires {}".format(
            block.block_type.event_type.subtype,
            block.block_type.size - block.bookings_made(),
            block.block_type.size,
            block.expiry_date.strftime('%d %b %y')
        )


@register.filter
def has_print_disclaimer(user):
    disclaimer = PrintDisclaimer.objects.filter(user=user)
    return bool(disclaimer)


@register.filter
def has_online_disclaimer(user):
    disclaimer = OnlineDisclaimer.objects.filter(user=user)
    return bool(disclaimer)


@register.filter
def has_disclaimer(user):
    return has_online_disclaimer(user) or has_print_disclaimer(user)


@register.simple_tag
def get_verbose_field_name(instance, field_name):
    return instance._meta.get_field(field_name).verbose_name.title()


@register.filter
def encode(val):
    return int_str(chaffify(val))


@register.filter
def format_event_types(ev_types):
    return ', '.join([ev_type.subtype for ev_type in ev_types])


@register.filter
def subscribed(user):
    group, _ = Group.objects.get_or_create(name='subscribed')
    return group in user.groups.all()

@register.filter
def has_booked_class(user):
    return Booking.objects.filter(
        user=user, event__event_type__event_type='CL'
    ).exists()