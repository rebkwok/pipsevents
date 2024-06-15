from datetime import datetime
import pytest
import os
import responses
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site

from model_bakery import baker
from stripe_payments.models import Invoice, Seller
from stripe_payments.tests.mock_connector import MockConnector


User = get_user_model()

@pytest.fixture
def configured_user():
    user = User.objects.create_user(
            username='test', 
            first_name="Test", 
            last_name="User", 
            email='test@test.com', 
            password='test'
        )
    yield user


@pytest.fixture
def configured_stripe_user():
    user = User.objects.create_user(
            username='stripe_customer', 
            first_name="Test", 
            last_name="User", 
            email='stripetest@test.com', 
            password='test'
        )
    user.userprofile.stripe_customer_id = "cus-1"
    user.userprofile.save()
    yield user


@pytest.fixture
def superuser():
    yield User.objects.create_superuser(
        username='test_superuser', 
        first_name="Super", 
        last_name="User", 
        email='super@test.com', 
        password='test'
    )


@pytest.fixture
def seller():
    yield baker.make(Seller, site=Site.objects.get_current(), stripe_user_id="id123")


@pytest.fixture
def mocked_responses():
    with responses.RequestsMock() as rsps:
        yield rsps


@pytest.fixture
def invoice_keyenv():
    old = os.environ.get("INVOICE_KEY")
    os.environ["INVOICE_KEY"] = "test"
    yield os.environ["INVOICE_KEY"]
    if old is None:  # pragma: no cover
        del os.environ["INVOICE_KEY"]
    else:  # pragma: no cover
        os.environ["INVOICE_KEY"] = old


@pytest.fixture
def send_all_studio_emails(settings):
    settings.SEND_ALL_STUDIO_EMAILS = True


@pytest.fixture
def invoice(configured_user):
    yield baker.make(
        Invoice, invoice_id="foo", amount=10,
        username=configured_user.email, stripe_payment_intent_id="mock-intent-id"
    )


def get_mock_payment_intent(webhook_event_type=None, **params):
    defaults = {
        "object": "payment_intent",
        "id": "mock-intent-id",
        "amount": 1000,
        "description": "",
        "status": "succeeded",
        "metadata": {},
        "currency": "gbp",
        "client_secret": "secret",
        "charges": Mock(data=[{"billing_details": {"email": "stripe-payer@test.com"}}])
    }
    options = {**defaults, **params}
    if webhook_event_type == "payment_intent.payment_failed":
        options["last_payment_error"] = {'error': 'an error'}
    return Mock(**options)
    

class MockSubscription:
    def __init__(self, **init_dict):
        for k, v in init_dict.items():
            setattr(self, k, v)
    
    def __getitem__(self, item):
        return getattr(self, item)


def get_mock_subscription(webhook_event_type, **params):
    defaults = {
        "object": "subscription",
        "id": "id",
        "status": "active",
        "items": Mock(data=[Mock(price=Mock(id="price_1234"))]),  # matches the id returned by the MockStripeConnector
        "customer": "cus-1",
        "start_date": datetime(2024, 6, 25).timestamp(),
        "billing_cycle_anchor": datetime(2024, 7, 25).timestamp(),
        "metadata": {},
    }
    options = {**defaults, **params}
    return MockSubscription(**options)


@pytest.fixture
def get_mock_webhook_event(seller):
    def mock_webhook_event(**params):
        webhook_event_type = params.pop("webhook_event_type", "payment_intent.succeeded")
        seller_id = params.pop("seller_id", seller.stripe_user_id)
        if webhook_event_type in ["payment_intent.succeeded", "payment_intent.payment_failed"]:
            object = get_mock_payment_intent(webhook_event_type, **params)
        elif webhook_event_type in ["customer.subscription.created", "customer.subscription.deleted", "customer.subscription.updated"]:
            object = get_mock_subscription(webhook_event_type, **params)
        else:
            object = Mock(**{"metadata": {}, **params})
        mock_event = Mock(
            account=seller_id,
            data=Mock(object=object), 
            type=webhook_event_type,
        )
        return mock_event
    return mock_webhook_event


@pytest.fixture
def block_gift_voucher():
    # setup gift voucher
    blocktype = baker.make_recipe("booking.blocktype", cost=10)
    block_voucher = baker.make_recipe(
        "booking.block_gift_voucher", purchaser_email="test@test.com", activated=True,
    )
    block_voucher.block_types.add(blocktype)
    blocktype = block_voucher.block_types.first()    
    baker.make("booking.GiftVoucherType", block_type=blocktype)
    yield block_voucher
