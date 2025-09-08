import json
import pytest
import stripe

from datetime import datetime
from datetime import timezone as datetime_tz
from unittest.mock import patch
from urllib.parse import parse_qs

from model_bakery import baker

from django.utils import timezone

from stripe_payments.utils import StripeConnector


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


def test_connector_get_or_create_customer_id_on_profile(configured_user, seller, mocked_responses):
    # If a user has a customer id on their profile, we still check that it's valid
    mocked_responses.get(
        "https://api.stripe.com/v1/customers/cus_123",
        body=json.dumps(
            {
                "object": "customer",
                "url": "/v1/customers/cus_123",
                "id": "cus_123",
            }
        ),
        status=200,
        content_type="application/json",
    )
    configured_user.userprofile.stripe_customer_id = "cus_123"
    configured_user.userprofile.save()
    connector = StripeConnector()
    connector.get_or_create_stripe_customer(configured_user) == "cus_123"


def test_connector_get_or_create_customer_id_on_profile_deleted(configured_user, seller, mocked_responses):
    # If a user has a customer id on their profile, we still check that it's valid
    configured_user.userprofile.stripe_customer_id = "cus_123"
    configured_user.userprofile.save()
    mocked_responses.get(
        "https://api.stripe.com/v1/customers/cus_123",
        body=json.dumps(
            {
                "object": "customer",
                "url": "/v1/customers/cus_123",
                "id": "cus_123",
                "deleted": True,
            }
        ),
        status=200,
        content_type="application/json",
    )
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
    connector.get_or_create_stripe_customer(configured_user) == "cus_NffrFeUfNV2Hib"
    configured_user.refresh_from_db()
    assert configured_user.userprofile.stripe_customer_id == "cus_NffrFeUfNV2Hib"


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


