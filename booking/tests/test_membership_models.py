import json

from django.core.exceptions import ValidationError
from django.utils import timezone

from datetime import datetime, timedelta
from datetime import timezone as dt_tz

from unittest.mock import patch

from model_bakery import baker
import pytest

from booking.models import Membership, MembershipItem, UserMembership, Event, StripeSubscriptionVoucher
from stripe_payments.tests.mock_connector import MockConnector


pytestmark = pytest.mark.django_db


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_purchaseable(seller):
    active_membership = baker.make(
        Membership, name="Test membership", description="a membership", price=10, visible=True
    )
    inactive_membership = baker.make(
        Membership, name="Test membership", description="a membership", price=10, visible=False
    )
    assert Membership.objects.purchasable().exists() is False

    baker.make(
        MembershipItem, membership=active_membership, quantity=4
    )
    baker.make(
        MembershipItem, membership=inactive_membership, quantity=4
    )
    assert [m.id for m in Membership.objects.purchasable()] == [active_membership.id]


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


def mock_change_price_responses(mocked_responses):
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
    # archive old price
    mocked_responses.post(
        "https://api.stripe.com/v1/prices/price_1",
        body=json.dumps(
            {
                "object": "price",
                "url": "/v1/prices",
                "id": "price_1",
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


def test_membership_change_price(mocked_responses, seller):
    mock_change_price_responses(mocked_responses)
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
    mock_change_price_responses(mocked_responses)

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
                "current_phase": {
                    "start_date": datetime(2024, 6, 25).timestamp(),
                    "end_date": datetime(2024, 7, 25).timestamp(),
                },
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


def test_membership_change_price_with_user_membership_existing_schedule(mocked_responses, seller):
    mock_change_price_responses(mocked_responses)

    # update subscriptions to add schedule to change price
    # get the subscription to check if it has a schedule
    # This one has a schedule with a different proce
    mocked_responses.get(
        "https://api.stripe.com/v1/subscriptions/subsc-1",
        body=json.dumps(
            {
                "object": "subscription",
                "url": "/v1/subscription",
                "id": "subsc-1",
                "schedule": {
                    "object": "subscription_schedule",
                    "url": "/v1/subscription_schedules",
                    "id": "sub_sched-1",
                    "subscription": "subsc-1",
                    "end_behavior": "release",
                    "current_phase": {
                        "start_date": datetime(2024, 6, 25).timestamp(),
                        "end_date": datetime(2024, 7, 25).timestamp(),
                    },
                    "phases": [
                        {
                            "start_date": datetime(2024, 6, 25).timestamp(),
                            "end_date": datetime(2024, 7, 25).timestamp(),
                            "items": [{"price": 500, "quantity": 1}],
                        }
                    ],
                },
            }
        ),
        status=200,
        content_type="application/json",
    )

    mocked_responses.post(
        "https://api.stripe.com/v1/subscription_schedules/sub_sched-1",
        body=json.dumps(
            {
                "object": "subscription_schedule",
                "url": "/v1/subscription_schedules/sub_sched-1",
                "id": "sub_sched-1",
                "subscription": "subsc-1",
                "end_behavior": "release",
                "current_phase": {
                    "start_date": datetime(2024, 6, 25).timestamp(),
                    "end_date": datetime(2024, 7, 25).timestamp(),
                },
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


def test_membership_change_price_with_user_membership_existing_cancelled_schedule(mocked_responses, seller):
    mock_change_price_responses(mocked_responses)
    
    # update subscriptions to add schedule to change price
    # get the subscription to check if it has a schedule
    # This one has a schedule with a different price but due to cancel, so it doesn't update
    mocked_responses.get(
        "https://api.stripe.com/v1/subscriptions/subsc-1",
        body=json.dumps(
            {
                "object": "subscription",
                "url": "/v1/subscription",
                "id": "subsc-1",
                "schedule": {
                    "object": "subscription_schedule",
                    "url": "/v1/subscription_schedules",
                    "id": "sub_sched-1",
                    "subscription": "subsc-1",
                    "end_behavior": "cancel",
                    "phases": [
                        {
                            "start_date": datetime(2024, 6, 25).timestamp(),
                            "end_date": datetime(2024, 7, 25).timestamp(),
                            "items": [{"price": 500, "quantity": 1}],
                        }
                    ],
                },
            }
        ),
        status=200,
        content_type="application/json",
    )
    # Subscription Modify endpoint is NOT called

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
def test_membership_item_str(seller):
    membership = baker.make(
        Membership, name="Test membership", description="a membership", price=10
    )
    event_type = baker.make_recipe("booking.event_type_PC", subtype="Level class")
    mitem = baker.make(
        MembershipItem, event_type=event_type, membership=membership, quantity=4
    )
    assert str(mitem) == "Level class x 4"


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


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_user_membership_invalid_override_status(seller):
    membership = baker.make(
        Membership, name="Test membership", description="a membership", price=10
    )
    with pytest.raises(ValidationError):
        um = baker.make(
            UserMembership,
            membership=membership,
            override_subscription_status="test",
        )
        um.clean()
    um = baker.make(
        UserMembership,
        membership=membership,
        override_subscription_status="paused",
    )
    um.clean()


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
        (datetime(2020, 11, 30, tzinfo=dt_tz.utc), datetime(2020, 12, 15, tzinfo=dt_tz.utc)),
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
    next_month_event1 = baker.make(Event, event_type=pc_event_type, date=datetime(2020, 4, 6, tzinfo=dt_tz.utc))
    next_month_event2 = baker.make(Event, event_type=pc_event_type, date=datetime(2020, 4, 7, tzinfo=dt_tz.utc))
    
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
    booking_next_cancelled = baker.make_recipe(
        "booking.booking",
        user=user_membership.user,
        event=next_month_event1,
        membership=user_membership,
        status="CANCELLED",
    )
    booking_next_no_show = baker.make_recipe(
        "booking.booking",
        user=user_membership.user,
        event=next_month_event2,
        membership=user_membership,
        status="OPEN",
        no_show=True
    )
    return user_membership, booking, booking_end_of_month, booking_next, booking_next_cancelled, booking_next_no_show


@pytest.mark.freeze_time("2020-03-21")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_reallocate_bookings(seller):
    user_membership, booking, booking_end_of_month, booking_next, booking_next_cancelled, booking_next_no_show = (
        _setup_user_membership_and_bookings()
    )
    booking_set = {booking, booking_end_of_month, booking_next, booking_next_cancelled, booking_next_no_show }

    # active membership, reallocating does nothing
    user_membership.reallocate_bookings()

    for bk in booking_set:
        bk.refresh_from_db()

    assert set(user_membership.bookings.all()) == booking_set


@pytest.mark.freeze_time("2020-03-21")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_reallocate_bookings_after_cancel(seller):
    user_membership, booking, booking_end_of_month, booking_next, booking_next_cancelled, booking_next_no_show = (
        _setup_user_membership_and_bookings()
    )
    booking_set = {booking, booking_end_of_month, booking_next, booking_next_cancelled, booking_next_no_show}

    # change status to cancelled
    user_membership.subscription_status = "canceled"
    user_membership.end_date = datetime(2020, 4, 1, tzinfo=dt_tz.utc)
    user_membership.save()

    user_membership.reallocate_bookings()

    for bk in booking_set:
        bk.refresh_from_db()
    
    # next months booking has been removed
    assert set(user_membership.bookings.all()) == {booking, booking_end_of_month}
    for booking in [booking_next, booking_next_cancelled, booking_next_no_show]:
        assert booking.membership is None
        assert not booking.paid


@pytest.mark.freeze_time("2020-03-21")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_reallocate_bookings_after_cancel_with_other_membership_inactive(seller):
    user_membership, booking, booking_end_of_month, booking_next, booking_next_cancelled, booking_next_no_show = (
        _setup_user_membership_and_bookings()
    )
    booking_set = {booking, booking_end_of_month, booking_next, booking_next_cancelled, booking_next_no_show}

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
    assert set(user_membership.bookings.all()) == {booking, booking_end_of_month}
    for booking in [booking_next, booking_next_cancelled, booking_next_no_show]:
        assert booking.membership == None
        assert not booking.paid


@pytest.mark.freeze_time("2020-03-21")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_reallocate_bookings_after_cancel_with_other_membership_active(seller):
    user_membership, booking, booking_end_of_month, booking_next, booking_next_cancelled, booking_next_no_show = (
        _setup_user_membership_and_bookings()
    )
    booking_set = {booking, booking_end_of_month, booking_next, booking_next_cancelled, booking_next_no_show}

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

    for booking in [booking_next_cancelled, booking_next_no_show]:
        assert booking.membership is None
        assert not booking.paid
        assert not booking.payment_confirmed


@pytest.mark.freeze_time("2020-03-21")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_reallocate_bookings_after_cancel_with_active_block(seller):
    user_membership, booking, booking_end_of_month, booking_next, booking_next_cancelled, booking_next_no_show = (
        _setup_user_membership_and_bookings()
    )
    booking_set = {booking, booking_end_of_month, booking_next, booking_next_cancelled, booking_next_no_show}

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

    for booking in [booking_next_cancelled, booking_next_no_show]:
        assert booking.membership is None
        assert not booking.paid
        assert not booking.payment_confirmed


@pytest.mark.parametrize(
    "status,start_date,end_date,has_membership",
    [
        # active, started
        (
            "active", 
            datetime(2020, 2, 25, tzinfo=dt_tz.utc),
            None,
            True
        ),
        # active, cancelling, still current
        (
            "active", 
            datetime(2020, 2, 25, tzinfo=dt_tz.utc),
            datetime(2020, 3, 25, tzinfo=dt_tz.utc),
            True
        ),
        # cancelled
        (
            "cancelled", 
            datetime(2020, 2, 25, tzinfo=dt_tz.utc),
            datetime(2020, 3, 20, tzinfo=dt_tz.utc),
            False
        ),
        # starts in future
        (
            "active", 
            datetime(2020, 4, 25, tzinfo=dt_tz.utc),
            None,
            True
        ),
        # past_due
        (
            "past_due", 
            datetime(2020, 2, 25, tzinfo=dt_tz.utc),
            None,
            True
        ),
        # incompleted
        (
            "incompleted", 
            datetime(2020, 3, 1, tzinfo=dt_tz.utc),
            None,
            False
        ),
    ]
)
@pytest.mark.freeze_time("2020-03-21")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_user_has_membership(seller, configured_stripe_user, status, start_date, end_date, has_membership):
    membership = baker.make(
        Membership, name="Test membership", description="a membership", price=10
    )
    mitem = baker.make(MembershipItem,  membership=membership, quantity=2)

    baker.make(
        UserMembership, 
        membership=membership, 
        user=configured_stripe_user, 
        subscription_status=status,
        start_date=start_date,
        end_date=end_date,
    )
    assert configured_stripe_user.has_membership() == has_membership


def test_subscription_voucher(seller):
    voucher = baker.make(
        StripeSubscriptionVoucher, code="Foo", promo_code_id="", redeem_by=timezone.now() + timedelta(1),
        percent_off=10,
        duration="once",
    )
    voucher_no_expiry = baker.make(
        StripeSubscriptionVoucher, code="foo1", promo_code_id="", redeem_by=None,
        percent_off=5,
        duration="repeating",
        duration_in_months=3
    )
    voucher_expired = baker.make(
        StripeSubscriptionVoucher, code="foo2", promo_code_id="", redeem_by=timezone.now() - timedelta(1),
        amount_off=10, duration="forever"   
    )
    assert not voucher.expired()
    assert str(voucher) == "foo"
    assert voucher.description == "10% off one month's membership"

    assert not voucher_no_expiry.expired()
    assert voucher_no_expiry.description == "5% off 3 months membership"

    assert voucher_expired.expired()
    assert voucher_expired.description == "£10 off"


def test_subscription_voucher_expires_before_next_payment_date(seller, freezer):
    voucher = baker.make(
        StripeSubscriptionVoucher, code="Foo", promo_code_id="",
        expiry_date=datetime(2024, 3, 20, tzinfo=dt_tz.utc),
        percent_off=10,
        duration="once",
    )
    freezer.move_to("2024-02-20")
    # next payment date 2024-02-25
    assert not voucher.expires_before_next_payment_date()

    freezer.move_to("2024-02-25")
    # next payment date 2024-03-25
    assert voucher.expires_before_next_payment_date()

    freezer.move_to("2024-02-29")
    # next payment date 2024-03-25
    assert voucher.expires_before_next_payment_date()


def test_subscription_voucher_create_stripe_code_no_memberships(seller):
    voucher = baker.make(
        StripeSubscriptionVoucher, code="foo", promo_code_id="", redeem_by=timezone.now() + timedelta(1),
        percent_off=10,
        duration="once",
    )
    voucher.create_stripe_code()
    voucher.refresh_from_db()
    assert voucher.promo_code_id == ""


def test_subscription_voucher_create_stripe_code(seller, mocked_responses):
    # creating the product
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
    # create the coupon
    mocked_responses.post(
        "https://api.stripe.com/v1/coupons",
        body=json.dumps(
            {
                "object": "coupon",
                "url": "/v1/coupons",
                "id": "coupon-1",
                "name": "coupon 1",
            }
        ),
        status=200,
        content_type="application/json",
    )
    # create the promo code
    mocked_responses.post(
        "https://api.stripe.com/v1/promotion_codes",
        body=json.dumps(
            {
                "object": "coupon",
                "url": "/v1/coupons",
                "id": "promo-1",
            }
        ),
        status=200,
        content_type="application/json",
    )

    active_membership = baker.make(
        Membership, name="memb-1", description="a membership", price=10, visible=True
    )
    
    voucher = baker.make(
        StripeSubscriptionVoucher, code="foo", promo_code_id="", redeem_by=timezone.now() + timedelta(1),
        percent_off=10,
        duration="once",
    )
    
    voucher.memberships.add(active_membership)
    voucher.create_stripe_code()

    voucher.refresh_from_db()
    assert voucher.promo_code_id == "promo-1"


def test_subscription_voucher_make_active(seller, mocked_responses):
    # promo code endpoint called to update active status
    mocked_responses.post(
        "https://api.stripe.com/v1/promotion_codes/promo-1",
        body=json.dumps(
            {
                "object": "coupon",
                "url": "/v1/coupons",
                "id": "promo-1",
            }
        ),
        status=200,
        content_type="application/json",
    )

    voucher = baker.make(
        StripeSubscriptionVoucher, code="foo", 
        promo_code_id="promo-1", redeem_by=timezone.now() + timedelta(1),
        percent_off=10,
        duration="once",
        active=False
    )
    voucher.active = True
    voucher.save()

    voucher.active = False
    voucher.save()

    mocked_responses.assert_call_count("https://api.stripe.com/v1/promotion_codes/promo-1", 2)
