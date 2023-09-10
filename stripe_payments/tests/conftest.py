import pytest
import os
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site

from model_bakery import baker
from stripe_payments.models import Invoice, Seller


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


@pytest.fixture
def get_mock_payment_intent():
    def payment_intent(webhook_event_type=None, **params):
        defaults = {
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
    return payment_intent


@pytest.fixture
def get_mock_webhook_event(seller, get_mock_payment_intent):
    def mock_webhook_event(**params):
        webhook_event_type = params.pop("webhook_event_type", "payment_intent.succeeded")
        mock_event = Mock(
            account=seller.stripe_user_id,
            data=Mock(object=get_mock_payment_intent(webhook_event_type, **params)), type=webhook_event_type
        )
        return mock_event
    return mock_webhook_event
