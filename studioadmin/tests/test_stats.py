import pytest
from datetime import datetime, UTC
from unittest.mock import patch

from model_bakery import recipe, baker

from booking.models import Event, Booking, EventType, Membership, UserMembership

from stripe_payments.tests.mock_connector import MockConnector

from studioadmin.views.stats import (
    get_active_memberships_by_type,
    get_annual_monthly_stats_by_event_type,
    get_annual_payment_methods,
    get_avg_late_cancellation_per_class_for_month,
    get_avg_no_shows_per_class_for_month,
    get_bookings_count_for_month,
    get_bookings_ratio_for_month,
    get_cumulative_user_registrations,
    get_events_count_for_month,
    get_new_user_registrations,
    get_pct_waiting_list_for_month,
    get_users_by_age,
    get_years,
    get_event_types_year_dict,
)


pytestmark = pytest.mark.django_db


def test_get_years():
    baker.make(Event, date=datetime(2022, 1, 3, tzinfo=UTC))
    baker.make(Event, date=datetime(2024, 1, 3, tzinfo=UTC)) 
    baker.make(Event, date=datetime(2021, 1, 3, tzinfo=UTC))
    
    assert get_years() == [2024, 2022, 2021]

    baker.make(Event, date=datetime(2025, 1, 3, tzinfo=UTC)) 
    baker.make(Event, date=datetime(2025, 1, 3, tzinfo=UTC))
    assert get_years() == [2025, 2024, 2022, 2021]


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_get_active_memberships_by_type(seller):
    
    membership1 = baker.make(
        Membership, name="membership1", description="a membership", price=10
    )
    membership2 = baker.make(
        Membership, name="membership2", description="a membership", price=10
    )
    membership3 = baker.make(
        Membership, name="membership3", description="a membership", price=10
    )
    membership4 = baker.make(
        Membership, name="membership4", description="a membership", price=10
    )

    baker.make(UserMembership, membership=membership1, subscription_status="incomplete",)
    baker.make(UserMembership, membership=membership2, subscription_status="active", _quantity=3)
    baker.make(UserMembership, membership=membership3, subscription_status="active", _quantity=4)
    baker.make(UserMembership, membership=membership4,subscription_status="active",_quantity=5)
    
    assert get_active_memberships_by_type() == {"membership2": 3, "membership3": 4, "membership4": 5}


def test_get_users_by_age(freezer):
    freezer.move_to(datetime(2025, 6, 1, tzinfo=UTC))

    # 18, 20, 25: 18-25
    baker.make_recipe("booking.online_disclaimer", dob=datetime(2007, 2, 1, tzinfo=UTC))
    baker.make_recipe("booking.online_disclaimer", dob=datetime(2005, 2, 1, tzinfo=UTC))
    baker.make_recipe("booking.online_disclaimer", dob=datetime(2000, 2, 1, tzinfo=UTC))
    # 27: 26-30
    baker.make_recipe("booking.online_disclaimer", dob=datetime(1998, 2, 1, tzinfo=UTC))
    # 45: 41-45
    baker.make_recipe("booking.online_disclaimer", dob=datetime(1980, 2, 1, tzinfo=UTC))
    # 71, 80, 85: 71+
    baker.make_recipe("booking.online_disclaimer", dob=datetime(1954, 2, 1, tzinfo=UTC))
    baker.make_recipe("booking.online_disclaimer", dob=datetime(1945, 2, 1, tzinfo=UTC))
    baker.make_recipe("booking.online_disclaimer", dob=datetime(1940, 2, 1, tzinfo=UTC))
    # nonsense age, excluded
    baker.make_recipe("booking.online_disclaimer", dob=datetime(1800, 2, 1, tzinfo=UTC))

    assert get_users_by_age() == {
        "18-25": 3,
        "26-30": 1,
        "31-35": 0,
        "36-40": 0,
        "41-45": 1,
        "46-50": 0,
        "51-55": 0,
        "56-60": 0,
        "61-65": 0,
        "66-70": 0,
        "71+": 3,
    }
    
    freezer.move_to(datetime(2027, 6, 1, tzinfo=UTC))
    assert get_users_by_age() == {
        "18-25": 2,
        "26-30": 2,
        "31-35": 0,
        "36-40": 0,
        "41-45": 0,
        "46-50": 1,
        "51-55": 0,
        "56-60": 0,
        "61-65": 0,
        "66-70": 0,
        "71+": 3,
    }


