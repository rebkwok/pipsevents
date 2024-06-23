import json

from datetime import datetime
from datetime import timezone as dt_tz

from unittest.mock import patch

from model_bakery import baker
import pytest

from booking.models import Membership, MembershipItem, UserMembership, Event
from stripe_payments.tests.mock_connector import MockConnector


pytestmark = pytest.mark.django_db


def test_membership_create(mocked_responses, seller):
    mocked_responses.post(
        "https://api.stripe.com/v1/products",
        body=json.dumps(
            {
                "object": "product",
                "url": "/v1/product",
                "id": "memb-1",
                "name": "memb 1",
                "description": "a membership",
                "default_price": "price_1",
            }
        ),
        status=200,
        content_type="application/json",
    )
    membership = baker.make(
        Membership, name="memb 1", description="a membership", price=10
    )
    assert membership.stripe_product_id == "memb-1"
    assert membership.stripe_price_id == "price_1"

    assert str(membership) == "memb 1 - £10"


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_create_duplicate_name(seller):
    m1 = baker.make(Membership, name="memb", description="a membership", price=10)
    assert m1.stripe_product_id == "memb"

    m2 = baker.make(Membership, name="memb", description="a membership", price=10)
    assert m2.stripe_product_id == "memb_1"


def test_membership_change_price(mocked_responses, seller):
    # created initial product
    mocked_responses.post(
        "https://api.stripe.com/v1/products",
        body=json.dumps(
            {
                "object": "product",
                "url": "/v1/product",
                "id": "memb-1",
                "name": "membership 1",
                "description": "a membership",
                "default_price": "price_1",
            }
        ),
        status=200,
        content_type="application/json",
    )
    # gets list of matching product prices
    mocked_responses.get(
        "https://api.stripe.com/v1/prices",
        body=json.dumps(
            {
                "object": "list",
                "url": "/v1/prices",
                "data": [],
            }
        ),
        status=200,
        content_type="application/json",
    )
    # create new price
    mocked_responses.post(
        "https://api.stripe.com/v1/prices",
        body=json.dumps(
            {
                "object": "price",
                "url": "/v1/prices",
                "id": "price_2",
            }
        ),
        status=200,
        content_type="application/json",
    )
    # update product to set price as default
    mocked_responses.post(
        "https://api.stripe.com/v1/products/memb-1",
        body=json.dumps(
            {
                "object": "product",
                "url": "/v1/product",
                "id": "memb-1",
                "name": "membership 1",
                "description": "a membership",
                "default_price": "price_2",
            }
        ),
        status=200,
        content_type="application/json",
    )

    membership = baker.make(
        Membership, name="memb 1", description="a membership", price=10
    )
    assert membership.stripe_product_id == "memb-1"
    assert membership.stripe_price_id == "price_1"

    membership.price = 20
    membership.save()

    assert membership.stripe_product_id == "memb-1"
    assert membership.stripe_price_id == "price_2"


