import json
from datetime import datetime
from datetime import timezone as datetime_tz
from unittest.mock import patch, MagicMock, Mock

import pytest

from django.urls import reverse

from model_bakery import baker

from stripe_payments.tests.mock_connector import MockConnector

from booking.models import Membership, UserMembership
from booking.views.membership_views import ensure_subscription_up_to_date


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


def test_membership_checkout_no_seller(client, configured_stripe_user):
    # membership checkout page, with data from membership selection page
    client.force_login(configured_stripe_user)
    resp = client.post(checkout_url, {"membership": "m1", "backdate": 1})
    assert resp.status_code == 200
    assert resp.context_data["preprocessing_error"]
   

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


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector")
def test_membership_checkout_existing_subscription_with_invoice(mock_conn, client, seller, configured_stripe_user):
    mock_connector = MockConnector(invoice_secret="pi_secret")
    mock_conn.return_value = mock_connector
    
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
@patch("booking.views.membership_views.StripeConnector")
def test_membership_checkout_existing_subscription_with_setup_intent(mock_conn, client, seller, configured_stripe_user):
    mock_connector = MockConnector(setup_intent_secret="su_secret")
    mock_conn.return_value = mock_connector

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


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector")
def test_membership_checkout_existing_subscription_with_setup_intent_already_succeeded(
    mock_conn, client, seller, configured_stripe_user
):
    mock_connector = MockConnector(setup_intent_secret="su_secret", setup_intent_status="succeeded")
    mock_conn.return_value = mock_connector

    # membership checkout page, with data from membership selection page
    client.force_login(configured_stripe_user)
    m1 = baker.make(Membership, name="m1", active=True)
    # user membership is incorrectly marked as setup pending
    user_membership = baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=m1, 
        subscription_id="sub1b",
        subscription_status="setup_pending",
        pending_setup_intent="su1",
    )
    resp = client.post(checkout_url, {"subscription_id": "sub1b"})
    assert resp.status_code == 302
    assert resp.url == reverse("membership_status", args=("sub1b",))
    
    user_membership.refresh_from_db()
    assert user_membership.subscription_status == "active"
    assert user_membership.pending_setup_intent is None 


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector")
def test_membership_checkout_existing_subscription_with_invoice_already_paid(mock_conn, client, seller, configured_stripe_user):
    mock_connector = MockConnector(invoice_secret="pi_secret", subscription_status="active")
    mock_conn.return_value = mock_connector
    
    # membership checkout page, with data from membership selection page
    client.force_login(configured_stripe_user)
    m1 = baker.make(Membership, name="m1", active=True)
    user_membership = baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=m1, 
        subscription_id="sub1a",
        subscription_status="incomplete"
    )
    resp = client.post(checkout_url, {"subscription_id": "sub1a"})
    assert resp.status_code == 302
    assert resp.url == reverse("membership_status", args=("sub1a",))
    
    user_membership.refresh_from_db()
    assert user_membership.subscription_status == "active"
    assert user_membership.pending_setup_intent is None


# membership change
# setup 2 memberships; 1 user membership with one of the membership types

# get - form options to change to
# can only change IF the membership is active and not cancelling, i.e. it has no end date (context var)

# changes will all start from the beginning of the next month 
# cancellations will start from the beginning of the next month 
# if it's the user's current (uncancelled) membership, this one will be cancelled from the end of the month and 
# a new one created from start of next month 
# if it's a future membership (starting at beginning of next month): 
# - if it's not billed yet, it'll be cancelled from the end of the month (25th) and a new one created that starts 
# from the start of next month - so this one should never be invoiced. 
    
# post
# create new sub, cancel current one; new one created with default payment method from current one
# sub starts in future -> cancel immediately
# if sub start day < 25, means sub started earlier in the month and was not backdated (if sub start day was
# >= 25 it's always backdated to 25th). Check if the billing_anchor_date, which is the actual start date of the
# subscription, is in the future
# start date

