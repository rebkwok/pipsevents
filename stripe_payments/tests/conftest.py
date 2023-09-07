import pytest
import os

from model_bakery import baker
from stripe_payments.models import Invoice

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
def membership(invoice, configured_user):
    yield baker.make_recipe(
        'booking.membership', paid=False, invoice=invoice, user=configured_user
    )
