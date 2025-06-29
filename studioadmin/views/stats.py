import calendar
import logging
from collections import Counter
from datetime import datetime, UTC

from dateutil.relativedelta import relativedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import Count, F,Func, IntegerField, Value, Q
from django.db.models.functions import ExtractYear, ExtractMonth, TruncMonth, TruncYear
from django.http import JsonResponse
from django.template.response import TemplateResponse

from accounts.models import OnlineDisclaimer, DisclaimerContent
from booking.models import Event, EventType, Booking, Membership, UserMembership, WaitingListUser
from studioadmin.views.helpers import StaffUserMixin, staff_required, is_instructor_or_staff


logger = logging.getLogger(__name__)

colourPalette = ["#55efc4", "#81ecec", "#a29bfe", "#ffeaa7", "#fab1a0", "#ff7675", "#fd79a8"]
colourPrimary, colourSecondary, colourDanger = "#79aec8", colourPalette[0], colourPalette[5]

background_colours = [
    'rgba(255, 99, 132, 0.4)',
    'rgba(255, 159, 64, 0.4)',
    'rgba(255, 205, 86, 0.4)',
    'rgba(75, 192, 192, 0.4)',
    'rgba(54, 162, 235, 0.4)',
    'rgba(153, 102, 255, 0.4)',
    'rgba(201, 203, 207, 0.4)',
    'rgba(245, 40, 145, 0.4)',
    'rgba(172, 245, 49, 0.4)',
    'rgba(14, 18, 186, 0.4)',
    'rgba(9, 246, 201, 0.4)',
]
border_colours = [
    'rgb(255, 99, 132)',
    'rgb(255, 159, 64)',
    'rgb(255, 205, 86)',
    'rgb(75, 192, 192)',
    'rgb(54, 162, 235)',
    'rgb(153, 102, 255)',
    'rgb(201, 203, 207)',
    'rgb(245, 40, 145)',
    'rgb(172, 245, 49)',
    'rgb(14, 18, 186)',
    'rgb(9, 246, 201)'
]


def get_year_dict():
    return {month: 0 for month in calendar.month_abbr if month}


def get_event_types_dict():
    return {event_type: {} for event_type in EventType.TYPE_VERBOSE_NAME.keys()}


def get_event_types_year_dict():
    return {event_type: get_year_dict() for event_type in EventType.TYPE_VERBOSE_NAME.keys()}


def generate_colour_palette(amount):
    palette = []

    i = 0
    while i < len(background_colours) and len(palette) < amount:
        palette.append((background_colours[i], border_colours[i]))
        i += 1
        if i == len(background_colours) and len(palette) < amount:
            i = 0

    return palette


@login_required
@staff_required
def view_stats(request):
    
    context={
        "sidenav_selection": "stats", 
        "user_count": User.objects.count(),
        "user_membership_count": len(UserMembership.active_member_ids()),
        "booking_count": Booking.objects.filter(event__cancelled=False, status="OPEN", no_show=False).count()
    }
    return TemplateResponse(request, template="studioadmin/stats.html", context=context)


def get_years():
    current_year = datetime.now().year
    cache_key = "stats_years_filter"
    years = cache.get(cache_key)
    if years is None:
        grouped_years = Event.objects.annotate(year=ExtractYear("date")).values("year").order_by("-year").distinct()
        years = [grouped_year["year"] for grouped_year in grouped_years]
        cache.set(cache_key, years)
    elif current_year not in years:
        years = [current_year, *years]
        cache.set(cache_key, years)
    return years


@staff_member_required
def view_filter_options(request):
    return JsonResponse({"options": get_years()})


def months_to_recalculate(now, recalc_future):
    # Recalculate months that might have changed (assuming this is the current year)
    
    # recalculate last month if we're not in the first month; 
    # we haven't calculated this month yet, so we can't be sure last month is up to date
    # If it's Jan, we don't care about last year
    if now.month > 1:
        yield now.month - 1
    # always re-calculate this month
    yield now.month
    # For some calculations we need to include info for future months
    if recalc_future:
        for i in range(now.month + 1, 13):
            yield i