@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector", MockConnector)
def test_membership_change_get(client, seller, configured_stripe_user):
    client.force_login(configured_stripe_user)
    m1 = baker.make(Membership, name="m1", active=True)
    m2 = baker.make(Membership, name="m2", active=True)
    m2.stripe_price_id = "price_2345"
    m2.save()
    baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=m1, 
        subscription_id="sub1",
        subscription_status="active",
        start_date=datetime(2024, 1, 1)
    )

    resp = client.get(reverse("membership_change", args=("sub1",)))
    assert resp.status_code == 200
    assert resp.context_data["can_change"] is True
    form = resp.context_data["form"]
    assert list(form.fields["membership"].queryset) == [m2]


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector", MockConnector)
def test_membership_change_get_current_membership_cancelled(client, seller, configured_stripe_user):
    # can't change a cancelled membership
    client.force_login(configured_stripe_user)
    m1 = baker.make(Membership, name="m1", active=True)
    m2 = baker.make(Membership, name="m2", active=True)
    m2.stripe_price_id = "price_2345"
    m2.save()
    baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=m1, 
        subscription_id="sub1",
        subscription_status="active",
        start_date=datetime(2023, 12, 1),
        end_date=datetime(2024, 3, 1)
    )

    resp = client.get(reverse("membership_change", args=("sub1",)))
    assert resp.status_code == 200
    assert resp.context_data["can_change"] is False
    assert resp.context_data["form"] is None


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector")
def test_membership_change_post_active_subscription(mock_conn, client, seller, configured_stripe_user):
    # default payment method is used in get_subscription (to get the old subscription)
    # and passed on to create_subscription to create the new one
    mock_connector = MockConnector(default_payment_method="p1")
    mock_conn.return_value = mock_connector

    client.force_login(configured_stripe_user)
    m1 = baker.make(Membership, name="m1", active=True)
    m2 = baker.make(Membership, name="m2", active=True)
    m2.stripe_price_id = "price_2345"
    m2.save()
    baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=m1, 
        subscription_id="sub1",
        subscription_status="active",
        subscription_start_date=datetime(2023, 12, 25),
        start_date=datetime(2024, 1, 1)
    )

    resp = client.post(reverse("membership_change", args=("sub1",)), {"membership": m2.id})
    assert resp.status_code == 302

    create_calls = mock_connector.method_calls["create_subscription"]
    cancel_calls = mock_connector.method_calls["cancel_subscription"]
    for calls in [create_calls, cancel_calls]:
        assert len(calls) == 1
    
    # create for customer with m2 price
    assert create_calls[0]["args"] == ("cus-1",)
    assert create_calls[0]["kwargs"]["price_id"] == m2.stripe_price_id
    assert create_calls[0]["kwargs"]["default_payment_method"] == "p1"
    assert create_calls[0]["kwargs"]["backdate"] is False

    # cancel sub1   
    assert cancel_calls[0]["args"] == ("sub1",)
    assert cancel_calls[0]["kwargs"]["cancel_immediately"] is False


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector")
def test_membership_change_post_future_subscription(mock_conn, client, seller, configured_stripe_user):
    # default payment method is used in get_subscription (to get the old subscription)
    # and passed on to create_subscription to create the new one
    mock_connector = MockConnector(default_payment_method="p1")
    mock_conn.return_value = mock_connector

    client.force_login(configured_stripe_user)
    m1 = baker.make(Membership, name="m1", active=True)
    m2 = baker.make(Membership, name="m2", active=True)
    m2.stripe_price_id = "price_2345"
    m2.save()
    baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=m1, 
        subscription_id="sub1",
        subscription_status="active",
        subscription_start_date=datetime(2024, 2, 10),
        subscription_billing_cycle_anchor=datetime(2024, 2, 25),
        start_date=datetime(2024, 3, 1)
    )

    resp = client.post(reverse("membership_change", args=("sub1",)), {"membership": m2.id})
    assert resp.status_code == 302

    create_calls = mock_connector.method_calls["create_subscription"]
    cancel_calls = mock_connector.method_calls["cancel_subscription"]
    for calls in [create_calls, cancel_calls]:
        assert len(calls) == 1
    
    # create for customer with m2 price
    assert create_calls[0]["args"] == ("cus-1",)
    assert create_calls[0]["kwargs"]["price_id"] == m2.stripe_price_id
    assert create_calls[0]["kwargs"]["default_payment_method"] == "p1"
    assert create_calls[0]["kwargs"]["backdate"] is False

    # cancel sub1   
    assert cancel_calls[0]["args"] == ("sub1",)
    assert cancel_calls[0]["kwargs"]["cancel_immediately"] is True


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_change_post_invalid_form(client, seller, configured_stripe_user):
    client.force_login(configured_stripe_user)
    m1 = baker.make(Membership, name="m1", active=True)
    baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=m1, 
        subscription_id="sub1",
    )
    resp = client.post(reverse("membership_change", args=("sub1",)), {"membership": "foo"})
    assert resp.status_code == 200


