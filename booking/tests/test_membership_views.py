from datetime import datetime
from datetime import timezone as datetime_tz
from unittest.mock import patch

import pytest

from django.urls import reverse

from model_bakery import baker

from stripe_payments.tests.mock_connector import MockConnector

from booking.models import Membership, UserMembership

pytestmark = pytest.mark.django_db

create_url = reverse("membership_create")
checkout_url = reverse("membership_checkout")


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
    assert resp.url == reverse("stripe_subscription_checkout")


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector", MockConnector)
def test_subscription_checkout(client, seller, configured_user):
    # subscription checkout page, with data from membership selection page
    client.force_login(configured_user)
    m1 = baker.make(Membership, name="m1", active=True)
    resp = client.post(checkout_url, {"membership": m1.id, "backdate": 1})
    assert resp.status_code == 200
    assert "/stripe/subscribe-complete/" in resp.context_data["stripe_return_url"]