def get_new_user_registrations(year):
    cache_key = (f"stats_new_user_registration_{year}")
    month_dict = cache.get(cache_key)
    now = datetime.now(tz=UTC)

    if month_dict is None:
        logger.info(f"cache miss: {cache_key}")
        month_dict = get_year_dict()
        grouped = (
            User.objects.filter(date_joined__year=year)
            .annotate(month=ExtractMonth("date_joined"))
            .values("month").annotate(count=Count("pk"))
        )
        for group in grouped:
            month_dict[calendar.month_abbr[group["month"]]] = group["count"] 
        cache.set(cache_key, month_dict)
    elif now.year == year:
        logger.info(f"cache hit (this year): {cache_key}")
        users_this_year = User.objects.filter(date_joined__year=year)

        for month in months_to_recalculate(now):
            month_abbr =  calendar.month_abbr[month]
            month_dict[month_abbr] = users_this_year.filter(date_joined__month=month).count()
        cache.set(cache_key, month_dict)
    else:
        logger.info(f"cache hit (this year): {cache_key}")
    return month_dict


@staff_member_required
def view_new_user_registration(request, year):    
    month_dict = get_new_user_registrations(year)
    colours = generate_colour_palette(1)

    return JsonResponse({
        "title": year,
        "data": {
            "labels": list(month_dict.keys()),
            "datasets": [
                {
                    "label": "# new users",
                    "backgroundColor": colours[0][0],
                    "borderColor": colours[0][1],
                    "data": list(month_dict.values()),
                }
            ]
        },
    })


def get_cumulative_user_registrations():
    cache_key = "stats_cumulative_user_registrations"
    yr_month_dict = cache.get(cache_key)
    now = datetime.now(tz=UTC)

    def _calculate_users_to_month_end(year, month_num):
        dt = datetime(year, month_num, calendar.monthrange(year, month_num)[1], tzinfo=UTC)
        return User.objects.filter(date_joined__lte=dt).count()

    if yr_month_dict is not None:
        logger.info(f"cache hit: {cache_key}")
        month_abbr =  calendar.month_abbr[now.month]
        months_to_recalc = [(now.year, now.month)]
        if f"{month_abbr} {now.year}" not in yr_month_dict:
            # also recalculate last month; we haven't calculated this month yet, so we can't be sure
            # last month is up to date
            last_month = now.month - 1
            last_month_year = now.year
            if last_month == 0:
                last_month = 12
                last_month_year -= 1
            months_to_recalc.append((last_month_year, last_month))

        for year, month in months_to_recalc:
            month_abbr = calendar.month_abbr[month]
            yr_month_dict[f"{month_abbr} {year}"] = _calculate_users_to_month_end(year, month)
    else:
        logger.info(f"cache miss: {cache_key}")
        years = User.objects.distinct("date_joined__year").values_list("date_joined__year", flat=True)
        yr_month_dict = {}
        for year in sorted(years):
            for i in range(1, 13):
                yr_month_dict[f"{calendar.month_abbr[i]} {year}"] = _calculate_users_to_month_end(year, i)

    cache.set(cache_key, yr_month_dict)
    return yr_month_dict


@staff_member_required
def view_cumulative_user_registrations(request):    
    yr_month_dict = get_cumulative_user_registrations()
    colours = generate_colour_palette(1)

    return JsonResponse({
        "title": "User registrations",
        "data": {
            "labels": list(yr_month_dict.keys()),
            "datasets": [
                {
                    "label": "# users",
                    "backgroundColor": colours[0][0],
                    "borderColor": colours[0][1],
                    "data": list(yr_month_dict.values()),
                }
            ]
        },
    })