# httpx calls
    
# subscription_create
# - called with customer_id, price_id and backdate (0/1 str) in post data
# - looks up subscriptions for customer
# - looks for a subscription with matching price id and date that is either
#     - incomplete OR
#     - active, but with non-succeeded pending_setup_intent
# - if it doesn't find a matching one, creates a new one
# - Returns either the setup intent or invoices payment intent secret
from conftest import MockSubscription
@pytest.mark.parametrize(
    "subscriptions,setup_intent_secret,invoice_secret,expected_secret,expected_setup_type",
    [
        # no existing subscriptions, setup intent
        ({}, "setup_secret", None, "setup_secret", "setup"),
        # no existing subscriptions, invoice
        ({}, None, "inv_secret", "inv_secret", "payment"),
        # no matching subscriptions, setup intent
        (
            {
                "s1": Mock(customer="cus-1", status="canceled", pending_setup_intent=Mock(client_secret="foo"))
            }, 
            "setup_secret", None, "setup_secret", "setup"
        ),
        # no matching subscriptions, invoice
        (
            {
                "s1": Mock(customer="cus-1", status="canceled", latest_invoice=Mock(payment_intent=Mock(client_secret="foo")))
            }, 
            None, "inv_secret", "inv_secret", "payment",
        ),
        # matching subscriptions, setup intent
        (
            {
                "s1": MockSubscription(
                    customer="cus-1", 
                    status="active", 
                    pending_setup_intent=Mock(client_secret="foo", status="payment_method_required"),
                    latest_invoice=None,
                    items=Mock(data=[Mock(price=Mock(id="price-1"), quantity=1)]),
                    billing_cycle_anchor=datetime(2024, 2, 25, tzinfo=datetime_tz.utc).timestamp(),
                    payment_settings=Mock(save_default_payment_method="on_subscription")
                )
            }, 
            "setup_secret", None, "foo", "setup"
        ),
        # matching subscriptions, setup intent succeeded
        (
            {
                "s1": MockSubscription(
                    customer="cus-1", 
                    status="active", 
                    pending_setup_intent=Mock(client_secret="foo", status="succeeded"),
                    latest_invoice=None,
                    items=Mock(data=[Mock(price=Mock(id="price-1"), quantity=1)]),
                    billing_cycle_anchor=datetime(2024, 2, 25, tzinfo=datetime_tz.utc).timestamp(),
                    payment_settings=Mock(save_default_payment_method="on_subscription")
                )
            }, 
            "setup_secret", None, "setup_secret", "setup"
        ),
        # matching subscriptions, invoice
        (
            {
                "s1": MockSubscription(
                    customer="cus-1", 
                    status="active", 
                    pending_setup_intent=None,
                    latest_invoice=Mock(payment_intent="pi-1", paid=False, client_secret="foo"),
                    items=Mock(data=[Mock(price=Mock(id="price-1"), quantity=1)]),
                    billing_cycle_anchor=datetime(2024, 2, 25, tzinfo=datetime_tz.utc).timestamp(),
                    payment_settings=Mock(save_default_payment_method="on_subscription")
                )
            }, 
            None, "inv_secret", "foo", "payment"
        ),
        # matching subscriptions, invoice paid
        (
            {
                "s1": MockSubscription(
                    customer="cus-1", 
                    status="active", 
                    pending_setup_intent=None,
                    latest_invoice=Mock(payment_intent="pi-1", paid=True, client_secret="foo"),
                    items=Mock(data=[Mock(price=Mock(id="price-1"), quantity=1)]),
                    billing_cycle_anchor=datetime(2024, 2, 25, tzinfo=datetime_tz.utc).timestamp(),
                    payment_settings=Mock(save_default_payment_method="on_subscription")
                )
            }, 
            None, "inv_secret", "inv_secret", "payment"
        )
    ]
)
@patch("booking.views.membership_views.StripeConnector")
@pytest.mark.freeze_time("2024-02-12")
def test_subscription_create_subscription(
    mock_conn, client, seller, subscriptions, setup_intent_secret, invoice_secret, expected_secret, expected_setup_type
):
    """
    parametrize:
    existing_user_subscriptions - none, no matching, matching with invoice, matching with setup intent
    backdate for post - 0/1
    """
    mock_connector = MockConnector(
        setup_intent_secret=setup_intent_secret, invoice_secret=invoice_secret, subscriptions=subscriptions,
        # payment intent for the existing invoice not-paid test
        get_payment_intent=Mock(id="pi-1", status="incomplete", client_secret="foo")
    )
    mock_conn.return_value = mock_connector
    resp = client.post(
        reverse("subscription_create"), 
        json.dumps({"customer_id": "cus-1", "price_id": "price-1", "backdate": "0"}),
        content_type="application/json"
    )

    assert resp.status_code == 200, resp.content
    assert json.loads(resp.content) == {'clientSecret': expected_secret, 'type': expected_setup_type}