def test_membership_change_price_with_user_memberships(mocked_responses, seller):
    # created initial product
    mocked_responses.post(
        "https://api.stripe.com/v1/products",
        body=json.dumps(
            {
                "object": "product",
                "url": "/v1/product",
                "id": "memb-1",
                "name": "membership 1",
                "description": "a membership",
                "default_price": "price_1",
            }
        ),
        status=200,
        content_type="application/json",
    )
    # gets list of matching product prices
    mocked_responses.get(
        "https://api.stripe.com/v1/prices",
        body=json.dumps(
            {
                "object": "list",
                "url": "/v1/prices",
                "data": [],
            }
        ),
        status=200,
        content_type="application/json",
    )
    # create new price
    mocked_responses.post(
        "https://api.stripe.com/v1/prices",
        body=json.dumps(
            {
                "object": "price",
                "url": "/v1/prices",
                "id": "price_2",
            }
        ),
        status=200,
        content_type="application/json",
    )
    # update product to set price as default
    mocked_responses.post(
        "https://api.stripe.com/v1/products/memb-1",
        body=json.dumps(
            {
                "object": "product",
                "url": "/v1/product",
                "id": "memb-1",
                "name": "membership 1",
                "description": "a membership",
                "default_price": "price_2",
            }
        ),
        status=200,
        content_type="application/json",
    )

    # update subscriptions to add schedule to change price
    # get the subscription to check if it has a schedule
    mocked_responses.get(
        "https://api.stripe.com/v1/subscriptions/subsc-1",
        body=json.dumps(
            {
                "object": "subscription",
                "url": "/v1/subscription",
                "id": "subsc-1",
                "schedule": None,
            }
        ),
        status=200,
        content_type="application/json",
    )

    # create the schedule
    mocked_responses.post(
        "https://api.stripe.com/v1/subscription_schedules",
        body=json.dumps(
            {
                "object": "subscription_schedule",
                "url": "/v1/subscription_schedules",
                "id": "sub_sched-1",
                "subscription": "subsc-1",
                "end_behavior": "release",
                "phases": [
                    {
                        "start_date": datetime(2024, 6, 25).timestamp(),
                        "end_date": datetime(2024, 7, 25).timestamp(),
                        "items": [{"price": 2000, "quantity": 1}],
                    }
                ],
            }
        ),
        status=200,
        content_type="application/json",
    )
    # update the schedule
    mocked_responses.post(
        "https://api.stripe.com/v1/subscription_schedules/sub_sched-1",
        body=json.dumps(
            {
                "object": "subscription_schedule",
                "url": "/v1/subscription_schedules",
                "id": "sub_sched-1",
                "subscription": "subsc-1",
            }
        ),
        status=200,
        content_type="application/json",
    )

    membership = baker.make(
        Membership, name="memb 1", description="a membership", price=10
    )
    assert membership.stripe_product_id == "memb-1"
    assert membership.stripe_price_id == "price_1"

    baker.make(
        UserMembership,
        membership=membership,
        subscription_status="active",
        subscription_id="subsc-1",
    )
    membership.price = 20
    membership.save()

    assert membership.stripe_product_id == "memb-1"
    assert membership.stripe_price_id == "price_2"


def test_membership_change_name(mocked_responses, seller):
    # created initial product
    mocked_responses.post(
        "https://api.stripe.com/v1/products",
        body=json.dumps(
            {
                "object": "product",
                "url": "/v1/product",
                "id": "memb-1",
                "name": "memb 1",
                "description": "a membership",
                "default_price": "price_1",
            }
        ),
        status=200,
        content_type="application/json",
    )
    # update product
    mocked_responses.post(
        "https://api.stripe.com/v1/products/memb-1",
        body=json.dumps(
            {
                "object": "product",
                "url": "/v1/product",
                "id": "memb-1",
                "name": "memb 2",
                "description": "a membership",
                "default_price": "price_1",
            }
        ),
        status=200,
        content_type="application/json",
    )

    membership = baker.make(
        Membership, name="memb 1", description="a membership", price=10
    )
    assert membership.stripe_product_id == "memb-1"
    assert membership.stripe_price_id == "price_1"

    membership.name = "memb 2"
    membership.save()

    assert membership.stripe_product_id == "memb-1"
    assert membership.stripe_price_id == "price_1"
    assert membership.name == "memb 2"


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_item_str():
    membership = baker.make(
        Membership, name="Test membership", description="a membership", price=10
    )
    event_type = baker.make_recipe("booking.event_type_PC", subtype="Level class")
    mitem = baker.make(
        MembershipItem, event_type=event_type, membership=membership, quantity=4
    )
    assert str(mitem) == "Test membership - Level class - 4"


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_user_membership_str(seller):
    membership = baker.make(
        Membership, name="Test membership", description="a membership", price=10
    )
    user_membership = baker.make(
        UserMembership,
        membership=membership,
        user__username="test",
    )
    assert str(user_membership) == "test - Test membership"


@pytest.mark.parametrize(
    "start_date,end_date,status,is_active",
    [
        # started, no end, status active
        (datetime(2020, 5, 20, tzinfo=dt_tz.utc), None, "active", True),
        # started, end, status active
        (datetime(2020, 2, 20, tzinfo=dt_tz.utc), datetime(2020, 5, 20, tzinfo=dt_tz.utc), "active", True),
        # started, no end, status cancelled
        (datetime(2020, 5, 20, tzinfo=dt_tz.utc), None, "canceled", False),
         # started, no end, status inactive
        (datetime(2020, 5, 20, tzinfo=dt_tz.utc), None, "inactive", False),
    ],
)
@pytest.mark.freeze_time("2020-05-21")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_user_membership_is_active(seller, start_date, end_date, status, is_active):
    membership = baker.make(
        Membership, name="Test membership", description="a membership", price=10
    )
    user_membership = baker.make(
        UserMembership,
        membership=membership,
        start_date=start_date,
        end_date=end_date,
        subscription_status=status,
    )
    assert user_membership.is_active() == is_active