def get_annual_monthly_stats_by_event_type(cache_key, year, calc_fn, extra_filter_kwargs=None, recalc_future=False):
    extra_filter_kwargs = extra_filter_kwargs or {}
    events_filter_kwargs = {
        "cancelled": False,
        "date__year": year,
        **extra_filter_kwargs,
    }

    events_year_dict = cache.get(cache_key)

    now = datetime.now(tz=UTC)

    if events_year_dict is None:
        logger.info("cache miss: %s", cache_key)
        events_year_dict = get_event_types_year_dict()

        events = Event.objects.filter(**events_filter_kwargs)

        for ev_type in EventType.TYPE_VERBOSE_NAME.keys():
            events_by_type = events.filter(event_type__event_type=ev_type)  
            for month in range(1, 13):
                events_year_dict[ev_type][calendar.month_abbr[month]] = calc_fn(events_by_type, month)
        cache.set(cache_key, events_year_dict)
    elif now.year == year:
        logger.info("cache hit (this year): %s", cache_key)
        
        events = Event.objects.filter(**events_filter_kwargs)

        for ev_type in EventType.TYPE_VERBOSE_NAME.keys():
            events_by_type = events.filter(event_type__event_type=ev_type)
            
            for month in months_to_recalculate(now, recalc_future):
                events_year_dict[ev_type][calendar.month_abbr[month]] = calc_fn(events_by_type, month)
        cache.set(cache_key, events_year_dict)
    else:
        logger.info("cache hit (previous year): %s", cache_key)
    
    return events_year_dict


def json_response_annual_stats_by_event_type(year, events_year_dict):
    colours = generate_colour_palette(4)
    return JsonResponse({
        "title": year,
        "data": {
            "labels": list(events_year_dict["CL"].keys()),
            "datasets": [
                {
                    "label": "Classes",
                    "backgroundColor": colours[0][0],
                    "borderColor": colours[0][1],
                    "data": list(events_year_dict["CL"].values()),
                },
                {
                    "label": "Events/Workshops",
                    "backgroundColor": colours[1][0],
                    "borderColor": colours[1][1],
                    "data": list(events_year_dict["EV"].values()),
                },
                {
                    "label": "Room Hire",
                    "backgroundColor": colours[2][0],
                    "borderColor": colours[2][1],
                    "data": list(events_year_dict["RH"].values()),
                },
                {
                    "label": "Online Tutorials",
                    "backgroundColor": colours[3][0],
                    "borderColor": colours[3][1],
                    "data": list(events_year_dict["OT"].values()),
                }

            ]
        },
    })


def get_bookings_count_for_month(all_events, month):
    events_for_month = all_events.filter(date__month=month).values_list("id", flat=True)
    return Booking.objects.filter(event_id__in=events_for_month, status="OPEN", paid=True).count()


@staff_member_required
def view_bookings_count(request, year):
    cache_key = f"stats_bookings_count_{year}"   
    events_year_dict = get_annual_monthly_stats_by_event_type(cache_key, year, get_bookings_count_for_month, recalc_future=True)
    return json_response_annual_stats_by_event_type(year, events_year_dict)


def get_events_count_for_month(all_events, month):
    return all_events.filter(date__month=month).count()


@staff_member_required
def view_events_count(request, year):
    cache_key = f"stats_events_count_{year}"
    events_year_dict = get_annual_monthly_stats_by_event_type(cache_key, year, get_events_count_for_month, recalc_future=True)
    return json_response_annual_stats_by_event_type(year, events_year_dict)


def get_pct_waiting_list_for_month(all_events, month):
    events_for_month = all_events.filter(date__month=month)
    total_events_for_month = events_for_month.count()
    waiting_lists = WaitingListUser.objects.filter(event__in=events_for_month).distinct("event_id").count()
    if events_for_month:
        return (waiting_lists / total_events_for_month) * 100
    return 0


@staff_member_required
def view_pct_events_with_waiting_list(request, year):
    """
    (events with waiting list / total events) * 100; average per week/month
    Accept start/end date and units (week/month)
    """

    cache_key = f"stats_pct_events_with_waiting_list_{year}"
    events_year_dict = get_annual_monthly_stats_by_event_type(
        cache_key, year, get_pct_waiting_list_for_month, extra_filter_kwargs={"max_participants__isnull": False},
        recalc_future=True
    )
    return json_response_annual_stats_by_event_type(year, events_year_dict)