@patch("booking.views.membership_views.StripeConnector.get_subscriptions_for_customer")
def test_subscription_create_subscription_error(
    mock_get_subscriptions, client, seller
):
    """
    parametrize:
    existing_user_subscriptions - none, no matching, matching with invoice, matching with setup intent
    backdate for post - 0/1
    """
    mock_get_subscriptions.side_effect = Exception("Something went wrong")
    resp = client.post(
        reverse("subscription_create"), 
        json.dumps({"customer_id": "cus-1", "price_id": "price-1", "backdate": "0"}),
        content_type="application/json"
    )

    assert resp.status_code == 400
    assert json.loads(resp.content) == {'error': 'Something went wrong'}


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_subscription_cancel_get(
    client, seller, configured_stripe_user
):
    client.force_login(configured_stripe_user)
    m1 = baker.make(Membership, name="m1", active=True)
    user_membership = baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=m1, 
        subscription_id="sub-1",
        subscription_status="active",
        subscription_start_date=datetime(2024, 2, 10),
        subscription_billing_cycle_anchor=datetime(2024, 2, 25),
        start_date=datetime(2024, 3, 1)
    )

    resp = client.get(reverse("subscription_cancel", args=("sub-1",)))
    assert resp.context_data["user_membership"] == user_membership


def test_subscription_cancel_get_404(
    client, seller, configured_stripe_user
):
    client.force_login(configured_stripe_user)
    resp = client.get(reverse("subscription_cancel", args=("sub-1",)))
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "now,subscription_start_date,cancel_immediately",
    [
        # start date in past, first billig date (25th) in future -> cancel immediately
        (datetime(2024, 2, 12), datetime(2024, 2, 10), True),
        # start date in past, currently >= 25th, first billing date past -> cancel in future
        (datetime(2024, 2, 25, 10), datetime(2024, 2, 10), False),
        # start date in past, first billig date in past -> cancel in future
        (datetime(2024, 2, 12), datetime(2024, 1, 10), False),
        (datetime(2024, 2, 28), datetime(2024, 2, 25), False),
    ]
)
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector")
def test_subscription_cancel(
        mock_conn, freezer, client, seller, configured_stripe_user, 
        now, subscription_start_date, cancel_immediately
):
    mock_connector = MockConnector()
    mock_conn.return_value = mock_connector

    client.force_login(configured_stripe_user)
    m1 = baker.make(Membership, name="m1", active=True)
    baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=m1, 
        subscription_id="sub-1",
        subscription_status="active",
        subscription_start_date=subscription_start_date,
    )
    freezer.move_to(now)

    resp = client.post(reverse("subscription_cancel", args=("sub-1",)))
    assert resp.url == reverse("membership_list")
    assert mock_connector.method_calls == {
        'cancel_subscription': [
            {'args': ('sub-1',), 
             'kwargs': {'cancel_immediately': cancel_immediately}}
             ]
        }


