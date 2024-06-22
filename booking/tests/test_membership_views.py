from datetime import datetime
from datetime import timezone as datetime_tz
from unittest.mock import patch, MagicMock, Mock

import pytest

from django.urls import reverse

from model_bakery import baker

from stripe_payments.tests.mock_connector import MockConnector

from booking.models import Membership, UserMembership

pytestmark = pytest.mark.django_db

create_url = reverse("membership_create")
checkout_url = reverse("membership_checkout")
stripe_subscribe_url = reverse("subscription_create")


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_create_get_required_login(client, seller):
    baker.make(Membership, name="m1")
    resp = client.get(create_url)
    assert resp.status_code == 302
    assert "login" in resp.url


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_create_get(client, seller, configured_user):
    client.force_login(configured_user)
    m1 = baker.make(Membership, name="m1", active=True)
    m2 = baker.make(Membership, name="m2", active=True)
    baker.make(Membership, name="m3", active=False)
    resp = client.get(create_url)
    assert resp.status_code == 200
    form = resp.context_data["form"]
    assert set(form.fields["membership"].queryset) == {m1, m2}
    assert form.fields["backdate"].choices == [(1, "February"), (0, "March")]


@pytest.mark.freeze_time("2024-02-25 10:00")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_create_after_25th_of_month(client, seller, configured_user):
    client.force_login(configured_user)
    baker.make(Membership, name="m1", active=True)
    resp = client.get(create_url)
    assert resp.status_code == 200
    form = resp.context_data["form"]
    assert form.fields["backdate"].choices == [(0, "March")]


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_create_user_has_cancelled_membership(client, seller, configured_user):
    client.force_login(configured_user)
    m1 = baker.make(Membership, name="m1", active=True)
    m2 = baker.make(Membership, name="m2", active=True)
    baker.make(UserMembership, user=configured_user, membership=m1, subscription_status="cancelled")
    resp = client.get(create_url)
    form = resp.context_data["form"]
    # membership is fully cancelled, can buy new one
    assert set(form.fields["membership"].queryset) == {m1, m2}


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_create_user_has_cancelled_unexpired_membership(client, seller, configured_user):
    client.force_login(configured_user)
    m1 = baker.make(Membership, name="m1", active=True)
    m2 = baker.make(Membership, name="m2", active=True)
    baker.make(
        UserMembership, user=configured_user, membership=m1, 
        subscription_status="active", 
        start_date=datetime(2024, 2, 1, tzinfo=datetime_tz.utc),
        end_date=datetime(2024, 3, 1, tzinfo=datetime_tz.utc)
    )
    resp = client.get(create_url)
    form = resp.context_data["form"]
    # membership cancels from end of month, only has option for next month
    assert set(form.fields["membership"].queryset) == {m1, m2}
    assert form.fields["backdate"].choices == [(0, "March")]


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_create_user_has_current_membership(client, seller, configured_user):
    # redirect; no options to create new membership
    client.force_login(configured_user)
    m1 = baker.make(Membership, name="m1", active=True)
    m2 = baker.make(Membership, name="m2", active=True)
    baker.make(
        UserMembership, user=configured_user, membership=m1, 
        subscription_status="active", 
        start_date=datetime(2024, 2, 1, tzinfo=datetime_tz.utc),
    )
    resp = client.get(create_url)
    assert "You already have an active membership" in resp.rendered_content


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_create_user_has_future_membership(client, seller, configured_user):
    client.force_login(configured_user)
    m1 = baker.make(Membership, name="m1", active=True)
    m2 = baker.make(Membership, name="m2", active=True)
    baker.make(
        UserMembership, user=configured_user, membership=m1, 
        subscription_status="active", 
        start_date=datetime(2024, 3, 1, tzinfo=datetime_tz.utc),
    )
    resp = client.get(create_url)
    form = resp.context_data["form"]
    assert set(form.fields["membership"].queryset) == {m1, m2}
    assert "You already have an active membership" in resp.rendered_content


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_create_post(client, seller, configured_user):
    # can't post to this page; form posts to stripe checkout
    client.force_login(configured_user)
    m1 = baker.make(Membership, name="m1", active=True)
    resp = client.post(create_url, {"membership": m1.id, "backdate": 1})
    assert resp.status_code == 405


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector", MockConnector)
def test_membership_checkout_new_subscription_backdate(client, seller, configured_stripe_user):
    # membership checkout page, with data from membership selection page
    client.force_login(configured_stripe_user)
    m1 = baker.make(Membership, name="m1", active=True)
    resp = client.post(checkout_url, {"membership": m1.id, "backdate": 1})
    assert resp.status_code == 200
    assert "/stripe/subscribe-complete/" in resp.context_data["stripe_return_url"]
    assert resp.context_data["backdate"] == 1
    assert resp.context_data["amount"] == m1.price * 100
    assert resp.context_data["creating"] == True
    assert resp.context_data["membership"] == m1
    assert resp.context_data["customer_id"] == configured_stripe_user.userprofile.stripe_customer_id


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector", MockConnector)
def test_membership_checkout_new_subscription_no_backdate(client, seller, configured_stripe_user):
    # membership checkout page, with data from membership selection page
    client.force_login(configured_stripe_user)
    m1 = baker.make(Membership, name="m1", active=True)
    resp = client.post(checkout_url, {"membership": m1.id, "backdate": 0})
    assert resp.status_code == 200
    assert "/stripe/subscribe-complete/" in resp.context_data["stripe_return_url"]
    assert resp.context_data["backdate"] == 0
    # no backdating, amount charged now is 0
    assert resp.context_data["amount"] == 0
    assert resp.context_data["creating"] == True
    assert resp.context_data["membership"] == m1
    assert resp.context_data["customer_id"] == configured_stripe_user.userprofile.stripe_customer_id