def get_bookings_ratio_for_month(all_events, month):
    events_for_month = all_events.filter(date__month=month)
    total_events_for_month = events_for_month.count()
    ratios = [
        event.bookings.filter(status="OPEN", paid=True, no_show=False).count() / event.max_participants
        for event in events_for_month
    ]
    if events_for_month:
        return (sum(ratios) / total_events_for_month) * 100
    return 0


@staff_member_required
def view_pct_bookings_per_class(request, year):
    """
    (bookings / max) * 100; average per week/month
    Accept start/end date and units (week/month)
    """
    cache_key = (f"stats_pct_bookings_per_class_{year}")
    events_year_dict = get_annual_monthly_stats_by_event_type(
        cache_key, year, get_bookings_ratio_for_month, extra_filter_kwargs={"max_participants__isnull": False},
        recalc_future=True
    )
    return json_response_annual_stats_by_event_type(year, events_year_dict)


def get_avg_no_shows_per_class_for_month(all_events, month):
    events_for_month = all_events.filter(date__month=month)
    no_shows = [
        event.bookings.filter(status="OPEN", paid=True, no_show=True, instructor_confirmed_no_show=True).count()
        for event in events_for_month
    ]
    if events_for_month:
        return sum(no_shows) / len(no_shows)
    return 0


@staff_member_required
def view_average_no_show_per_class(request, year):
    """
    instructor_confirmed_no_show; average per week/month
    Accept start/end date and units (week/month)
    """
    cache_key = (f"stats_pct_bookings_per_class_{year}")
    events_year_dict = get_annual_monthly_stats_by_event_type(
        cache_key, year, get_avg_no_shows_per_class_for_month
    )
    
    return json_response_annual_stats_by_event_type(year, events_year_dict)


def get_avg_late_cancellation_per_class_for_month(all_events, month):
    events_for_month = all_events.filter(date__month=month)
    late_cancellations = [
        event.bookings.filter(status="OPEN", paid=True, no_show=True, instructor_confirmed_no_show=False).count()
        for event in events_for_month
    ]
    if events_for_month:
        return sum(late_cancellations) / len(late_cancellations)
    return 0


@staff_member_required
def view_average_late_cancellation_per_class(request, year):
    """
    no shows with instructor_confirmed_no_show=False; average per week/month
    Accept start/end date and units (week/month)
    """
    cache_key = (f"stats_pct_bookings_per_class_{year}")
    events_year_dict = cache.get(cache_key)
    events_year_dict = get_annual_monthly_stats_by_event_type(
        cache_key, year, get_avg_late_cancellation_per_class_for_month
    )
    
    return json_response_annual_stats_by_event_type(year, events_year_dict)


def get_annual_payment_methods(year, event_types):
    cache_key = f"stats_payment_methods_{year}_{event_types}"
    data = cache.get(cache_key)
    
    event_types = [et.upper() for et in event_types.split("-")]

    if data is None or year == datetime.now().year:
        logger.info(f"cache miss: {cache_key}")
        paid_bookings = Booking.objects.filter(event__event_type__event_type__in=event_types, event__date__year=year, paid=True)
        block = paid_bookings.filter(block__isnull=False).count()
        membership = paid_bookings.filter(membership__isnull=False).count()
        # stripe
        stripe = paid_bookings.filter(invoice__paid=True).count()
        paypal = paid_bookings.filter(paypalbookingtransaction__transaction_id__isnull=False).count()
        data = {
            "block": block,
            "membership": membership,
            "stripe": stripe,
            "paypal": paypal,
            "other": paid_bookings.count() - block - membership - stripe - paypal
        }
        cache.set(cache_key, data)
    return data


@staff_member_required
def view_payment_methods(request, year, event_types):
    data = get_annual_payment_methods(year, event_types)
    colours = generate_colour_palette(5)

    return JsonResponse({
        "title": year,
        "data": {
            "labels": list(data.keys()),
            "datasets": [
                {
                    "label": "Payment method",
                    "backgroundColor": [colour[0] for colour in colours],
                    "borderColor": [colour[1] for colour in colours],
                    "data": list(data.values()),
                }
            ]
        },
    })