@pytest.mark.parametrize(
    "now,is_active",
    [
        (datetime(2020, 5, 25, tzinfo=dt_tz.utc), True),
        (datetime(2020, 5, 28, tzinfo=dt_tz.utc), True),
        (datetime(2020, 5, 30, tzinfo=dt_tz.utc), False),
    ],
)
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_user_membership_past_due_is_active(freezer, seller, now, is_active):
    freezer.move_to(now)
    membership = baker.make(
        Membership, name="Test membership", description="a membership", price=10
    )
    user_membership = baker.make(
        UserMembership,
        membership=membership,
        start_date=datetime(2020, 4, 20, tzinfo=dt_tz.utc),
        subscription_status="past_due",
    )
    assert user_membership.is_active() == is_active


@pytest.mark.parametrize(
    "now,start_date,end_date,is_active",
    [
        # started before, ends at end of month
        # membership is still active if we're before the end date
        (
            datetime(2020, 5, 25, tzinfo=dt_tz.utc),
            datetime(2020, 4, 20, tzinfo=dt_tz.utc),
            datetime(2020, 6, 1, tzinfo=dt_tz.utc),
            True,
        ),
        (
            datetime(2020, 5, 28, tzinfo=dt_tz.utc),
            datetime(2020, 4, 20, tzinfo=dt_tz.utc),
            datetime(2020, 6, 1, tzinfo=dt_tz.utc),
            True,
        ),
        (
            datetime(2020, 5, 30, tzinfo=dt_tz.utc),
            datetime(2020, 4, 20, tzinfo=dt_tz.utc),
            datetime(2020, 6, 1, tzinfo=dt_tz.utc),
            True,
        ),
        # After end date
        (
            datetime(2020, 6, 1, tzinfo=dt_tz.utc),
            datetime(2020, 4, 20, tzinfo=dt_tz.utc),
            datetime(2020, 6, 1, tzinfo=dt_tz.utc),
            False,
        ),
        # Starts in future
        (
            datetime(2020, 5, 25, tzinfo=dt_tz.utc),
            datetime(2020, 6, 1, tzinfo=dt_tz.utc),
            datetime(2020, 6, 1, tzinfo=dt_tz.utc),
            False,
        ),
    ],
)
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_user_membership_cancelled_is_active(
    freezer, seller, now, start_date, end_date, is_active
):
    freezer.move_to(now)
    membership = baker.make(
        Membership, name="Test membership", description="a membership", price=10
    )
    user_membership = baker.make(
        UserMembership,
        membership=membership,
        start_date=start_date,
        end_date=end_date,
        subscription_status="canceled",
    )
    assert user_membership.is_active() == is_active


@pytest.mark.freeze_time("2020-05-21")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_user_membership_valid_for_event(seller):
    membership = baker.make(
        Membership, name="Test membership", description="a membership", price=10
    )
    pc_event_type = baker.make_recipe("booking.event_type_PC", subtype="Level class")
    pp_event_type = baker.make_recipe("booking.event_type_PP", subtype="Pole practice")
    baker.make(
        MembershipItem, event_type=pc_event_type, membership=membership, quantity=4
    )

    user_membership = baker.make(
        UserMembership,
        membership=membership,
        start_date=datetime(2020, 5, 1, tzinfo=dt_tz.utc),
        subscription_status="active",
    )

    # only valid for correct event type
    pc_event = baker.make(Event, event_type=pc_event_type, date=datetime(2020, 5, 28, tzinfo=dt_tz.utc))
    pp_event = baker.make(Event, event_type=pp_event_type, date=datetime(2020, 5, 28, tzinfo=dt_tz.utc))
    assert user_membership.valid_for_event(pc_event)
    assert not user_membership.valid_for_event(pp_event)

    # already booked for this event type this month
    baker.make(
        "booking.booking",
        user=user_membership.user,
        event__event_type=pc_event_type,
        event__date=datetime(2020, 5, 20, tzinfo=dt_tz.utc),
        membership=user_membership,
        _quantity=3,
    )
    assert user_membership.valid_for_event(pc_event)

    baker.make(
        "booking.booking",
        user=user_membership.user,
        event__event_type=pc_event_type,
        event__date=datetime(2020, 5, 15, tzinfo=dt_tz.utc),
        membership=user_membership,
    )
    assert not user_membership.valid_for_event(pc_event)