# membership status
# get_subscription
# calculate date next invoice due
    # - not for cancelled
    # - not for cancelling in future
# get last invoice date (if there is one)
@pytest.mark.parametrize(
    "now,status,end_date,"
    "current_period_end,latest_invoice,cancel_at_ts,"
    "expected",
    [   
        # not cancelling, no latest invoice
        (
            datetime(2024, 2, 12, tzinfo=datetime_tz.utc), "active", None, 
            datetime(2024, 5, 25, tzinfo=datetime_tz.utc).timestamp(), None, None,
            dict(
                this_month="February",
                next_month="March",
                next_due=datetime(2024, 5, 25, tzinfo=datetime_tz.utc),
                last_invoice=None,
                cancelling=False,
            )
        ),
        # cancelled, no latest invoice
        (
            datetime(2024, 2, 12, tzinfo=datetime_tz.utc), "canceled", datetime(2024, 2, 25, tzinfo=datetime_tz.utc), 
            datetime(2024, 5, 25, tzinfo=datetime_tz.utc).timestamp(), None, None,
            dict(
                this_month="February",
                next_month="March",
                next_due=None,
                last_invoice=None,
                cancelling=True,
            )
        ),
        # December, calculate next month correctly
        (
            datetime(2024, 12, 12, tzinfo=datetime_tz.utc), "active", None, 
            datetime(2024, 12, 25, tzinfo=datetime_tz.utc).timestamp(), None, None,
            dict(
                this_month="December",
                next_month="January",
                next_due=datetime(2024, 12, 25, tzinfo=datetime_tz.utc),
                last_invoice=None,
                cancelling=False,
            )
        ),
        # not cancelling, with latest invoice
        (
            datetime(2024, 2, 12, tzinfo=datetime_tz.utc), "active", None, 
            datetime(2024, 5, 25, tzinfo=datetime_tz.utc).timestamp(), 
            Mock(effective_at=datetime(2024, 4, 25, tzinfo=datetime_tz.utc).timestamp()), 
            None,
            dict(
                this_month="February",
                next_month="March",
                next_due=datetime(2024, 5, 25, tzinfo=datetime_tz.utc),
                last_invoice=datetime(2024, 4, 25, tzinfo=datetime_tz.utc),
                cancelling=False,
            )
        ),
        # cancelling, no latest invoice
        (
            datetime(2024, 2, 12, tzinfo=datetime_tz.utc), "active", datetime(2024, 2, 25, tzinfo=datetime_tz.utc), 
            datetime(2024, 2, 25, tzinfo=datetime_tz.utc).timestamp(), None, datetime(2024, 2, 25, tzinfo=datetime_tz.utc).timestamp(),
            dict(
                this_month="February",
                next_month="March",
                next_due=None,
                last_invoice=None,
                cancelling=True,
            )
        ),
    ]
)
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector.get_subscription")
def test_membership_status(
    mock_get_subscription, freezer, client, seller, configured_stripe_user, 
    now, status, end_date, current_period_end, latest_invoice, cancel_at_ts, expected
):
    freezer.move_to(now)
    mock_get_subscription.return_value = MockSubscription(
        id="sub-1",
        customer="cus-1", 
        status="active", 
        cancel_at=cancel_at_ts,
        current_period_end=current_period_end,
        latest_invoice=latest_invoice,
    )
                    
    client.force_login(configured_stripe_user)
    m1 = baker.make(Membership, name="m1", active=True)
    user_membership = baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=m1, 
        subscription_id="sub-1",
        subscription_status=status,
        end_date=end_date,
    )
    resp = client.get(reverse("membership_status", args=("sub-1",)))
    assert resp.context_data == { 
        "user_membership": user_membership, 
        **expected
    } 


# membership list
# checks and updates subscriptions
def test_membership_list_not_logged_in(client):
    resp = client.get(reverse("membership_list"))
    assert resp.status_code == 302
    assert reverse("login") in resp.url


