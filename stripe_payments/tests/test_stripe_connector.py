import json
import pytest

from model_bakery import baker

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


def test_connector_get_or_create_customer_id_on_profile(configured_user, seller):
    configured_user.userprofile.stripe_customer_id = "cus_123"
    configured_user.userprofile.save()
    connector = StripeConnector()
    connector.get_or_create_stripe_customer(configured_user) == "cus_123"