@pytest.mark.parametrize(
    "event_date,end_date,is_valid",
    [
        # valid, same month
        (datetime(2020, 5, 1, 10, 0, tzinfo=dt_tz.utc), None, True),
        (datetime(2020, 5, 31, 10, 0, tzinfo=dt_tz.utc), None, True),
        # same day/month later year, still valid because no end date
        (datetime(2021, 5, 31, 10, 0, tzinfo=dt_tz.utc), None, True),
        # same day/month later year, not valid because end date
        (datetime(2021, 5, 31, 10, 0, tzinfo=dt_tz.utc), datetime(2020, 6, 1, tzinfo=dt_tz.utc), False),
        # same day/month earlier year, not valid
        (datetime(2019, 5, 31, 10, 0, tzinfo=dt_tz.utc), None, False),
        (
            datetime(2020, 6, 1, 10, 0, tzinfo=dt_tz.utc),
            None,
            True,
        ),  # event date is after this month, but still valid because no end date
        (datetime(2020, 6, 1, 10, 0, tzinfo=dt_tz.utc), datetime(2020, 6, 1, tzinfo=dt_tz.utc), False),
        (datetime(2020, 4, 30, 10, 0, tzinfo=dt_tz.utc), None, False),
        # membership has already ended, not active
        (datetime(2020, 5, 1, 10, 0, tzinfo=dt_tz.utc), datetime(2020, 4, 1, tzinfo=dt_tz.utc), False),
    ],
)
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_user_membership_valid_for_event_dates(seller, event_date, end_date, is_valid):
    membership = baker.make(
        Membership, name="Test membership", description="a membership", price=10
    )
    pc_event_type = baker.make_recipe("booking.event_type_PC", subtype="Level class")
    baker.make(
        MembershipItem, event_type=pc_event_type, membership=membership, quantity=4
    )

    user_membership = baker.make(
        UserMembership,
        membership=membership,
        start_date=datetime(2020, 5, 1, tzinfo=dt_tz.utc),
        end_date=end_date,
        subscription_status="active",
    )

    # only valid for correct event type
    pc_event = baker.make(Event, event_type=pc_event_type, date=event_date)
    assert user_membership.valid_for_event(pc_event) == is_valid


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_user_membership_valid_for_event_inactive_membership(seller):
    membership = baker.make(
        Membership, name="Test membership", description="a membership", price=10
    )
    pc_event_type = baker.make_recipe("booking.event_type_PC", subtype="Level class")
    baker.make(
        MembershipItem, event_type=pc_event_type, membership=membership, quantity=4
    )

    inactive_user_membership = baker.make(
        UserMembership,
        membership=membership,
        start_date=datetime(2020, 5, 1, tzinfo=dt_tz.utc),
        subscription_status="incomplete",
    )

    active_user_membership = baker.make(
        UserMembership,
        membership=membership,
        start_date=datetime(2020, 5, 1, tzinfo=dt_tz.utc),
        subscription_status="active",
    )

    # not valid for correct event type
    pc_event = baker.make(Event, event_type=pc_event_type, date=datetime(2020, 5, 10, tzinfo=dt_tz.utc))
    assert not inactive_user_membership.valid_for_event(pc_event)
    assert active_user_membership.valid_for_event(pc_event)


@pytest.mark.parametrize(
    "status,hr_status",
    [
       *[(k, v) for k, v in UserMembership.HR_STATUS.items()],
       ("unknown status", "Unknown Status")
    ]
)
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_user_membership_hr_status(seller, status, hr_status):
    membership = baker.make(
        Membership, name="Test membership", description="a membership", price=10
    )
    user_membership = baker.make(
        UserMembership,
        membership=membership,
        start_date=datetime(2020, 5, 1, tzinfo=dt_tz.utc),
        subscription_status=status,
    )
    assert user_membership.hr_status() == hr_status