def test_membership_list_no_customer_id(client, configured_user):
    client.force_login(configured_user)
    resp = client.get(reverse("membership_list"))
    assert resp.status_code == 200


@patch("booking.views.membership_views.StripeConnector", MockConnector)
def test_membership_list_no_user_memberships(client, seller, configured_stripe_user):
    client.force_login(configured_stripe_user)
    resp = client.get(reverse("membership_list"))
    assert resp.status_code == 200
    assert list(resp.context_data["memberships"]) == []


@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector")
def test_membership_list(mock_conn, client, seller, configured_stripe_user):
    mock_connector = MockConnector(
        subscriptions={
            "sub-1": MockSubscription(
                id="sub-1", canceled_at=None, cancel_at=None, status="active", start_date=123, billing_cycle_anchor=123),
        }
    )
    mock_conn.return_value = mock_connector
    m1 = baker.make(Membership, name="m1", active=True)
    user_membership = baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=m1, 
        subscription_id="sub-1",
        subscription_status="active",
    )

    client.force_login(configured_stripe_user)
    resp = client.get(reverse("membership_list"))
    assert resp.status_code == 200
    assert list(resp.context_data["memberships"]) == [user_membership]


@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector")
def test_membership_list_get_subscription(mock_conn, client, seller, configured_stripe_user):
    mock_connector = MockConnector(subscriptions={}, no_subscription=True)
    mock_conn.return_value = mock_connector
    m1 = baker.make(Membership, name="m1", active=True)
    user_membership = baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=m1, 
        subscription_id="sub-1",
        subscription_status="active",
    )

    client.force_login(configured_stripe_user)
    resp = client.get(reverse("membership_list"))
    assert resp.status_code == 200
    assert list(resp.context_data["memberships"]) == [user_membership]


