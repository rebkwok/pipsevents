import json

from datetime import datetime

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
                "default_price": "price_1"
            }
        ),
        status=200,
        content_type="application/json",
    )
    membership = baker.make(Membership, name="memb 1", description="a membership", price=10)
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
                "default_price": "price_1"
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
                "default_price": "price_2"
            }
        ),
        status=200,
        content_type="application/json",
    )

    membership = baker.make(Membership, name="memb 1", description="a membership", price=10)
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
                "default_price": "price_1"
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
                "default_price": "price_2"
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
                          "items": [{"price": 2000, "quantity": 1}]
                     }
                ]
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
                "subscription": "subsc-1"
            }
        ),
        status=200,
        content_type="application/json",
    )
   

    membership = baker.make(Membership, name="memb 1", description="a membership", price=10)
    assert membership.stripe_product_id == "memb-1"
    assert membership.stripe_price_id == "price_1"

    baker.make(UserMembership, membership=membership, subscription_status="active", subscription_id="subsc-1")
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
                "default_price": "price_1"
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
                "default_price": "price_1"
            }
        ),
        status=200,
        content_type="application/json",
    )

    membership = baker.make(Membership, name="memb 1", description="a membership", price=10)
    assert membership.stripe_product_id == "memb-1"
    assert membership.stripe_price_id == "price_1"

    membership.name = "memb 2"
    membership.save()

    assert membership.stripe_product_id == "memb-1"
    assert membership.stripe_price_id == "price_1"
    assert membership.name == "memb 2"


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_item_str():
    membership = baker.make(Membership, name="Test membership", description="a membership", price=10)
    event_type = baker.make_recipe("booking.event_type_PC", subtype="Level class")
    mitem = baker.make(MembershipItem, event_type=event_type, membership=membership, quantity=4)
    assert str(mitem) == "Test membership - Level class - 4"


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_user_membership_str(seller):
    membership = baker.make(Membership, name="Test membership", description="a membership", price=10)
    user_membership = baker.make(UserMembership, membership=membership, user__username="test", )
    assert str(user_membership) == "test - Test membership"


@pytest.mark.parametrize(
    "start_date,end_date,status,is_active",
    [
        # started, no end, status active
        (datetime(2020, 5, 20), None, "active", True),
        # started, end, status active
        (datetime(2020, 2, 20), datetime(2020, 5, 20), "active", True),
        # started, no end, status cancelled
        (datetime(2020, 5, 20), None, "canceled", False),
    ]
)
@pytest.mark.freeze_time('2020-05-21')
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_user_membership_is_active(seller, start_date, end_date, status, is_active):
    membership = baker.make(Membership, name="Test membership", description="a membership", price=10)
    user_membership = baker.make(UserMembership, membership=membership, start_date=start_date, end_date=end_date, subscription_status=status)
    assert user_membership.is_active() == is_active


@pytest.mark.parametrize(
    "now,is_active",
    [
        (datetime(2020, 5, 25), True),
        (datetime(2020, 5, 28), True),
        (datetime(2020, 5, 30), False),
    ]
)
@pytest.mark.freeze_time('2020-05-21')
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_user_membership_past_due_is_active(freezer, seller, now, is_active):
    freezer.move_to(now)
    membership = baker.make(Membership, name="Test membership", description="a membership", price=10)
    user_membership = baker.make(UserMembership, membership=membership, start_date=datetime(2020, 4, 20), subscription_status="past_due")
    assert user_membership.is_active() == is_active


@pytest.mark.freeze_time('2020-05-21')
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_user_membership_valid_for_event(seller):
    membership = baker.make(Membership, name="Test membership", description="a membership", price=10)
    pc_event_type = baker.make_recipe("booking.event_type_PC", subtype="Level class")
    pp_event_type = baker.make_recipe("booking.event_type_PP", subtype="Pole practice")
    baker.make(MembershipItem, event_type=pc_event_type, membership=membership, quantity=4)

    user_membership = baker.make(UserMembership, membership=membership, start_date=datetime(2020, 5, 1), subscription_status="active")

    # only valid for correct event type 
    pc_event = baker.make(Event, event_type=pc_event_type, date=datetime(2020, 5, 28))
    pp_event = baker.make(Event, event_type=pp_event_type, date=datetime(2020, 5, 28))
    assert user_membership.valid_for_event(pc_event)
    assert not user_membership.valid_for_event(pp_event)

    # already booked for this event type this month
    baker.make(
        "booking.booking", user=user_membership.user, event__event_type=pc_event_type, event__date=datetime(2020, 5, 20),
        membership=user_membership, _quantity=3
    )
    assert user_membership.valid_for_event(pc_event)

    baker.make(
        "booking.booking", user=user_membership.user, event__event_type=pc_event_type, event__date=datetime(2020, 5, 15),
        membership=user_membership
    )
    assert not user_membership.valid_for_event(pc_event)


@pytest.mark.parametrize(
    "event_date,end_date,is_valid",
    [
        (datetime(2020, 5, 1, 10, 0), None, True),
        (datetime(2020, 5, 31, 10, 0), None, True),
        (datetime(2020, 6, 1, 10, 0), None, True), # event date is after this month, but still valid because no end date
        (datetime(2020, 6, 1, 10, 0), datetime(2020, 6, 1), False),
        (datetime(2020, 4, 30, 10, 0), None, False),
    ]
)
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_user_membership_valid_for_event_dates(seller, event_date, end_date, is_valid):
    membership = baker.make(Membership, name="Test membership", description="a membership", price=10)
    pc_event_type = baker.make_recipe("booking.event_type_PC", subtype="Level class")
    baker.make(MembershipItem, event_type=pc_event_type, membership=membership, quantity=4)

    user_membership = baker.make(
        UserMembership, membership=membership, start_date=datetime(2020, 5, 1), end_date=end_date, subscription_status="active"
    )

    # only valid for correct event type 
    pc_event = baker.make(Event, event_type=pc_event_type, date=event_date)
    assert user_membership.valid_for_event(pc_event) == is_valid