def test_get_bookings_count_for_month():
    # open, paid bookings
    baker.make("booking.booking", event__date=datetime(2022, 3, 1, tzinfo=UTC), paid=True, no_show=False)
    baker.make("booking.booking", event__date=datetime(2022, 3, 15, tzinfo=UTC), paid=True, no_show=False)
    # open, unpaid
    baker.make("booking.booking", event__date=datetime(2022, 3, 16, tzinfo=UTC), paid=False)
    # open, paid, different month
    baker.make("booking.booking", event__date=datetime(2022, 4, 1, tzinfo=UTC), paid=True)

    assert get_bookings_count_for_month(Event.objects.all(), 3) == 2
    assert get_bookings_count_for_month(Event.objects.all(), 4) == 1


def test_get_bookings_ratio_for_month():
    # 20% full
    baker.make("booking.booking", event__date=datetime(2022, 3, 1, tzinfo=UTC), event__max_participants=5, paid=True, no_show=False)
    # 100% full
    baker.make("booking.booking", event__date=datetime(2022, 3, 15, tzinfo=UTC), event__max_participants=1, paid=True, no_show=False)
    # open, unpaid - 0% full
    baker.make("booking.booking", event__date=datetime(2022, 3, 16, tzinfo=UTC), event__max_participants=10, paid=False)
    
    # open, paid, different month
    event = baker.make_recipe("booking.past_event", date=datetime(2022, 4, 1, tzinfo=UTC), max_participants=2)
    baker.make("booking.booking", event=event, paid=True, _quantity=2)

    assert get_bookings_ratio_for_month(Event.objects.all(), 3) == 40  # average of 20, 100, 0  
    assert get_bookings_ratio_for_month(Event.objects.all(), 4) == 100


def test_get_annual_monthly_stats_by_event_type(freezer):
    freezer.move_to(datetime(2025, 4, 1, tzinfo=UTC))
    
    def calc_fn(events, month):
        return month
    
    expected = get_event_types_year_dict()
    for evtype, months in expected.items():
        for i, month in enumerate(months, start=1):
            expected[evtype][month] = i

    assert get_annual_monthly_stats_by_event_type("test_key_2022", 2022, calc_fn) == expected
    assert get_annual_monthly_stats_by_event_type("test_key_2025", 2025, calc_fn) == expected

    # change the calc function; previous years are cached
    # this year is recalculated, but only for the current and previous months
    def calc_fn1(events, month):
        return month + 1
    
    assert get_annual_monthly_stats_by_event_type("test_key_2022", 2022, calc_fn1) == expected
    this_year = get_annual_monthly_stats_by_event_type("test_key_2025", 2025, calc_fn1) 
    assert this_year != expected
    assert this_year["CL"]["Jan"] == 1
    assert this_year["CL"]["Feb"] == 2
    # Mar/Apr only reflect calc_fn1
    assert this_year["CL"]["Mar"] == 4
    assert this_year["CL"]["Apr"] == 5
    assert this_year["CL"]["May"] == 5
    assert this_year["CL"]["Jun"] == 6

    # we can explicitly also recalculate future months for the current year
    this_year = get_annual_monthly_stats_by_event_type("test_key_2025", 2025, calc_fn1, recalc_future=True)
    assert this_year != expected
    assert this_year["CL"]["Jan"] == 1
    assert this_year["CL"]["Feb"] == 2
    assert this_year["CL"]["Mar"] == 4
    assert this_year["CL"]["Apr"] == 5
    assert this_year["CL"]["May"] == 6
    assert this_year["CL"]["Jun"] == 7
    # previous years are retrieved from cache
    assert get_annual_monthly_stats_by_event_type("test_key_2022", 2022, calc_fn1, recalc_future=True) == expected

    def calc_fn2(events, month):
        return "foo"
    
    # we can handle the 1st month
    freezer.move_to(datetime(2025, 1, 1, tzinfo=UTC))
    this_year = get_annual_monthly_stats_by_event_type("test_key_2025", 2025, calc_fn2) 
    assert this_year != expected
    # only the first month is recalculated; other months remain as per last call (calc_fn1)
    assert this_year["CL"]["Jan"] == "foo"
    assert this_year["CL"]["Feb"] == 2

    # previous years are still retrieved from cache
    assert get_annual_monthly_stats_by_event_type("test_key_2022", 2022, calc_fn2) == expected
    # unless we change the cache key
    assert get_annual_monthly_stats_by_event_type("test_new_key_2022", 2022, calc_fn2) != expected