@pytest.mark.parametrize(
    "user_membership_status,subscription,expected",
    [
        (
            "active",
            MockSubscription(
                canceled_at=None,
                cancel_at=None,
                status="active",
                start_date=datetime(2024, 2, 12, tzinfo=datetime_tz.utc).timestamp(),
                billing_cycle_anchor=datetime(2024, 2, 25, tzinfo=datetime_tz.utc).timestamp(),
            ),
            dict(
                subscription_status="active",
                start_date=datetime(2024, 3, 1, tzinfo=datetime_tz.utc),
                subscription_start_date=datetime(2024, 2, 12, tzinfo=datetime_tz.utc),
                end_date=None,
                subscription_end_date=None,
                subscription_billing_cycle_anchor=datetime(2024, 2, 25, tzinfo=datetime_tz.utc)
            )
        ),
        (
            "canceled",
            MockSubscription(
                canceled_at=None,
                cancel_at=None,
                status="active",
                start_date=datetime(2024, 2, 12, tzinfo=datetime_tz.utc).timestamp(),
                billing_cycle_anchor=datetime(2024, 2, 25, tzinfo=datetime_tz.utc).timestamp(),
            ),
            dict(
                subscription_status="active",
                start_date=datetime(2024, 3, 1, tzinfo=datetime_tz.utc),
                subscription_start_date=datetime(2024, 2, 12, tzinfo=datetime_tz.utc),
                end_date=None,
                subscription_end_date=None,
                subscription_billing_cycle_anchor=datetime(2024, 2, 25, tzinfo=datetime_tz.utc)
            )
        ),
        (
            "active",
            MockSubscription(
                canceled_at=datetime(2024, 2, 10, tzinfo=datetime_tz.utc).timestamp(),
                cancel_at=None,
                status="active",
                start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc).timestamp(),
                billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc).timestamp(),
            ),
            dict(
                subscription_status="active",
                start_date=datetime(2024, 2, 1, tzinfo=datetime_tz.utc),
                subscription_start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc),
                end_date=datetime(2024, 3, 1, tzinfo=datetime_tz.utc),
                subscription_end_date=datetime(2024, 2, 10, tzinfo=datetime_tz.utc),
                subscription_billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc)
            )
        ),
        (
            "active",
            MockSubscription(
                canceled_at=None,
                cancel_at=datetime(2024, 2, 10, tzinfo=datetime_tz.utc).timestamp(),
                status="active",
                start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc).timestamp(),
                billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc).timestamp(),
            ),
            dict(
                subscription_status="active",
                start_date=datetime(2024, 2, 1, tzinfo=datetime_tz.utc),
                subscription_start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc),
                end_date=datetime(2024, 3, 1, tzinfo=datetime_tz.utc),
                subscription_end_date=datetime(2024, 2, 10, tzinfo=datetime_tz.utc),
                subscription_billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc)
            )
        ),
        # setup_pending stays as is if pending setup intent not complete
        (
            "setup_pending",
            MockSubscription(
                canceled_at=None,
                cancel_at=None,
                status="active",
                start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc).timestamp(),
                billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc).timestamp(),
                default_payment_method=None,
                pending_setup_intent=Mock(status="payment_method_required")
            ),
            dict(
                subscription_status="setup_pending",
                start_date=datetime(2024, 2, 1, tzinfo=datetime_tz.utc),
                subscription_start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc),
                end_date=None,
                subscription_end_date=None,
                subscription_billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc)
            )
        ),
        # setup_pending updated if default payment method
        (
            "setup_pending",
            MockSubscription(
                canceled_at=None,
                cancel_at=None,
                status="active",
                start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc).timestamp(),
                billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc).timestamp(),
                default_payment_method="p1",
                pending_setup_intent=Mock(status="payment_method_required")
            ),
            dict(
                subscription_status="active",
                start_date=datetime(2024, 2, 1, tzinfo=datetime_tz.utc),
                subscription_start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc),
                end_date=None,
                subscription_end_date=None,
                subscription_billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc)
            )
        ),
        # setup_pending updated if setup succeeded
        (
            "setup_pending",
            MockSubscription(
                canceled_at=None,
                cancel_at=None,
                status="active",
                start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc).timestamp(),
                billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc).timestamp(),
                default_payment_method=None,
                pending_setup_intent=Mock(status="succeeded")
            ),
            dict(
                subscription_status="active",
                start_date=datetime(2024, 2, 1, tzinfo=datetime_tz.utc),
                subscription_start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc),
                end_date=None,
                subscription_end_date=None,
                subscription_billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc)
            )
        )
    ]
)
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_ensure_subscription_up_to_date(
    seller, configured_stripe_user, user_membership_status, subscription,
    expected
):
    m1 = baker.make(Membership, name="m1", active=True)
    user_membership = baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=m1, 
        subscription_id="sub-1",
        subscription_status=user_membership_status,
    )

    ensure_subscription_up_to_date(user_membership, subscription, "sub-1")
    user_membership.refresh_from_db()
    for attr, value in expected.items():
        assert getattr(user_membership, attr) == value, attr

"""

def ensure_subscription_up_to_date(user_membership, subscription, subscription_id=None):
    if subscription is None:
        client = StripeConnector()
        subscription = client.get_subscription(subscription_id)
        if subscription is None:
            return

    if subscription.canceled_at:
        sub_end = get_utcdate_from_timestamp(subscription.canceled_at)
    elif subscription.cancel_at:
        sub_end = get_utcdate_from_timestamp(subscription.cancel_at)
    else:
        sub_end = None

    status = subscription.status
    if user_membership.subscription_status == "setup_pending":
        # prevent status being updated to active (the stripe subscription status) if
        # the setup intent has not yet succeeded and there's no default_payment_method
        if not subscription.default_payment_method and subscription.pending_setup_intent.status != "succeeded":
            status = "setup_pending"

    subscription_data = {
        "subscription_start_date": get_utcdate_from_timestamp(subscription.start_date),
        "subscription_end_date": sub_end,
        "start_date": get_first_of_next_month_from_timestamp(subscription.start_date),
        "end_date": user_membership.calculate_membership_end_date(sub_end),
        "subscription_status": status,
        "subscription_billing_cycle_anchor": get_utcdate_from_timestamp(subscription.billing_cycle_anchor),
    }
    needs_update = False
    for attribute, value in subscription_data.items():
        if getattr(user_membership, attribute) != value:
            needs_update = True
            setattr(user_membership, attribute, value)
    
    if needs_update:
        user_membership.save()
"""