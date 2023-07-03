import os
import pytz

from datetime import datetime
from datetime import timezone as dt_timezone

from decimal import Decimal
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.models import Group
from django import template
from django.utils import timezone
from django.utils.safestring import mark_safe

from accounts.models import OnlineDisclaimer, has_active_disclaimer, \
    has_active_online_disclaimer, has_expired_disclaimer
from booking.models import BlockVoucher, Booking, Event, EventVoucher, \
    UsedBlockVoucher, UsedEventVoucher
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
def get_range(value, start=0):
    # start: 0 or 1
    return range(start, value + start)


@register.simple_tag(takes_context=True)
def get_pagination_params(context, page_type=None):
    params = {}
    if page_type == "events":
        location_obj = context.get("location_obj")
        if location_obj:
            params["tab"] = location_obj["index"]
        for req_param in ["name", "date_selection", "spaces_only"]:
            if req_param in context["request"].GET:
                params[req_param] = context["request"].GET[req_param]
    elif page_type == "admin_events":
        if "show_past" in context:
            params["past"] = True
    elif page_type == "admin_blocks":
        if "block_status" in context:
            params["block_status"] = context["block_status"]
    elif page_type == "attendance":
        form = context["form"]
        params["start_date"] = form.start_date.value
        params["end_date"] = form.end_date.value
    elif page_type == "activitylog":
        for req_param in ["hide_empty_cronjobs", "search", "search_date", "search_submitted"]:
            if req_param in context["request"].GET:
                params[req_param] = context["request"].GET[req_param]

    if params:
        return f"&{urlencode(params)}"
    return ""

@register.filter
def get_index_open(event, extraline_index):
    open_bookings = [
        booking for booking in event.bookings.all() if booking.status == 'OPEN'
        ]
    return len(open_bookings) + 1 + extraline_index