@pytest.mark.freeze_time("2020-05-21")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_user_membership_bookings_by_month(seller):
    membership = baker.make(
        Membership, name="Test membership", description="a membership", price=10
    )
    # 2 valid event types
    pc_event_type = baker.make_recipe("booking.event_type_PC", subtype="Level class")
    baker.make(
        MembershipItem, event_type=pc_event_type, membership=membership, quantity=4
    )
    pc_event_type1 = baker.make_recipe("booking.event_type_PC", subtype="Level class1")
    baker.make(
        MembershipItem, event_type=pc_event_type1, membership=membership, quantity=4
    )
    # 1 non-valid event type
    other_event_type = baker.make_recipe("booking.event_type_PC", subtype="Other class")

    # started membership in Jan last year
    user_membership = baker.make(
        UserMembership,
        membership=membership,
        start_date=datetime(2019, 1, 1, tzinfo=dt_tz.utc),
        subscription_status="active",
    )

    # Events this month for each event type
    pc_event = baker.make(Event, event_type=pc_event_type, date=datetime(2020, 5, 15, tzinfo=dt_tz.utc))
    pc_event1 = baker.make(Event, event_type=pc_event_type1, date=datetime(2020, 5, 10, tzinfo=dt_tz.utc))
    oc_event = baker.make(Event, event_type=other_event_type, date=datetime(2020, 5, 12, tzinfo=dt_tz.utc))

     # Events next month for each event type
    pc_event_next = baker.make(Event, event_type=pc_event_type, date=datetime(2020, 6, 15, tzinfo=dt_tz.utc))
    pc_event1_next = baker.make(Event, event_type=pc_event_type1, date=datetime(2020, 6, 10, tzinfo=dt_tz.utc))
    oc_event_next = baker.make(Event, event_type=other_event_type, date=datetime(2020, 6, 12, tzinfo=dt_tz.utc))

    # Events same month last year for each event type
    pc_event_old = baker.make(Event, event_type=pc_event_type, date=datetime(2019, 5, 15, tzinfo=dt_tz.utc))
    pc_event1_old = baker.make(Event, event_type=pc_event_type1, date=datetime(2019, 5, 10, tzinfo=dt_tz.utc))
    oc_event_old = baker.make(Event, event_type=other_event_type, date=datetime(2019, 5, 12, tzinfo=dt_tz.utc))

    # Valid events for non-open booking status
    # no-shows are included in count, cancelled are not
    no_show_pc = baker.make(Event, event_type=pc_event_type, date=datetime(2020, 5, 16, tzinfo=dt_tz.utc))
    cancelled_pc = baker.make(Event, event_type=pc_event_type, date=datetime(2020, 5, 17, tzinfo=dt_tz.utc))
    
    # make a booking with membership for each valid event type
    for ev in [pc_event, pc_event1, pc_event_next, pc_event_old, pc_event1_old, pc_event1_next]:
        baker.make_recipe(
            "booking.booking",
            user=user_membership.user,
            event=ev,
            membership=user_membership,
        )
    
    # make a booking without membership for each invalid event type
    for ev in [oc_event, oc_event_old, oc_event_next]:
        baker.make_recipe(
            "booking.booking",
            user=user_membership.user,
            event=ev,
            paid=True,
        )
    
    # no-show booking
    baker.make_recipe(
        "booking.booking",
        user=user_membership.user,
        event=no_show_pc,
        membership=user_membership,
        status="OPEN",
        no_show=True,
    )

    # cancelled booking
    baker.make_recipe(
        "booking.booking",
        user=user_membership.user,
        event=cancelled_pc,
        membership=user_membership,
        status="CANCELLED",
    )

    # Bookings for these events are counted
    booked_events = [pc_event.id, pc_event1.id, no_show_pc.id]
    assert set(user_membership.bookings_this_month()) == {booking for booking in user_membership.user.bookings.filter(event_id__in=booked_events)}
    booked_events_next = [pc_event1_next.id, pc_event_next.id]
    assert set(user_membership.bookings_next_month()) == {booking for booking in user_membership.user.bookings.filter(event_id__in=booked_events_next)}