def get_active_memberships_by_type():
    ums = UserMembership.active_memberships()
    memberships = Membership.objects.filter(user_memberships__in=ums).annotate(count=Count("user_memberships"))
    return {
        membership.name: membership.count for membership in memberships
    }


@staff_member_required
def view_memberships_types(request):
    data = get_active_memberships_by_type()
    colours = generate_colour_palette(len(data))

    return JsonResponse({
        "title": "Membership Types",
        "data": {
            "labels": list(data.keys()),
            "datasets": [
                {
                    "label": "Membership types",
                    "backgroundColor": [colour[0] for colour in colours],
                    "borderColor": [colour[1] for colour in colours],
                    "data": list(data.values()),
                }
            ]
        },
    })


def get_users_by_age():
    cache_key = "users_by_age"
    users_by_age = cache.get(cache_key)
    last_signed = OnlineDisclaimer.objects.latest("id").date

    if users_by_age is None or users_by_age["last_signed"] < last_signed:
        now = datetime.now(tz=UTC)
        cutoff = now - relativedelta(years=5)
        queries = Q(version=DisclaimerContent.current_version()) & (Q(date__gte=cutoff) | Q(date_updated__gte=cutoff))
        ages = (
            OnlineDisclaimer.objects.filter(queries)
            .annotate(
                age=Func(
                    Value("year"),
                    Func(Value(now.date()), F("dob"), function="age"),
                    function="date_part",
                    output_field=IntegerField(),
                )
            ).values_list("age", flat=True)
        )

        age_groups = {
            "18-25": (18, 25),
            "26-30": (26, 30),
            "31-35": (31, 35),
            "36-40": (36, 40),
            "41-45": (41, 45),
            "46-50": (46, 51),
            "51-55": (51, 56),
            "56-60": (56, 60),
            "61-65": (61, 66),
            "66-70": (66, 70),
            "71+": (71, 100),
        }
        age_counter = Counter(ages)

        data = {age: 0 for age in age_groups}
        for age, count in age_counter.items():
            for age_group, min_max in age_groups.items():
                if min_max[0] <= age <= min_max[1]:
                    data[age_group] += count

        users_by_age = {
            "last_signed": last_signed,
            "data": data
        }
        cache.set(cache_key, users_by_age, timeout=(60 * 60 * 24))
    
    return users_by_age["data"]


@staff_member_required
def view_users_by_age(request):
    data = get_users_by_age()
    colours = generate_colour_palette(len(data))

    return JsonResponse({
        "title": "User ages (users with active disclaimer)",
        "data": {
            "labels": list(data.keys()),
            "datasets": [
                {
                    "label": "User Age",
                    "backgroundColor": [colour[0] for colour in colours],
                    "borderColor": [colour[1] for colour in colours],
                    "data": list(data.values()),
                }
            ]
        },
    })


@staff_member_required
def view_users_booked_in_past_month(request):
    cutoff = datetime.now(tz=UTC) - relativedelta(months=1)
    now = datetime.now(tz=UTC)
    cutoff = now - relativedelta(years=5)
    queries = Q(version=DisclaimerContent.current_version()) & (Q(date__gte=cutoff) | Q(date_updated__gte=cutoff))
    users = OnlineDisclaimer.objects.filter(queries).values("user_id").count()
    booked_past_month = Booking.objects.filter(status="OPEN", event__date__gte=cutoff).distinct("user_id").count()

    data = {
        "booked": booked_past_month,
        "not booked": users - booked_past_month
    }
    colours = generate_colour_palette(len(data))

    return JsonResponse({
        "title": "Active users booked in past month",
        "data": {
            "labels": list(data.keys()),
            "datasets": [
                {
                    "label": "Users with booking in past month",
                    "backgroundColor": [colour[0] for colour in colours],
                    "borderColor": [colour[1] for colour in colours],
                    "data": list(data.values()),
                }
            ]
        },
    })