def mock_connector_class(subscription_id, invoice_secret=None, setup_secret=None, su_status="payment_method_required"):
    invoice = None
    pending_setup_intent = None

    if invoice_secret:
        invoice = Mock(payment_intent=Mock(client_secret=invoice_secret))
    elif setup_secret:
        pending_setup_intent = Mock(id="su", client_secret=setup_secret)

    class Connector(MockConnector):
        def get_subscription(self, subscription_id):
            return MagicMock(
                id=subscription_id,
                latest_invoice=invoice,
                pending_setup_intent=pending_setup_intent
            )
        
        def get_setup_intent(self, setup_intent_id):
            return Mock(id=setup_intent_id, status=su_status)
            

    return Connector


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector", mock_connector_class("sub1a", invoice_secret="pi_secret"))
def test_membership_checkout_existing_subscription_with_invoice(client, seller, configured_stripe_user):
    # membership checkout page, with data from membership selection page
    client.force_login(configured_stripe_user)
    m1 = baker.make(Membership, name="m1", active=True)
    baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=m1, 
        subscription_id="sub1a",
        subscription_status="incomplete"
    )
    resp = client.post(checkout_url, {"subscription_id": "sub1a"})
    assert resp.status_code == 200
    assert resp.context_data["backdate"] == 0
    assert resp.context_data["amount"] == ""
    assert "creating" not in resp.context_data
    assert resp.context_data["membership"] == m1
    assert resp.context_data["customer_id"] == configured_stripe_user.userprofile.stripe_customer_id
    assert resp.context_data["client_secret"] == "pi_secret"
    assert resp.context_data["confirm_type"] == "payment"


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector", mock_connector_class("sub1b", setup_secret="su_secret"))
def test_membership_checkout_existing_subscription_with_setup_intent(client, seller, configured_stripe_user):
    # membership checkout page, with data from membership selection page
    client.force_login(configured_stripe_user)
    m1 = baker.make(Membership, name="m1", active=True)
    baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=m1, 
        subscription_id="sub1b",
        subscription_status="setup_pending"
    )
    resp = client.post(checkout_url, {"subscription_id": "sub1b"})
    assert resp.status_code == 200
    assert resp.context_data["backdate"] == 0
    assert resp.context_data["amount"] == ""
    assert "creating" not in resp.context_data
    assert resp.context_data["membership"] == m1
    assert resp.context_data["customer_id"] == configured_stripe_user.userprofile.stripe_customer_id
    assert resp.context_data["client_secret"] == "su_secret"
    assert resp.context_data["confirm_type"] == "setup"