@register.filter
def bookings_count(event):
    return Booking.objects.select_related('event', 'event__type', 'user').filter(
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


@register.inclusion_tag('booking/banner.html')
def temporary_banner():
    now = timezone.now()
    banner = os.environ.get('TEMP_BANNER')
    banner_start = os.environ.get('BANNER_START')
    banner_end = os.environ.get('BANNER_END')

    if banner_start and banner_end:
        banner_start = datetime.strptime(banner_start, '%d-%b-%Y').replace(
            tzinfo=dt_timezone.utc
        )
        banner_end = datetime.strptime(banner_end, '%d-%b-%Y').replace(
            hour=23, minute=59, tzinfo=dt_timezone.utc
        )
        if now > banner_start and now < banner_end:
            return {
                'has_temporary_banner': True,
                'temporary_banner': banner,
            }
    return {'has_temporary_banner': False}


@register.inclusion_tag('booking/sale.html')
def sale_text():
    now = timezone.now()
    sale_title = os.environ.get('SALE_TITLE')
    sale_start = os.environ.get('SALE_ON')
    sale_end = os.environ.get('SALE_OFF')
    sale_code = os.environ.get('SALE_CODE')
    sale_description = os.environ.get('SALE_DESCRIPTION')

    active_sale_code = None

    if sale_code:
        try:
            voucher = EventVoucher.objects.get(code=sale_code)
            if voucher.has_started and not voucher.has_expired:
                active_sale_code = sale_code
        except EventVoucher.DoesNotExist:
            try:
                voucher = BlockVoucher.objects.get(code=sale_code)
                if voucher.has_started and not voucher.has_expired:
                    active_sale_code = sale_code
            except BlockVoucher.DoesNotExist:
                pass

    if sale_start and sale_end:
        sale_start = datetime.strptime(sale_start, '%d-%b-%Y').replace(
            tzinfo=dt_timezone.utc
        )
        sale_end = datetime.strptime(sale_end, '%d-%b-%Y').replace(
            hour=23, minute=59, tzinfo=dt_timezone.utc
        )
        if now > sale_start and now < sale_end:
            return {
                'is_sale_period': True,
                'sale_title': sale_title,
                'sale_description': sale_description,
                'sale_start': sale_start,
                'sale_end': sale_end,
                'active_sale_code': active_sale_code,
            }
    return {'is_sale_period': False}


@register.filter(name='in_group')
def in_group(user, group_name):
    group = Group.objects.get(name=group_name)
    return True if group in user.groups.all() else False


@register.filter
def format_block(block):
    return "{} ({}/{} left); exp {}".format(
            block.block_type.event_type.subtype,
            block.block_type.size - block.bookings_made(),
            block.block_type.size,
            block.expiry_date.strftime('%d %b %y')
        )


@register.filter
def has_online_disclaimer(user):
    return has_active_online_disclaimer(user)


@register.filter
def expired_disclaimer(user):
    return has_expired_disclaimer(user)


@register.filter
def has_disclaimer(user):
    return has_active_disclaimer(user)


@register.filter
def disclaimer_medical_info(user):
    disclaimer = OnlineDisclaimer.objects.select_related('user')\
        .filter(user=user).latest('id')
    return disclaimer.medical_conditions \
        or disclaimer.joint_problems \
        or disclaimer.allergies


@register.simple_tag
def get_verbose_field_name(instance, field_name):
    return instance._meta.get_field(field_name).verbose_name.title()


@register.filter
def encode(val):
    return int_str(chaffify(val))


@register.filter
def format_event_types(ev_types):
    return mark_safe(''.join(
        ['{}<br/>'.format(ev_type.subtype) for ev_type in ev_types]
    ))


@register.filter
def times_voucher_used(voucher):
    return UsedEventVoucher.objects.filter(voucher=voucher).count()


@register.filter
def times_block_voucher_used(voucher):
    return UsedBlockVoucher.objects.filter(voucher=voucher).count()


@register.filter
def subscribed(user):
    group, _ = Group.objects.get_or_create(name='subscribed')
    return group in user.groups.all()


@register.filter
def has_booked_class(user):
    return any(Booking.objects.select_related('user', 'event').filter(
        user=user, event__event_type__event_type='CL'
    ))


@register.filter
def format_block_type_id_user(block):
    if block.block_type.identifier \
            and block.block_type.identifier == 'free class':
        return '(free class)'
    elif block.block_type.identifier \
            and block.block_type.identifier == 'transferred':
        try:
            booking = Booking.objects.get(id=block.transferred_booking_id)
            return '(transferred from {} {})'.format(
                booking.event.name, booking.event.date.strftime('%d%b%y')
            )
        except Booking.DoesNotExist:
            return '(transferred)'
    return ''


@register.filter
def format_block_type_identifier(value):
    if value:
        if value.startswith('transferred'):
            return '(transfer)'
        return '({})'.format(value)
    return ''


@register.filter
def format_paid_status(booking):
    if booking.free_class:
        return mark_safe('<span class="confirmed">Free class</span>')
    elif booking.block and booking.block.block_type.identifier and \
            booking.block.block_type.identifier.startswith('transferred'):
        return mark_safe('<span class="confirmed">Transferred</span>')
    elif booking.event.cost and booking.paid:
        return mark_safe('<span class="confirmed fa fa-check"></span>')
    elif booking.event.cost and not booking.paid:
        if booking.paypal_pending:
            return mark_safe('<span class="not-confirmed">PayPal pending</span>')
        return mark_safe('<span class="not-confirmed fa fa-times"></span>')
    else:
        return mark_safe('<strong>N/A</strong>')


@register.filter
def transferred_from(block):
    if block.transferred_booking_id:
        try:
            bk = Booking.objects.get(id=block.transferred_booking_id)
            return '{} {} ({})'.format(
                bk.event.name, bk.event.date.strftime('%d%b%y'),
                block.transferred_booking_id
            )
        except Booking.DoesNotExist:
            return '({})'.format(block.transferred_booking_id)
    return ''


@register.simple_tag
def check_debug():
    return settings.DEBUG


@register.simple_tag
def voucher_expired(voucher):
    # voucher has expired if expiry date passed or has been used max times
    if voucher.expiry_date and voucher.expiry_date < timezone.now():
        return True
    elif voucher.max_vouchers:
        if isinstance(voucher, EventVoucher):
            times_used = UsedEventVoucher.objects.filter(voucher=voucher)\
                .count()
        else:
            times_used = UsedBlockVoucher.objects.filter(voucher=voucher)\
                .count()

        if times_used and times_used >= voucher.max_vouchers:
            return True

    return False


@register.simple_tag
def get_booking(event, user, user_bookings):
    # user_bookings is a dict of booking info by event_id
    if user.is_authenticated:
        return user_bookings.get(event.id)
        # return user_bookings.get(event.id)
        # return Booking.objects.filter(event=event, user=user).first()
    return None


@register.filter
def full_location(location):
    locations = dict(Event.LOCATION_CHOICES)
    return locations[location]


def get_shopping_basket_icon(user, menu=False):
    bookings = user.bookings.select_related('event').filter(
        paid=False, status='OPEN', event__date__gte=timezone.now(), no_show=False, paypal_pending=False
    )
    blocks = [
        block for block in user.blocks.filter(expiry_date__gte=timezone.now(), paid=False, paypal_pending=False) if not block.full
    ]
    return {
        'has_unpaid_bookings': any(bookings),
        'count': bookings.count() + len(blocks),
        'menu': menu
    }


@register.simple_tag
def has_shopping_basket_items(user):
    return get_shopping_basket_icon(user)['has_unpaid_bookings']


@register.inclusion_tag('booking/includes/shopping_basket_icon.html')
def show_shopping_basket_menu(user):
    return get_shopping_basket_icon(user, menu=True)


@register.filter
def voucher_applied_cost(cost, discount):
    return Decimal(float(cost) * ((100 - discount) / 100)).quantize(Decimal('.05'))


def is_active(location_index, tab):
    if tab:
        if str(location_index) == tab:
            return True
    return False


@register.filter
def get_active_class(location_index, tab):
    return 'active' if is_active(location_index, tab) else ''


@register.filter
def get_active_in_class(location_index, tab):
    return 'show active' if is_active(location_index, tab) else ''


@register.filter
def reset_url(event_type):
    return f"booking:{event_type}"


@register.filter
def format_status(booking):
    if booking.instructor_confirmed_no_show:
        return "No-show"
    elif booking.no_show:
        return "Late cancellation"
    else:
        return booking.status.title()