@pytest.mark.parametrize(
    "now,event_date",
    [
        (datetime(2020, 4, 15, tzinfo=dt_tz.utc), datetime(2020, 5, 15, tzinfo=dt_tz.utc)),
        (datetime(2020, 5, 31, tzinfo=dt_tz.utc), datetime(2020, 6, 1, tzinfo=dt_tz.utc)),
        (datetime(2020, 12, 30, tzinfo=dt_tz.utc), datetime(2021, 1, 15, tzinfo=dt_tz.utc)),
    ]
)
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_user_membership_bookings_next_month(freezer, seller, now, event_date):
    freezer.move_to(now)
    membership = baker.make(
        Membership, name="Test membership", description="a membership", price=10
    )
    pc_event_type = baker.make_recipe("booking.event_type_PC", subtype="Level class")
    baker.make(
        MembershipItem, event_type=pc_event_type, membership=membership, quantity=4
    )
    event = baker.make(Event, event_type=pc_event_type, date=event_date)
    # started membership in Jan last year
    user_membership = baker.make(
        UserMembership,
        membership=membership,
        start_date=datetime(2019, 1, 1, tzinfo=dt_tz.utc),
        subscription_status="active",
    )

    booking = baker.make_recipe(
        "booking.booking",
        user=user_membership.user,
        event=event,
        membership=user_membership,
    )

    assert list(user_membership.bookings_next_month()) == [booking]


@pytest.mark.parametrize(
    "end_date,membership_end_date",
    [   
        # no date
        (None, None),
        # non DST
        (datetime(2022, 2, 5, tzinfo=dt_tz.utc), datetime(2022, 3, 1, tzinfo=dt_tz.utc)),
        # DST
        (datetime(2022, 7, 5, tzinfo=dt_tz.utc), datetime(2022, 8, 1, tzinfo=dt_tz.utc)),
        # end of year
        (datetime(2022, 12, 5, tzinfo=dt_tz.utc), datetime(2023, 1, 1, tzinfo=dt_tz.utc)),
    ]
)
def test_calculate_membership_end_date(end_date, membership_end_date):
    assert UserMembership.calculate_membership_end_date(end_date) == membership_end_date


def _setup_user_membership_and_bookings():
    membership = baker.make(
        Membership, name="Test membership", description="a membership", price=10
    )
    pc_event_type = baker.make_recipe("booking.event_type_PC", subtype="Level class")
    baker.make(
        MembershipItem, event_type=pc_event_type, membership=membership, quantity=4
    )

    event = baker.make(Event, event_type=pc_event_type, date=datetime(2020, 3, 5, tzinfo=dt_tz.utc))
    end_of_month_event = baker.make(Event, event_type=pc_event_type, date=datetime(2020, 3, 29, tzinfo=dt_tz.utc))
    next_month_event = baker.make(Event, event_type=pc_event_type, date=datetime(2020, 4, 5, tzinfo=dt_tz.utc))
    
    # active membership, no end date
    user_membership = baker.make(
        UserMembership,
        membership=membership,
        start_date=datetime(2019, 1, 1, tzinfo=dt_tz.utc),
        subscription_status="active",
    )

    booking = baker.make_recipe(
        "booking.booking",
        user=user_membership.user,
        event=event,
        membership=user_membership,
    )
    booking_end_of_month = baker.make_recipe(
        "booking.booking",
        user=user_membership.user,
        event=end_of_month_event,
        membership=user_membership,
    )
    booking_next = baker.make_recipe(
        "booking.booking",
        user=user_membership.user,
        event=next_month_event,
        membership=user_membership,
    )
    return user_membership, booking, booking_end_of_month, booking_next


@pytest.mark.freeze_time("2020-03-21")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_reallocate_bookings(seller):
    user_membership, booking, booking_end_of_month, booking_next = _setup_user_membership_and_bookings()
    booking_set = {booking, booking_end_of_month, booking_next}

    # active membership, reallocating does nothing
    user_membership.reallocate_bookings()

    for bk in booking_set:
        bk.refresh_from_db()

    assert set(user_membership.bookings.all()) == booking_set


