import json
import pytest
import stripe

from datetime import datetime
from datetime import timezone as datetime_tz
from unittest.mock import patch
from urllib.parse import parse_qs

from model_bakery import baker

from stripe_payments.utils import StripeConnector
from responses import matchers


pytestmark = pytest.mark.django_db


def test_connector_get_or_create_customer_no_existing_customers(configured_user, seller, mocked_responses):
    mocked_responses.get(
        "https://api.stripe.com/v1/customers",
        body=json.dumps(
            {
                "object": "list",
                "url": "/v1/customers",
                "has_more": False,
                "data": [],
            }
        ),
        status=200,
        content_type="application/json",
    )
    mocked_responses.post(
        "https://api.stripe.com/v1/customers",
        body=json.dumps(
            {
                "id": "cus_NffrFeUfNV2Hib",
                "object": "customer",
                "email": configured_user.email,
            }
        ),
        status=200,
        content_type="application/json",
    )
        
    connector = StripeConnector()
    connector.get_or_create_stripe_customer(configured_user) ==  "cus_NffrFeUfNV2Hib"
    
    configured_user.refresh_from_db()
    assert configured_user.userprofile.stripe_customer_id ==  "cus_NffrFeUfNV2Hib"


def test_connector_get_or_create_customer_existing_customer(configured_user, seller, mocked_responses):
    mocked_responses.get(
        "https://api.stripe.com/v1/customers",
        body=json.dumps(
            {
                "object": "list",
                "url": "/v1/customers",
                "has_more": False,
                "data": [{"id": "cus_NffrFeUfNV2Hia"}],
            }
        ),
        status=200,
        content_type="application/json",
    )
    
    connector = StripeConnector()
    connector.get_or_create_stripe_customer(configured_user) == "cus_NffrFeUfNV2Hia"
    
    configured_user.refresh_from_db()
    assert configured_user.userprofile.stripe_customer_id ==  "cus_NffrFeUfNV2Hia"


def test_connector_get_or_create_customer_id_on_profile(configured_user, seller):
    configured_user.userprofile.stripe_customer_id = "cus_123"
    configured_user.userprofile.save()
    connector = StripeConnector()
    connector.get_or_create_stripe_customer(configured_user) == "cus_123"


def test_connector_create_stripe_product(seller, mocked_responses):
    mocked_responses.post(
        "https://api.stripe.com/v1/products",
        body=json.dumps(
            {
                "id": "prod_123c",
                "object": "product",
                "active": True,
                "created": 1678833149,
                "default_price": 10,
                "description": "a membership",
                "images": [],
                "features": [],
                "livemode": False,
                "metadata": {},
                "name": "Memb 1",
                "package_dimensions": None,
                "shippable": None,
                "statement_descriptor": None,
                "tax_code": None,
                "unit_label": None,
                "updated": 1678833149,
                "url": None
            }
        ),
        status=200,
        content_type="application/json",
    )
    connector = StripeConnector()
    product = connector.create_stripe_product(
        "prod_123c", "Memb 1", "a membership", 10
    )
    assert isinstance(product, stripe.Product)
    calls = mocked_responses.calls
    assert len(calls) == 1
    call = calls[0]
    body = call.request.body
    parsed = parse_qs(body)
    assert parsed == {
        'id': ['prod_123c'], 
        'name': ['Memb 1'], 
        'description': ['a membership'], 
        'default_price_data[unit_amount]': ['1000'], 
        'default_price_data[currency]': ['gbp'], 
        'default_price_data[recurring][interval]': ['month']
    }


@patch("stripe_payments.utils.stripe.Product.create", side_effect=stripe.InvalidRequestError("err", 200))
def test_connector_create_stripe_product_error(mock_create, seller):
    connector = StripeConnector()
    with pytest.raises(stripe.InvalidRequestError):
        product = connector.create_stripe_product(
            "prod_123c", "Memb 1", "a membership", 10
        )


@patch("stripe_payments.utils.stripe.Product.create", side_effect=stripe.InvalidRequestError("Error: already exists", 200))
def test_connector_create_stripe_product_already_exists_error(mock_create, seller, mocked_responses):
    connector = StripeConnector()

    # If already exists error, call prices list with the product
    mocked_responses.get(
        "https://api.stripe.com/v1/prices",
        body=json.dumps(
            {
                "object": "list",
                "data": [
                    {"id": "price_1"}
                ]
            }
        ),
        status=200,
        content_type="application/json",
    )
    # and then products update to modify the price
    mocked_responses.post(
        "https://api.stripe.com/v1/products/prod_123c",
        body=json.dumps(
            {
                "id": "prod_123c",
            }
        ),
        status=200,
        content_type="application/json",
    )
    connector.create_stripe_product(
        "prod_123c", "Memb 1", "a membership", 10
    )


def test_update_stripe_customer(seller, mocked_responses):
    mocked_responses.post(
        "https://api.stripe.com/v1/customers/cus-1",
        body=json.dumps(
            {
                "object": "customer",
                "id": "cus-1"
            }
        ),
        status=200,
        content_type="application/json",
    )
    connector = StripeConnector()
    connector.update_stripe_customer("cus-1")
    assert len(mocked_responses.calls) == 1