def test_connector_archive_stripe_product(seller, mocked_responses):
    mocked_responses.post(
        "https://api.stripe.com/v1/products/prod_123c",
        body=json.dumps(
            {
                "id": "prod_123c",
                "object": "product",
                "active": False,
                "created": 1678833149,
                "default_price": "price_1",
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
    mocked_responses.post(
        "https://api.stripe.com/v1/prices/price_1",
        body=json.dumps(
            {
                "id": "price_1",
                "object": "price",
                "active": False,
            }
        ),
        status=200,
        content_type="application/json",
    )

    connector = StripeConnector()
    product = connector.archive_stripe_product("prod_123c", "price_1")
    assert isinstance(product, stripe.Product)
    calls = mocked_responses.calls
    assert len(calls) == 2
    for call in calls:
        body = call.request.body
        parsed = parse_qs(body)
        assert parsed == {'active': ['False']}


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
    freezer, seller, mocked_responses, now, backdate, default_payment_method,
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
        'expand[1]': ['latest_invoice.discounts'],
        'expand[2]': ['pending_setup_intent'],
    }
    if expected_backdate_start_date:
        expected["backdate_start_date"] = [str(expected_backdate_start_date)]
    assert parsed == expected


def test_cancel_subscription_immediately(seller, mocked_responses):
    mocked_responses.delete(
        "https://api.stripe.com/v1/subscriptions/sub-1",
        body=json.dumps(
            {
                "id": "sub_1MlPf9LkdIwHu7ixB6VIYRyX",
                "object": "subscription",
                "application": None,
                "billing_cycle_anchor": 1678768838,
                "billing_thresholds": None,
                "cancel_at": None,
                "cancel_at_period_end": False,
                "canceled_at": timezone.now().timestamp(),
                "cancellation_details": {
                    "comment": None,
                    "feedback": None,
                    "reason": "cancellation_requested"
                },
                "customer": "cus-1"
            }
        )
    )
    connector = StripeConnector()
    subscription = connector.cancel_subscription(
        "sub-1", cancel_immediately=True
    )
    assert isinstance(subscription, stripe.Subscription)


def test_cancel_subscription_on_schedule(seller, mocked_responses):
    # get subscription
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
                        "start_date": datetime(2024, 5, 25).timestamp(),
                        "end_date": datetime(2024, 6, 25).timestamp(),
                        "items": [{"price": 1000, "quantity": 2}],
                    },
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
    # update the schedule to
    mocked_responses.post(
        "https://api.stripe.com/v1/subscription_schedules/sub_sched-1",
        body=json.dumps(
            {
                "object": "subscription_schedule",
                "url": "/v1/subscription_schedules",
                "id": "sub_sched-1",
                "subscription": {
                    "object": "subscription",
                    "id": "subsc-1"
                },
            }
        ),
        status=200,
        content_type="application/json",
    )

    connector = StripeConnector()
    subscription = connector.cancel_subscription(
        "subsc-1", cancel_immediately=False
    )
    assert isinstance(subscription, stripe.Subscription)
    last_call = mocked_responses.calls[-1]
    parsed = parse_qs(last_call.request.body)
    # called with the schedule details and end behvaiour cancel
    expected = {
        'end_behavior': ['cancel'], 
        'phases[0][items][0][price]': ['2000'], 
        'phases[0][items][0][quantity]': ['1'], 
        'phases[0][start_date]': [str(datetime(2024, 6, 25).timestamp())], 
        'phases[0][end_date]': [str(datetime(2024, 7, 25).timestamp())], 
        'phases[0][proration_behavior]': ['none'], 
        'expand[0]': ['subscription']
    }
    assert parsed == expected


def test_stripe_customer_portal_existing_config(seller, mocked_responses):
    # list configs
    mocked_responses.get(
        "https://api.stripe.com/v1/billing_portal/configurations?active=True",
        body=json.dumps(
            {
                "object": "list",
                "url": "https://api.stripe.com/v1/billing_portal/configurations",
                "data": [
                    {
                        "id": "bpc_1",
                        "object": "billing_portal.configuration",
                        "active": True,
                        "business_profile": {
                            "headline": None,
                            "privacy_policy_url": "https://example.com/privacy",
                            "terms_of_service_url": "https://example.com/terms"
                        },
                        "default_return_url": "https://thewatermelonstudio.co.uk/",
                        "features": {
                            "customer_update": {"allowed_updates": ["email", "name", "address"], "enabled": True},
                            "payment_method_update": {"enabled": True},
                            "invoice_history": {"enabled": True},
                            "subscription_cancel": {"enabled": False},
                            "subscription_update": {"enabled": False},
                        }
                    },
                    {
                        "id": "bpc_2",
                        "object": "billing_portal.configuration",
                        "active": True,
                        "business_profile": {
                            "headline": None,
                            "privacy_policy_url": "https://booking.thewatermelonstudio.co.uk/data-privacy-policy/",
                            "terms_of_service_url": "https://www.thewatermelonstudio.co.uk/t&c.html"
                        },
                        "default_return_url": "https://booking.thewatermelonstudio.co.uk/accounts/profile",
                        "features": {
                            "customer_update": {"allowed_updates": ["email", "name", "address"], "enabled": True},
                            "payment_method_update": {"enabled": True},
                            "invoice_history": {"enabled": True},
                            "subscription_cancel": {"enabled": False},
                            "subscription_update": {"enabled": False},
                        }
                    },
                    
                ]
            }
        ),
        status=200,
        content_type="application/json",
    )

    # get customer portal session
    mocked_responses.post(
        "https://api.stripe.com/v1/billing_portal/sessions",
        body=json.dumps(
            {
                "id": "bps_1",
                "object": "billing_portal.session",
                "url": "https://example.com/sessionid"
            }
        )
    )    

    connector = StripeConnector()
    assert connector.customer_portal_url("cus-1") ==  "https://example.com/sessionid"
    # session create called with bpc_2
    last_call = mocked_responses.calls[-1]
    parsed = parse_qs(last_call.request.body)
    assert parsed == {'customer': ['cus-1'], 'configuration': ['bpc_2']}


def test_stripe_customer_portal_existing_mismatched_config(seller, mocked_responses):
    # list configs
    mocked_responses.get(
        "https://api.stripe.com/v1/billing_portal/configurations?active=True",
        body=json.dumps(
            {
                "object": "list",
                "url": "https://api.stripe.com/v1/billing_portal/configurations",
                "data": [
                    {
                        "id": "bpc_1",
                        "object": "billing_portal.configuration",
                        "active": True,
                        "business_profile": {
                            "headline": None,
                            "privacy_policy_url": "https://booking.thewatermelonstudio.co.uk/data-privacy-policy/",
                            "terms_of_service_url": "https://www.thewatermelonstudio.co.uk/t&c.html"
                        },
                        "default_return_url": "https://booking.thewatermelonstudio.co.uk/accounts/profile",
                        "features": {
                            "customer_update": {"allowed_updates": ["email", "name", "address"], "enabled": True},
                            "payment_method_update": {"enabled": True},
                            "invoice_history": {"enabled": True},
                            "subscription_cancel": {"enabled": False},
                            "subscription_update": {"enabled": True},
                        }
                    },
                    
                ]
            }
        ),
        status=200,
        content_type="application/json",
    )
    # modifies the config
    mocked_responses.post(
        "https://api.stripe.com/v1/billing_portal/configurations/bpc_1",
        body=json.dumps(
            {
                "id": "bpc_1",
                "object": "billing_portal.configuration"
            }
        )
    )

    # get customer portal session
    mocked_responses.post(
        "https://api.stripe.com/v1/billing_portal/sessions",
        body=json.dumps(
            {
                "id": "bps_1",
                "url": "https://example.com/sessionid"
            }
        )
    )    

    connector = StripeConnector()
    assert connector.customer_portal_url("cus-1") ==  "https://example.com/sessionid"    

    last_call = mocked_responses.calls[-1]
    parsed = parse_qs(last_call.request.body)
    assert parsed == {'customer': ['cus-1'], 'configuration': ['bpc_1']}


def test_stripe_customer_portal_no_existing_config(seller, mocked_responses):
    # list configs
    mocked_responses.get(
        "https://api.stripe.com/v1/billing_portal/configurations?active=True",
        body=json.dumps(
            {
                "object": "list",
                "url": "https://api.stripe.com/v1/billing_portal/configurations",
                "data": [
                    {
                        "id": "bpc_1",
                        "object": "billing_portal.configuration",
                        "active": True,
                        "business_profile": {
                            "headline": None,
                            "privacy_policy_url": "https://booking.thewatermelonstudio.co.uk/data-privacy-policy/",
                            "terms_of_service_url": "https://www.thewatermelonstudio.co.uk/t&c.html"
                        },
                        "default_return_url": "https:/foo",
                        "features": {
                            "customer_update": {"allowed_updates": ["email", "name", "address"], "enabled": True},
                            "payment_method_update": {"enabled": True},
                            "invoice_history": {"enabled": True},
                            "subscription_cancel": {"enabled": False},
                            "subscription_update": {"enabled": True},
                        }
                    },
                    
                ]
            }
        ),
        status=200,
        content_type="application/json",
    )
    # creates new config
    mocked_responses.post(
        "https://api.stripe.com/v1/billing_portal/configurations",
        body=json.dumps(
            {
                "id": "bpc_1",
                "object": "billing_portal.configuration"
            }
        )
    )

    # get customer portal session
    mocked_responses.post(
        "https://api.stripe.com/v1/billing_portal/sessions",
        body=json.dumps(
            {
                "id": "bps_1",
                "url": "https://example.com/sessionid"
            }
        )
    )    

    connector = StripeConnector()
    assert connector.customer_portal_url("cus-1") ==  "https://example.com/sessionid"    

    last_call = mocked_responses.calls[-1]
    parsed = parse_qs(last_call.request.body)
    assert parsed == {'customer': ['cus-1'], 'configuration': ['bpc_1']}  


def test_connector_get_promo_code(seller, mocked_responses):
    mocked_responses.get(
        "https://api.stripe.com/v1/promotion_codes/promo_1",
        body=json.dumps(
            {
                "id": "promo_1",
            }
        )
    ) 
    mocked_responses.get(
        "https://api.stripe.com/v1/promotion_codes/promo_unknown",
        body=json.dumps(
            {
                "error": {
                    "code": "resource_missing",
                    "doc_url": "https://stripe.com/docs/error-codes/resource-missing",
                    "message": "No such promotion code: 'promo_unknown'",
                    "param": "promotion_code",
                    "request_log_url": "https://dashboard.stripe.com/test/logs/req_IeybpNvVnJBTT8?t=1722423791",
                    "type": "invalid_request_error"
                }
            }
        ),
        status=404
    )    

    connector = StripeConnector()
    promo_code = connector.get_promo_code("promo_1")
    assert isinstance(promo_code, stripe.PromotionCode)

    assert connector.get_promo_code("promo_unknown") is None


def test_connector_get_upcoming_invoice(seller, mocked_responses):
    mocked_responses.get(
        "https://api.stripe.com/v1/invoices/upcoming?subscription=sub-1&expand[0]=discounts",
        body=json.dumps(
            {
                "object": "invoice",
                "currency": "gbp",
                "customer": "cus-1",
                "discount": None,
                "subscription": "sub-1",
                "total": 0,
            }
        )
    )
    connector = StripeConnector()
    invoice = connector.get_upcoming_invoice("sub-1")
    assert isinstance(invoice, stripe.Invoice)

    assert len(mocked_responses.calls) == 1


def test_connector_add_discount_to_subscription(seller, mocked_responses):
    mocked_responses.post(
        "https://api.stripe.com/v1/subscriptions/sub-1",
        body=json.dumps(
            {
                "id": "sub-1",
                "object": "subscription",
                "customer": "cus-1",
                "discount": {"promotion_code": "promo-1"}
            }
        )
    )
    connector = StripeConnector()
    connector.add_discount_to_subscription(
        "sub-1", promo_code_id="promo-1"
    )
    assert_call_body(
        mocked_responses.calls[0],
        {'discounts[0][promotion_code]': ['promo-1']}
    )


def test_connector_remove_discount_from_subscription(seller, mocked_responses):
    mocked_responses.delete(
        "https://api.stripe.com/v1/subscriptions/sub-1/discount",
        body=json.dumps(
            {
                "object": "discount",
                "deleted": True,
            }
        )
    )
    connector = StripeConnector()
    connector.remove_discount_from_subscription("sub-1")
    assert_call_body(mocked_responses.calls[0], {})


def assert_call_body(call, expected):
    parsed = parse_qs(call.request.body)
    assert parsed == expected