@pytest.mark.freeze_time("2020-03-21")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_reallocate_bookings_after_cancel(seller):
    user_membership, booking, booking_end_of_month, booking_next = _setup_user_membership_and_bookings()
    booking_set = {booking, booking_end_of_month, booking_next}

    # change status to cancelled
    user_membership.subscription_status = "canceled"
    user_membership.end_date = datetime(2020, 4, 1, tzinfo=dt_tz.utc)
    user_membership.save()

    user_membership.reallocate_bookings()

    for bk in booking_set:
        bk.refresh_from_db()
    
    # next months booking has been removed
    assert set(user_membership.bookings.all()) == {booking, booking_end_of_month}
    assert booking_next.membership == None
    assert not booking_next.paid


@pytest.mark.freeze_time("2020-03-21")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_reallocate_bookings_after_cancel_with_other_membership_inactive(seller):
    user_membership, booking, booking_end_of_month, booking_next = _setup_user_membership_and_bookings()
    booking_set = {booking, booking_end_of_month, booking_next}

    # change status to cancelled
    user_membership.subscription_status = "canceled"
    user_membership.end_date = datetime(2020, 4, 1, tzinfo=dt_tz.utc)
    user_membership.save()

    # New membership starts next month, not yet active
    next_user_membership = baker.make(
        UserMembership,
        user=user_membership.user,
        membership=user_membership.membership,
        start_date=datetime(2020, 4, 1, tzinfo=dt_tz.utc),
        subscription_status="inactive",
    )
    assert not next_user_membership.valid_for_event(booking_next.event)

    user_membership.reallocate_bookings()

    for bk in booking_set:
        bk.refresh_from_db()
    
    # next months booking has been removed
    assert set(user_membership.bookings.all()) == {booking, booking_end_of_month}
    # not allocated to next membership
    assert set(next_user_membership.bookings.all()) == set()
    assert booking_next.membership == None
    assert not booking_next.paid


@pytest.mark.freeze_time("2020-03-21")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_reallocate_bookings_after_cancel_with_other_membership_active(seller):
    user_membership, booking, booking_end_of_month, booking_next = _setup_user_membership_and_bookings()
    booking_set = {booking, booking_end_of_month, booking_next}

    # change status to cancelled
    user_membership.subscription_status = "canceled"
    user_membership.end_date = datetime(2020, 4, 1, tzinfo=dt_tz.utc)
    user_membership.save()

    # New membership starts next month, not yet active
    next_user_membership = baker.make(
        UserMembership,
        user=user_membership.user,
        membership=user_membership.membership,
        start_date=datetime(2020, 4, 1, tzinfo=dt_tz.utc),
        subscription_status="active",
    )
    assert next_user_membership.valid_for_event(booking_next.event)

    user_membership.reallocate_bookings()

    for bk in booking_set:
        bk.refresh_from_db()

    # next months booking has been removed
    assert set(user_membership.bookings.all()) == {booking, booking_end_of_month}
    # allocated to next membership
    assert set(next_user_membership.bookings.all()) == {booking_next}
    assert booking_next.membership == next_user_membership
    assert booking_next.paid


@pytest.mark.freeze_time("2020-03-21")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_reallocate_bookings_after_cancel_with_active_block(seller):
    user_membership, booking, booking_end_of_month, booking_next = _setup_user_membership_and_bookings()
    booking_set = {booking, booking_end_of_month, booking_next}

    # make a valid block
    block = baker.make_recipe(
        "booking.block", block_type__size=4, start_date=datetime(2020, 3, 1, tzinfo=dt_tz.utc),
        block_type__event_type=booking_next.event.event_type, paid=True,
        user=user_membership.user,
        
    )
    assert block.active_block()
    assert booking_next.get_next_active_block() == block

    # change status to cancelled
    user_membership.subscription_status == "canceled"
    user_membership.end_date = datetime(2020, 4, 1, tzinfo=dt_tz.utc)
    user_membership.save()

    user_membership.reallocate_bookings()

    for bk in booking_set:
        bk.refresh_from_db()

    # next months booking has been removed
    assert set(user_membership.bookings.all()) == {booking, booking_end_of_month}
    # allocated to next membership
    assert booking_next.membership is None
    assert booking_next.block == block
    assert booking_next.paid