def test_get_payment_intent(seller, mocked_responses):
    mocked_responses.get(
        "https://api.stripe.com/v1/payment_intents/pi-1",
        body=json.dumps(
            {
                "object": "payment_intent",
                "id": "pi-1"
            }
        ),
        status=200,
        content_type="application/json",
    )
    connector = StripeConnector()
    pi = connector.get_payment_intent("pi-1")
    assert isinstance(pi, stripe.PaymentIntent) 
    assert len(mocked_responses.calls) == 1


def test_getsetup_intent(seller, mocked_responses):
    mocked_responses.get(
        "https://api.stripe.com/v1/setup_intents/su-1",
        body=json.dumps(
            {
                "object": "setup_intent",
                "id": "su-1"
            }
        ),
        status=200,
        content_type="application/json",
    )
    connector = StripeConnector()
    pi = connector.get_setup_intent("su-1")
    assert isinstance(pi, stripe.SetupIntent) 
    assert len(mocked_responses.calls) == 1


def test_get_subscriptions_for_customer_no_subscriptions(seller, mocked_responses):
    mocked_responses.get(
        "https://api.stripe.com/v1/subscriptions",
        body=json.dumps(
            {
                "object": "list",
                "data": [],
                "has_more": False,
            }
        ),
        status=200,
        content_type="application/json",
    )
    connector = StripeConnector()
    subscriptions = connector.get_subscriptions_for_customer("cus-1")
    assert subscriptions == {}


def test_get_subscriptions_for_customer(seller, mocked_responses):
    mocked_responses.get(
        "https://api.stripe.com/v1/subscriptions",
        body=json.dumps(
            {
                "object": "list",
                "data": [
                    {
                        "object": "subscription",
                        "id": "sub-1"
                    }
                ],
                "has_more": False,
            }
        ),
        status=200,
        content_type="application/json",
    )
    connector = StripeConnector()
    subscriptions = connector.get_subscriptions_for_customer("cus-1")
    assert [
        s.id for s in subscriptions.values()
    ] == ["sub-1"]


def test_get_subscriptions_for_customer_paginated(seller, mocked_responses):
    mocked_responses.get(
        "https://api.stripe.com/v1/subscriptions",
        body=json.dumps(
            {
                "object": "list",
                "data": [
                    {
                        "object": "subscription",
                        "id": "sub-1"
                    }
                ],
                "has_more": True,
            }
        ),
        status=200,
        content_type="application/json",
    )
    mocked_responses.get(
        "https://api.stripe.com/v1/subscriptions",
        body=json.dumps(
            {
                "object": "list",
                "data": [
                    {
                        "object": "subscription",
                        "id": "sub-2"
                    }
                ],
                "has_more": False,
            }
        ),
        status=200,
        content_type="application/json",
    )
    connector = StripeConnector()
    subscriptions = connector.get_subscriptions_for_customer("cus-1")
    assert [
        s.id for s in subscriptions.values()
    ] == ["sub-1", "sub-2"]

@pytest.mark.parametrize(
    "now,backdate,default_payment_method,expected_billing_cycle_anchor,expected_backdate_start_date,expected_proration_behavior",
    [
        (   
            # backdate
            datetime(2024, 4, 1, tzinfo=datetime_tz.utc), True, None,
            int(datetime(2024, 4, 25, tzinfo=datetime_tz.utc).timestamp()),
            int(datetime(2024, 3, 25, tzinfo=datetime_tz.utc).timestamp()),
            "create_prorations"
        ),
        (
            # no backdating
            datetime(2024, 4, 1, tzinfo=datetime_tz.utc), False, None,
            int(datetime(2024, 4, 25, tzinfo=datetime_tz.utc).timestamp()),
            None,
            "none"
        ),
        (   
            # backdating, but after 25th
            datetime(2024, 4, 26, tzinfo=datetime_tz.utc), True, None,
            int(datetime(2024, 5, 25, tzinfo=datetime_tz.utc).timestamp()),
            int(datetime(2024, 4, 25, tzinfo=datetime_tz.utc).timestamp()),
            "create_prorations"
        ),
    ]
)
def test_create_subscription(
    freezer,seller, mocked_responses, now, backdate, default_payment_method,
    expected_billing_cycle_anchor, expected_backdate_start_date, expected_proration_behavior
):
    freezer.move_to(now)
    mocked_responses.post(
        "https://api.stripe.com/v1/subscriptions",
        body=json.dumps(
            {
                "object": "subscription",
                "id": "sub-1",
            }
        ),
        status=200,
        content_type="application/json",
    )
    connector = StripeConnector()
    subscription = connector.create_subscription(
        "cus-1", "price-1", backdate=backdate, default_payment_method=default_payment_method
    )
    assert isinstance(subscription, stripe.Subscription)
    assert len(mocked_responses.calls) == 1
    call = mocked_responses.calls[0]
    parsed = parse_qs(call.request.body)
    expected = {
        'customer': ['cus-1'], 
        'items[0][price]': ['price-1'],
        'billing_cycle_anchor': [str(expected_billing_cycle_anchor)], 
        'proration_behavior': [expected_proration_behavior],
        # always the same
        'items[0][quantity]': ['1'],
        'payment_behavior': ['default_incomplete'],
        'payment_settings[save_default_payment_method]': ['on_subscription'],
        'expand[0]': ['latest_invoice.payment_intent'], 
        'expand[1]': ['pending_setup_intent'],
    }
    if expected_backdate_start_date:
        expected["backdate_start_date"] = [str(expected_backdate_start_date)]
    assert parsed == expected


