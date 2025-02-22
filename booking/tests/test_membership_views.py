import json
from datetime import datetime, timedelta
from datetime import timezone as datetime_tz
from unittest.mock import patch, Mock

import pytest

from django.urls import reverse

from model_bakery import baker
from django.utils import timezone

from stripe_payments.models import Seller, StripeSubscriptionInvoice
from stripe_payments.utils import get_utcdate_from_timestamp
from stripe_payments.tests.mock_connector import MockConnector

from booking.models import Membership, MembershipItem, UserMembership, StripeSubscriptionVoucher
from booking.views.membership_views import ensure_subscription_up_to_date, validate_voucher_code

from conftest import MockEventObject


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
    m3 = baker.make(Membership, name="m3", active=False)
    baker.make(Membership, name="m4", active=True)
    for m in [m1, m2, m3]:
        baker.make(MembershipItem, membership=m)
    resp = client.get(create_url)
    assert resp.status_code == 200
    form = resp.context_data["form"]
    assert set(form.fields["membership"].queryset) == {m1, m2}
    assert form.fields["backdate"].choices == [(1, "February"), (0, "March")]


@pytest.mark.freeze_time("2024-12-10")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_create_get_end_of_year(client, seller, configured_user):
    client.force_login(configured_user)
    m1 = baker.make(Membership, name="m1", active=True)
    m2 = baker.make(Membership, name="m2", active=True)
    m3 = baker.make(Membership, name="m3", active=False)
    baker.make(Membership, name="m4", active=True)
    for m in [m1, m2, m3]:
        baker.make(MembershipItem, membership=m)
    resp = client.get(create_url)
    assert resp.status_code == 200
    form = resp.context_data["form"]
    assert set(form.fields["membership"].queryset) == {m1, m2}
    assert form.fields["backdate"].choices == [(1, "December"), (0, "January")]


@pytest.mark.freeze_time("2024-02-25 10:00")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_create_after_25th_of_month(client, seller, configured_user):
    client.force_login(configured_user)
    resp = client.get(create_url)
    assert resp.status_code == 200
    form = resp.context_data["form"]
    assert form.fields["backdate"].choices == [(0, "March")]


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_create_user_has_cancelled_membership(client, seller, configured_user, purchasable_membership):
    client.force_login(configured_user)
    m2 = baker.make(Membership, name="m2", active=True)
    baker.make(MembershipItem, membership=m2, quantity=5)
    baker.make(UserMembership, user=configured_user, membership=purchasable_membership, subscription_status="cancelled")
    resp = client.get(create_url)
    form = resp.context_data["form"]
    # membership is fully cancelled, can buy new one
    assert set(form.fields["membership"].queryset) == {purchasable_membership, m2}


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_create_user_has_cancelled_unexpired_membership(freezer, client, seller, configured_user, purchasable_membership):
    freezer.move_to("2024-02-12")
    client.force_login(configured_user)
    m1 = baker.make(Membership, name="m1", active=True)
    baker.make(MembershipItem, membership=m1)
    baker.make(
        UserMembership, user=configured_user, membership=m1, 
        subscription_status="active", 
        start_date=datetime(2024, 2, 1, tzinfo=datetime_tz.utc),
        end_date=datetime(2024, 3, 1, tzinfo=datetime_tz.utc)
    )
    resp = client.get(create_url)
    form = resp.context_data["form"]
    # membership cancels from end of month, only has option for next month
    assert set(form.fields["membership"].queryset) == {m1, purchasable_membership}
    assert form.fields["backdate"].choices == [(0, "March")]
    assert "You already have an active membership which ends after this month" in resp.rendered_content

    # After the 25th in this month, we're in the next billing period, so this is considered an already cancelled membership
    # We only show options for the current billing period, but we DON'T show the active membership message
    freezer.move_to("2024-02-26")
    client.force_login(configured_user)
    resp = client.get(create_url)
    form = resp.context_data["form"]
    assert form.fields["backdate"].choices == [(0, "March")]
    assert "You already have an active membership" not in resp.rendered_content

    # After the 25th in the PREVIOUS month, we're in the billing period that the cancelled membership ends in, 
    # so this is considered an active membership
    freezer.move_to("2024-01-26")
    client.force_login(configured_user)
    resp = client.get(create_url)
    assert resp.context_data["form"] is None
    assert "You already have an active membership" in resp.rendered_content


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_create_user_has_current_membership(client, seller, configured_user, purchasable_membership):
    # redirect; no options to create new membership
    client.force_login(configured_user)
    m1 = baker.make(Membership, name="m1", active=True)
    baker.make(MembershipItem, membership=m1)
    baker.make(
        UserMembership, user=configured_user, membership=m1, 
        subscription_status="active", 
        start_date=datetime(2024, 2, 1, tzinfo=datetime_tz.utc),
    )
    resp = client.get(create_url)
    assert "You already have an active membership" in resp.rendered_content


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_create_user_has_future_membership(client, seller, configured_user, purchasable_membership):
    client.force_login(configured_user)
    m1 = baker.make(Membership, name="m1", active=True)
    baker.make(MembershipItem, membership=m1)
    baker.make(
        UserMembership, user=configured_user, membership=m1, 
        subscription_status="active", 
        start_date=datetime(2024, 3, 1, tzinfo=datetime_tz.utc),
    )
    resp = client.get(create_url)
    form = resp.context_data["form"]
    assert form is None
    assert "You already have an active membership" in resp.rendered_content


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_create_post(client, seller, configured_user, purchasable_membership):
    # can't post to this page; form posts to stripe checkout
    client.force_login(configured_user)
    resp = client.post(create_url, {"membership": purchasable_membership.id, "backdate": 1})
    assert resp.status_code == 405


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_checkout_no_seller(client, configured_stripe_user, purchasable_membership):
    Seller.objects.all().delete()
    # membership checkout page, with data from membership selection page
    client.force_login(configured_stripe_user)
    resp = client.post(checkout_url, {"membership": purchasable_membership.id, "backdate": 1})
    assert resp.status_code == 200
    assert resp.context_data["preprocessing_error"]
   

@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector", MockConnector)
def test_membership_checkout_new_subscription_backdate(client, seller, configured_stripe_user, purchasable_membership):
    # membership checkout page, with data from membership selection page
    client.force_login(configured_stripe_user)
    resp = client.post(checkout_url, {"membership": purchasable_membership.id, "backdate": 1})
    assert resp.status_code == 200
    assert "/stripe/subscribe-complete/" in resp.context_data["stripe_return_url"]
    assert resp.context_data["backdate"] == 1
    assert resp.context_data["amount"] == purchasable_membership.price * 100
    assert resp.context_data["creating"] == True
    assert resp.context_data["membership"] == purchasable_membership
    assert resp.context_data["customer_id"] == configured_stripe_user.userprofile.stripe_customer_id


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector", MockConnector)
def test_membership_checkout_new_subscription_no_backdate(client, seller, configured_stripe_user, purchasable_membership):
    # membership checkout page, with data from membership selection page
    client.force_login(configured_stripe_user)
    resp = client.post(checkout_url, {"membership": purchasable_membership.id, "backdate": 0})
    assert resp.status_code == 200
    assert "/stripe/subscribe-complete/" in resp.context_data["stripe_return_url"]
    assert resp.context_data["backdate"] == 0
    # no backdating, amount charged now is 0
    assert resp.context_data["amount"] == 0
    assert resp.context_data["creating"] == True
    assert resp.context_data["membership"] == purchasable_membership
    assert resp.context_data["customer_id"] == configured_stripe_user.userprofile.stripe_customer_id


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector")
def test_membership_checkout_existing_subscription_with_invoice(mock_conn, client, seller, configured_stripe_user, purchasable_membership):
    mock_connector = MockConnector(invoice_secret="pi_secret")
    mock_conn.return_value = mock_connector
    
    # membership checkout page, with data from membership selection page
    client.force_login(configured_stripe_user)
    baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=purchasable_membership, 
        subscription_id="sub1a",
        subscription_status="incomplete"
    )
    resp = client.post(checkout_url, {"subscription_id": "sub1a"})
    assert resp.status_code == 200
    assert resp.context_data["backdate"] == 0
    assert resp.context_data["amount"] == ""
    assert "creating" not in resp.context_data
    assert resp.context_data["membership"] == purchasable_membership
    assert resp.context_data["customer_id"] == configured_stripe_user.userprofile.stripe_customer_id
    assert resp.context_data["client_secret"] == "pi_secret"
    assert resp.context_data["confirm_type"] == "payment"


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector")
def test_membership_checkout_existing_subscription_with_setup_intent(mock_conn, client, seller, configured_stripe_user, purchasable_membership):
    mock_connector = MockConnector(setup_intent_secret="su_secret")
    mock_conn.return_value = mock_connector

    # membership checkout page, with data from membership selection page
    client.force_login(configured_stripe_user)
    baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=purchasable_membership, 
        subscription_id="sub1b",
        subscription_status="setup_pending"
    )
    resp = client.post(checkout_url, {"subscription_id": "sub1b"})
    assert resp.status_code == 200
    assert resp.context_data["backdate"] == 0
    assert resp.context_data["amount"] == ""
    assert "creating" not in resp.context_data
    assert resp.context_data["membership"] == purchasable_membership
    assert resp.context_data["customer_id"] == configured_stripe_user.userprofile.stripe_customer_id
    assert resp.context_data["client_secret"] == "su_secret"
    assert resp.context_data["confirm_type"] == "setup"


@pytest.mark.freeze_time("2024-02-12")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector")
def test_membership_status_existing_subscription_with_setup_intent_already_succeeded(
    mock_conn, client, seller, configured_stripe_user, purchasable_membership
):
    mock_connector = MockConnector(setup_intent_secret="su_secret", setup_intent_status="succeeded")
    mock_conn.return_value = mock_connector

    client.force_login(configured_stripe_user)
    # user membership is incorrectly marked as setup pending
    user_membership = baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=purchasable_membership, 
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
def test_membership_status_existing_subscription_with_invoice_already_paid(mock_conn, client, seller, configured_stripe_user, purchasable_membership):
    mock_connector = MockConnector(invoice_secret="pi_secret", subscription_status="active")
    mock_conn.return_value = mock_connector
    
    client.force_login(configured_stripe_user)
    user_membership = baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=purchasable_membership, 
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
def test_membership_change_get(client, seller, configured_stripe_user, purchasable_membership):
    client.force_login(configured_stripe_user)
    m2 = baker.make(Membership, name="m2", active=True)
    m2.stripe_price_id = "price_2345"
    m2.save()
    baker.make(MembershipItem, membership=m2, quantity=3)
    baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=purchasable_membership, 
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
def test_membership_change_get_current_membership_cancelled(client, seller, configured_stripe_user, purchasable_membership):
    # can't change a cancelled membership
    client.force_login(configured_stripe_user)
    m2 = baker.make(Membership, name="m2", active=True)
    m2.stripe_price_id = "price_2345"
    m2.save()
    baker.make(MembershipItem, membership=m2, quantity=3)
    baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=purchasable_membership, 
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
def test_membership_change_post_active_subscription(mock_conn, client, seller, configured_stripe_user, purchasable_membership):
    # default payment method is used in get_subscription (to get the old subscription)
    # and passed on to create_subscription to create the new one
    mock_connector = MockConnector(default_payment_method="p1")
    mock_conn.return_value = mock_connector

    client.force_login(configured_stripe_user)
    m2 = baker.make(Membership, name="m2", active=True)
    m2.stripe_price_id = "price_2345"
    m2.save()
    baker.make(MembershipItem, membership=m2, quantity=3)
    baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=purchasable_membership, 
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
def test_membership_change_post_future_subscription(mock_conn, client, seller, configured_stripe_user, purchasable_membership):
    # default payment method is used in get_subscription (to get the old subscription)
    # and passed on to create_subscription to create the new one
    mock_connector = MockConnector(default_payment_method="p1")
    mock_conn.return_value = mock_connector

    client.force_login(configured_stripe_user)
    m2 = baker.make(Membership, name="m2", active=True)
    m2.stripe_price_id = "price_2345"
    m2.save()
    baker.make(MembershipItem, membership=m2, quantity=3)
    baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=purchasable_membership, 
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
def test_membership_change_post_invalid_form(client, seller, configured_stripe_user, purchasable_membership):
    client.force_login(configured_stripe_user)
    baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=purchasable_membership, 
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
@pytest.mark.parametrize(
    "subscriptions,setup_intent_secret,invoice_secret,expected_secret,expected_setup_type,voucher_code,voucher_valid",
    [
        # no existing subscriptions, setup intent
        ({}, "setup_secret", None, "setup_secret", "setup", None, False),
        # no existing subscriptions, setup intent, with voucher
         ({}, "setup_secret", None, "setup_secret", "setup", "foo", True),
        # no existing subscriptions, invoice
        ({}, None, "inv_secret", "inv_secret", "payment", None, False),
         # no existing subscriptions, invoice, with voucher
        ({}, None, "inv_secret", "inv_secret", "payment", "foo", False),
        # no matching subscriptions, setup intent
        (
            {
                "s1": Mock(customer="cus-1", status="canceled", pending_setup_intent=Mock(client_secret="foo"))
            }, 
            "setup_secret", None, "setup_secret", "setup", None, False,
        ),
        # no matching subscriptions, invoice
        (
            {
                "s1": Mock(customer="cus-1", status="canceled", latest_invoice=Mock(payment_intent=Mock(client_secret="foo")))
            }, 
            None, "inv_secret", "inv_secret", "payment", None, False,
        ),
        # matching subscriptions, setup intent
        (
            {
                "s1": MockEventObject(
                    id="s1",
                    object="subscription",
                    customer="cus-1", 
                    status="active", 
                    pending_setup_intent=Mock(client_secret="foo", status="payment_method_required"),
                    latest_invoice=None,
                    items=Mock(data=[Mock(price=Mock(id="price-1"), quantity=1)]),
                    billing_cycle_anchor=datetime(2024, 2, 25, tzinfo=datetime_tz.utc).timestamp(),
                    payment_settings=Mock(save_default_payment_method="on_subscription"),
                    discount=None,
                    discounts=[]
                )
            }, 
            "setup_secret", None, "foo", "setup", None, False,
        ),
        # matching subscriptions, setup intent, with voucher, no existing discount
        (
            {
                "s1": MockEventObject(
                    id="s1",
                    object="subscription",
                    customer="cus-1", 
                    status="active", 
                    pending_setup_intent=Mock(client_secret="foo", status="payment_method_required"),
                    latest_invoice=None,
                    items=Mock(data=[Mock(price=Mock(id="price-1"), quantity=1)]),
                    billing_cycle_anchor=datetime(2024, 2, 25, tzinfo=datetime_tz.utc).timestamp(),
                    payment_settings=Mock(save_default_payment_method="on_subscription"),
                    discount=None,
                    discounts=[]
                )
            }, 
            "setup_secret", None, "foo", "setup", "voucher_foo", True,
        ),
        # matching subscriptions, setup intent, with voucher, existing mismatched discount
        (
            {
                "s1": MockEventObject(
                    id="s1",
                    object="subscription",
                    customer="cus-1", 
                    status="active", 
                    pending_setup_intent=Mock(client_secret="foo", status="payment_method_required"),
                    latest_invoice=None,
                    items=Mock(data=[Mock(price=Mock(id="price-1"), quantity=1)]),
                    billing_cycle_anchor=datetime(2024, 2, 25, tzinfo=datetime_tz.utc).timestamp(),
                    payment_settings=Mock(save_default_payment_method="on_subscription"),
                    discount=Mock(promotion_code="voucher_bar"),
                    discounts=[Mock(promotion_code="voucher_bar")]
                )
            }, 
            "setup_secret", None, "foo", "setup", "voucher_foo", True,
        ),
        # matching subscriptions, setup intent, no voucher, existing discount
        (
            {
                "s1": MockEventObject(
                    id="s1",
                    object="subscription",
                    customer="cus-1", 
                    status="active", 
                    pending_setup_intent=Mock(client_secret="foo", status="payment_method_required"),
                    latest_invoice=None,
                    items=Mock(data=[Mock(price=Mock(id="price-1"), quantity=1)]),
                    billing_cycle_anchor=datetime(2024, 2, 25, tzinfo=datetime_tz.utc).timestamp(),
                    payment_settings=Mock(save_default_payment_method="on_subscription"),
                    discount=Mock(promotion_code="voucher_bar"),
                    discounts=[Mock(promotion_code="voucher_bar")],
                )
            }, 
            "setup_secret", None, "foo", "setup", None, False,
        ),
         # matching subscriptions, setup intent, with voucher, existing matched discount
        (
            {
                "s1": MockEventObject(
                    id="s1",
                    object="subscription",
                    customer="cus-1", 
                    status="active", 
                    pending_setup_intent=Mock(client_secret="foo", status="payment_method_required"),
                    latest_invoice=None,
                    items=Mock(data=[Mock(price=Mock(id="price-1"), quantity=1)]),
                    billing_cycle_anchor=datetime(2024, 2, 25, tzinfo=datetime_tz.utc).timestamp(),
                    payment_settings=Mock(save_default_payment_method="on_subscription"),
                    discount=Mock(promotion_code="voucher_foo"),
                    discounts=[Mock(promotion_code="voucher_foo")],
                )
            }, 
            "setup_secret", None, "foo", "setup", "voucher_foo", True,
        ),
        # matching subscriptions, setup intent succeeded
        (
            {
                "s1": MockEventObject(
                    id="s1",
                    object="subscription",
                    customer="cus-1", 
                    status="active", 
                    pending_setup_intent=Mock(client_secret="foo", status="succeeded"),
                    latest_invoice=None,
                    items=Mock(data=[Mock(price=Mock(id="price-1"), quantity=1)]),
                    billing_cycle_anchor=datetime(2024, 2, 25, tzinfo=datetime_tz.utc).timestamp(),
                    payment_settings=Mock(save_default_payment_method="on_subscription"),
                    discount=None,
                    discounts=[],
                )
            }, 
            "setup_secret", None, "setup_secret", "setup", None, False,
        ),
        # matching subscriptions, invoice unpaid
        (
            {
                "s1": MockEventObject(
                    id="s1",
                    object="subscription",
                    customer="cus-1", 
                    status="active", 
                    pending_setup_intent=None,
                    latest_invoice=Mock(payment_intent=Mock(id="pi-1",client_secret="foo"), paid=False),
                    items=Mock(data=[Mock(price=Mock(id="price-1"), quantity=1)]),
                    billing_cycle_anchor=datetime(2024, 2, 25, tzinfo=datetime_tz.utc).timestamp(),
                    payment_settings=Mock(save_default_payment_method="on_subscription"),
                    discount=None,
                    discounts=[],
                )
            }, 
            None, "inv_secret", "foo", "payment", None, False,
        ),
        # matching subscriptions, invoice paid
        (
            {
                "s1": MockEventObject(
                    id="s1",
                    object="subscription",
                    customer="cus-1", 
                    status="active", 
                    pending_setup_intent=None,
                    latest_invoice=Mock(payment_intent=Mock(id="pi-1",client_secret="foo"), paid=True),
                    items=Mock(data=[Mock(price=Mock(id="price-1"), quantity=1)]),
                    billing_cycle_anchor=datetime(2024, 2, 25, tzinfo=datetime_tz.utc).timestamp(),
                    payment_settings=Mock(save_default_payment_method="on_subscription"),
                    discount=None,
                    discounts=[],
                )
            }, 
            None, "inv_secret", "inv_secret", "payment", None, False,
        )
    ]
)
@patch("booking.views.membership_views.StripeConnector")
@pytest.mark.freeze_time("2024-02-12")
def test_subscription_create_subscription(
    mock_conn, client, seller, subscriptions, setup_intent_secret, invoice_secret, expected_secret, expected_setup_type,
    voucher_code, voucher_valid, settings
):
    """
    parametrize:
    existing_user_subscriptions - none, no matching, matching with invoice, matching with setup intent
    backdate for post - 0/1
    """
    settings.DEBUG = True
    mock_connector = MockConnector(
        setup_intent_secret=setup_intent_secret, invoice_secret=invoice_secret, subscriptions=subscriptions,
        # payment intent for the existing invoice not-paid test
        get_payment_intent=Mock(id="pi-1", status="incomplete", client_secret="foo")
    )
    mock_conn.return_value = mock_connector

    if voucher_valid:
        baker.make(StripeSubscriptionVoucher, code=voucher_code)

    post_data = {"customer_id": "cus-1", "price_id": "price-1", "backdate": "0"}
    if voucher_code:
        post_data["voucher_code"] = voucher_code
    resp = client.post(
        reverse("subscription_create"), 
        json.dumps(post_data),
        content_type="application/json"
    )

    assert resp.status_code == 200, resp.content
    assert json.loads(resp.content) == {'clientSecret': expected_secret, 'type': expected_setup_type}


@pytest.mark.parametrize(
    "debug,expected_error",
    [
        (True, "This is the actual error raised"),
        (False, "An unexpected error occurred.")
    ]

)
@patch("booking.views.membership_views.StripeConnector.get_subscriptions_for_customer")
def test_subscription_create_subscription_error(
    mock_get_subscriptions, client, seller, settings, debug, expected_error
):
    """
    parametrize:
    existing_user_subscriptions - none, no matching, matching with invoice, matching with setup intent
    backdate for post - 0/1
    """
    settings.DEBUG = debug
    mock_get_subscriptions.side_effect = Exception("This is the actual error raised")
    resp = client.post(
        reverse("subscription_create"), 
        json.dumps({"customer_id": "cus-1", "price_id": "price-1", "backdate": "0"}),
        content_type="application/json"
    )

    assert resp.status_code == 400
    assert json.loads(resp.content) == {"error": {"message": expected_error}}


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_subscription_cancel_get(
    client, seller, configured_stripe_user, purchasable_membership
):
    client.force_login(configured_stripe_user)
    user_membership = baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=purchasable_membership, 
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
        (datetime(2024, 2, 12, tzinfo=datetime_tz.utc), datetime(2024, 2, 10, tzinfo=datetime_tz.utc), True),
        # start date in past, currently >= 25th, first billing date past -> cancel in future
        (datetime(2024, 2, 25, 10, tzinfo=datetime_tz.utc), datetime(2024, 2, 10, tzinfo=datetime_tz.utc), False),
        # start date in past, first billig date in past -> cancel in future
        (datetime(2024, 2, 12, tzinfo=datetime_tz.utc), datetime(2024, 1, 10, tzinfo=datetime_tz.utc), False),
        (datetime(2024, 2, 28, tzinfo=datetime_tz.utc), datetime(2024, 2, 25, tzinfo=datetime_tz.utc), False),
    ]
)
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector")
def test_subscription_cancel(
        mock_conn, freezer, client, seller, configured_stripe_user, purchasable_membership,
        now, subscription_start_date, cancel_immediately
):
    mock_connector = MockConnector()
    mock_conn.return_value = mock_connector

    client.force_login(configured_stripe_user)
    baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=purchasable_membership, 
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


@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector.cancel_subscription")
def test_subscription_cancel_with_error(
    mock_cancel, freezer, client, seller, configured_stripe_user, purchasable_membership,
):
    mock_cancel.side_effect = [Exception]

    client.force_login(configured_stripe_user)
    baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=purchasable_membership, 
        subscription_id="sub-1",
        subscription_status="active",
        subscription_start_date=datetime(2024, 2, 10, tzinfo=datetime_tz.utc),
    )
    freezer.move_to(datetime(2024, 2, 12, tzinfo=datetime_tz.utc))

    client.post(reverse("subscription_cancel", args=("sub-1",)))
    # get booking list to check messages (not using follow=True b/c the redirected URL also uses the StripeConnector)
    resp = client.get(reverse("booking:events"))
    assert "Something went wrong" in resp.rendered_content
    

# membership status
# get_subscription
# calculate date next invoice due
    # - not for cancelled
    # - not for cancelling in future
# get last invoice date (if there is one)
@pytest.mark.parametrize(
    "now,status,end_date,"
    "current_period_end,latest_invoice,cancel_at_ts,upcoming_invoice_discount,expected",
    [   
        # not cancelling, no latest invoice
        (
            datetime(2024, 2, 12, tzinfo=datetime_tz.utc), "active", None, 
            datetime(2024, 5, 25, tzinfo=datetime_tz.utc).timestamp(), None, None,
            None,
            dict(
                this_month="February",
                next_month="March",
                last_invoice=None,
                cancelling=False,
            )
        ),
        # cancelled, no latest invoice
        (
            datetime(2024, 2, 12, tzinfo=datetime_tz.utc), "canceled", datetime(2024, 2, 25, tzinfo=datetime_tz.utc), 
            datetime(2024, 5, 25, tzinfo=datetime_tz.utc).timestamp(), None, None,
            None,
            dict(
                this_month="February",
                next_month="March",
                last_invoice=None,
                cancelling=True,
            )
        ),
        # December, calculate next month correctly
        (
            datetime(2024, 12, 12, tzinfo=datetime_tz.utc), "active", None, 
            datetime(2024, 12, 25, tzinfo=datetime_tz.utc).timestamp(), None, None,
            None,
            dict(
                this_month="December",
                next_month="January",
                last_invoice=None,
                cancelling=False,
            )
        ),
        # not cancelling, with latest invoice
        (
            datetime(2024, 2, 12, tzinfo=datetime_tz.utc), "active", None, 
            datetime(2024, 5, 25, tzinfo=datetime_tz.utc).timestamp(), 
            Mock(
                effective_at=datetime(2024, 4, 25, tzinfo=datetime_tz.utc).timestamp(),
                discount=None,
                discounts=[],
                total=1000,
            ), 
            None,
            None,
            dict(
                this_month="February",
                next_month="March",
                last_invoice={
                    "date": datetime(2024, 4, 25, tzinfo=datetime_tz.utc),
                    "amount": 10,
                    "voucher_description": None
                },
                cancelling=False,
            )
        ),
        # not cancelling, with latest invoice and discount
        (
            datetime(2024, 2, 12, tzinfo=datetime_tz.utc), "active", None, 
            datetime(2024, 5, 25, tzinfo=datetime_tz.utc).timestamp(), 
            Mock(
                effective_at=datetime(2024, 4, 25, tzinfo=datetime_tz.utc).timestamp(),
                discount=Mock(promotion_code="promo-1"),
                discounts=[Mock(promotion_code="promo-1")],
                total=1000,
            ), 
            None,
            Mock(promotion_code="promo-2"),
            dict(
                this_month="February",
                next_month="March",
                last_invoice={
                    "date": datetime(2024, 4, 25, tzinfo=datetime_tz.utc),
                    "amount": 10,
                    "voucher_description": "£10.00"
                },
                cancelling=False,
            )
        ),
        # cancelling, no latest invoice
        (
            datetime(2024, 2, 12, tzinfo=datetime_tz.utc), "active", datetime(2024, 2, 25, tzinfo=datetime_tz.utc), 
            datetime(2024, 2, 25, tzinfo=datetime_tz.utc).timestamp(), None, datetime(2024, 2, 25, tzinfo=datetime_tz.utc).timestamp(),
            None,
            dict(
                this_month="February",
                next_month="March",
                last_invoice=None,
                cancelling=True,
            )
        ),
    ]
)
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector.get_upcoming_invoice")
@patch("booking.views.membership_views.StripeConnector.get_subscription")
def test_membership_status(
    mock_get_subscription, mock_upcoming_invoice, freezer, client, seller, configured_stripe_user, purchasable_membership,
    now, status, end_date, current_period_end, latest_invoice, cancel_at_ts, upcoming_invoice_discount, expected
):
    freezer.move_to(now)
    mock_get_subscription.return_value = MockEventObject(
        id="sub-1",
        object="subscription",
        customer="cus-1", 
        status="active", 
        cancel_at=cancel_at_ts,
        current_period_end=current_period_end,
        latest_invoice=latest_invoice,
        discount=None,
        discounts=[]
    )

    if upcoming_invoice_discount:
        baker.make(StripeSubscriptionVoucher, code="foo1", promo_code_id="promo-2", amount_off=8) 

    mock_upcoming_invoice.return_value = Mock(
        id="inv-1",
        customer="cus-1", 
        status="active", 
        period_end=current_period_end,
        total=purchasable_membership.price * 100,
        discount=upcoming_invoice_discount,
        discounts=[upcoming_invoice_discount] if upcoming_invoice_discount else []
    )

    if latest_invoice and latest_invoice.discount:
        baker.make(StripeSubscriptionVoucher, code="foo", promo_code_id="promo-1", amount_off=10)          
    
    client.force_login(configured_stripe_user)
    user_membership = baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=purchasable_membership, 
        subscription_id="sub-1",
        subscription_status=status,
        end_date=end_date,
    )
    resp = client.get(reverse("membership_status", args=("sub-1",)))
    if expected["cancelling"]:
        upcoming_invoice = None
    else:
        upcoming_invoice = {
            "date": get_utcdate_from_timestamp(current_period_end),
            "amount": purchasable_membership.price,
            "voucher_description": "£8.00" if upcoming_invoice_discount else None
        }

    assert resp.context_data == { 
        "user_membership": user_membership,
        "upcoming_invoice": upcoming_invoice,
        **expected,
    } 


@pytest.mark.parametrize(
    "voucher_expiry,upcoming_invoice_voucher_description",
    [
        (None, "£1.00"),
        (datetime(2024, 4, 23, tzinfo=datetime_tz.utc), "£1.00"),
        (datetime(2024, 3, 23, tzinfo=datetime_tz.utc), None)
    ]
)
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector.get_upcoming_invoice")
@patch("booking.views.membership_views.StripeConnector.remove_discount_from_subscription")
@patch("booking.views.membership_views.StripeConnector.get_subscription")
def test_membership_status_with_vouchers(
    mock_get_subscription, mock_remove_discount,  mock_upcoming_invoice, freezer, 
    client, seller, configured_stripe_user, purchasable_membership,
    voucher_expiry, upcoming_invoice_voucher_description
):
    freezer.move_to("2024-03-01")
    baker.make(
        StripeSubscriptionVoucher, code="foo", promo_code_id="foo", amount_off=1, 
        expiry_date=voucher_expiry
    )
    latest_invoice = Mock(
        effective_at=datetime(2024, 2, 25, tzinfo=datetime_tz.utc).timestamp(),
        discount=Mock(promotion_code="foo"),
        discounts=[Mock(promotion_code="foo")],
        total=purchasable_membership.price * 100,
    )
    mock_upcoming_invoice.return_value = Mock(
        id="inv-1",
        customer="cus-1", 
        status="active",
        period_end=datetime(2024, 3, 25, tzinfo=datetime_tz.utc).timestamp(),
        discount=Mock(promotion_code="foo"),
        discounts=[Mock(promotion_code="foo")],
        total=purchasable_membership.price * 100,
    )
    mock_get_subscription.return_value = MockEventObject(
        id="sub-1",
        object="subscription",
        customer="cus-1", 
        status="active", 
        cancel_at=None,
        current_period_end=datetime(2024, 3, 25).timestamp(),
        latest_invoice=latest_invoice,
        discount=latest_invoice.discount,
        discounts=latest_invoice.discounts
    )

    client.force_login(configured_stripe_user)
    baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=purchasable_membership, 
        subscription_id="sub-1",
        subscription_status="active",
    )
    resp = client.get(reverse("membership_status", args=("sub-1",)))

    # remove discount called
    if not upcoming_invoice_voucher_description:
        mock_remove_discount.assert_called_once()
    else:
        mock_remove_discount.assert_not_called()
    # no voucher description for upcoming
    upcoming_invoice_ctx = {
        "date": datetime(2024, 3, 25, tzinfo=datetime_tz.utc),
        "amount": purchasable_membership.price,
        "voucher_description": upcoming_invoice_voucher_description
    }
    last_invoice_ctx = {
        "date": datetime(2024, 2, 25, tzinfo=datetime_tz.utc),
        "amount": purchasable_membership.price,
        "voucher_description": "£1.00"
    }
    assert resp.context_data["upcoming_invoice"] == upcoming_invoice_ctx
    assert resp.context_data["last_invoice"] == last_invoice_ctx


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
def test_membership_list(mock_conn, client, seller, configured_stripe_user, purchasable_membership):
    mock_connector = MockConnector(
        subscriptions={
            "sub-1": MockEventObject(
                id="sub-1", object="subscription", canceled_at=None, cancel_at=None, 
                status="active", start_date=123, billing_cycle_anchor=123, discount=None, discounts=[]),
        }
    )
    mock_conn.return_value = mock_connector
    user_membership = baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=purchasable_membership, 
        subscription_id="sub-1",
        subscription_status="active",
    )

    client.force_login(configured_stripe_user)
    resp = client.get(reverse("membership_list"))
    assert resp.status_code == 200
    assert list(resp.context_data["memberships"]) == [user_membership]


@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector")
def test_membership_list_get_subscription(mock_conn, client, seller, configured_stripe_user, purchasable_membership):
    mock_connector = MockConnector(subscriptions={}, no_subscription=True)
    mock_conn.return_value = mock_connector
    user_membership = baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=purchasable_membership, 
        subscription_id="sub-1",
        subscription_status="active",
    )

    client.force_login(configured_stripe_user)
    resp = client.get(reverse("membership_list"))
    assert resp.status_code == 200
    assert list(resp.context_data["memberships"]) == [user_membership]


@pytest.mark.parametrize(
    "user_membership_attrs,subscription,expected",
    [
        (
            {"subscription_status": "active"},
            MockEventObject(
                canceled_at=None,
                cancel_at=None,
                status="active",
                start_date=datetime(2024, 2, 12, tzinfo=datetime_tz.utc).timestamp(),
                billing_cycle_anchor=datetime(2024, 2, 25, tzinfo=datetime_tz.utc).timestamp(),
                discount=None,
                discounts=[]
            ),
            dict(
                subscription_status="active",
                start_date=datetime(2024, 3, 1, tzinfo=datetime_tz.utc),
                subscription_start_date=datetime(2024, 2, 12, tzinfo=datetime_tz.utc),
                end_date=None,
                subscription_end_date=None,
                subscription_billing_cycle_anchor=datetime(2024, 2, 25, tzinfo=datetime_tz.utc),
            )
        ),
        (
            {"subscription_status": "canceled"},
            MockEventObject(
                canceled_at=None,
                cancel_at=None,
                status="active",
                start_date=datetime(2024, 2, 12, tzinfo=datetime_tz.utc).timestamp(),
                billing_cycle_anchor=datetime(2024, 2, 25, tzinfo=datetime_tz.utc).timestamp(),
                discount=None, 
                discounts=[]
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
            {"subscription_status": "active"},
            MockEventObject(
                canceled_at=datetime(2024, 2, 10, tzinfo=datetime_tz.utc).timestamp(),
                cancel_at=None,
                status="active",
                start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc).timestamp(),
                billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc).timestamp(),
                discount=None, 
                discounts=[]
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
            {"subscription_status": "active"},
            MockEventObject(
                canceled_at=None,
                cancel_at=datetime(2024, 2, 10, tzinfo=datetime_tz.utc).timestamp(),
                status="active",
                start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc).timestamp(),
                billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc).timestamp(),
                discount=None, 
                discounts=[]
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
        # payment intent status not succeeded/processing
        (
            {"subscription_status": "incomplete"},
            MockEventObject(
                canceled_at=None,
                cancel_at=datetime(2024, 2, 10, tzinfo=datetime_tz.utc).timestamp(),
                status="active",
                start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc).timestamp(),
                billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc).timestamp(),
                latest_invoice=Mock(payment_intent=Mock(status="pending")),
                discount=None, 
                discounts=[]
            ),
            dict(
                subscription_status="incomplete",
                start_date=datetime(2024, 2, 1, tzinfo=datetime_tz.utc),
                subscription_start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc),
                end_date=datetime(2024, 3, 1, tzinfo=datetime_tz.utc),
                subscription_end_date=datetime(2024, 2, 10, tzinfo=datetime_tz.utc),
                subscription_billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc)
            )
        ),
        # with non-expiring discount
        (
            {"subscription_status": "active"},
            MockEventObject(
                canceled_at=None,
                cancel_at=datetime(2024, 2, 10, tzinfo=datetime_tz.utc).timestamp(),
                status="active",
                start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc).timestamp(),
                billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc).timestamp(),
                discount=Mock(promotion_code="no_expire"), 
                discounts=[Mock(promotion_code="no_expire")]
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
        # with expiring discount
        (
            {"subscription_status": "active"},
            MockEventObject(
                canceled_at=None,
                cancel_at=datetime(2024, 2, 10, tzinfo=datetime_tz.utc).timestamp(),
                status="active",
                start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc).timestamp(),
                billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc).timestamp(),
                discount=Mock(promotion_code="expire"), 
                discounts=[Mock(promotion_code="expire")]
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
            {"subscription_status": "setup_pending"},
            MockEventObject(
                canceled_at=None,
                cancel_at=None,
                status="active",
                start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc).timestamp(),
                billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc).timestamp(),
                default_payment_method=None,
                pending_setup_intent=Mock(status="payment_method_required"),
                discount=None, 
                discounts=[]
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
            {"subscription_status": "setup_pending"},
            MockEventObject(
                canceled_at=None,
                cancel_at=None,
                status="active",
                start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc).timestamp(),
                billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc).timestamp(),
                default_payment_method="p1",
                pending_setup_intent=Mock(status="payment_method_required"),
                discount=None, 
                discounts=[]
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
            {"subscription_status": "setup_pending"},
            MockEventObject(
                canceled_at=None,
                cancel_at=None,
                status="active",
                start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc).timestamp(),
                billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc).timestamp(),
                default_payment_method=None,
                pending_setup_intent=Mock(status="succeeded"),
                discount=None, 
                discounts=[]
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
        # with different start date, no override
        (
            {"subscription_status": "active", "start_date": datetime(2024, 2, 1, tzinfo=datetime_tz.utc)},
            MockEventObject(
                canceled_at=None,
                cancel_at=None,
                status="active",
                start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc).timestamp(),
                billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc).timestamp(),
                discount=None, 
                discounts=[]
            ),
            dict(
                subscription_status="active",
                start_date=datetime(2024, 2, 1, tzinfo=datetime_tz.utc),
                subscription_start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc),
                end_date=None,
                subscription_end_date=None,
                subscription_billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc)
            ),
        ),
        # with override start date
        (
            {
                "subscription_status": "active", 
                "start_date": datetime(2024, 1, 1, tzinfo=datetime_tz.utc),
                "override_start_date": datetime(2024, 3, 1, tzinfo=datetime_tz.utc)
            },
            MockEventObject(
                canceled_at=None,
                cancel_at=None,
                status="active",
                start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc).timestamp(),
                billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc).timestamp(),
                discount=None, 
                discounts=[]
            ),
            dict(
                subscription_status="active",
                start_date=datetime(2024, 3, 1, tzinfo=datetime_tz.utc),
                subscription_start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc),
                end_date=None,
                subscription_end_date=None,
                subscription_billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc)
            ),
        ),
        # paused status is not updated
        (
            {
                "subscription_status": "active",
                "override_subscription_status": "paused" 
            },
            MockEventObject(
                canceled_at=None,
                cancel_at=None,
                status="active",
                start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc).timestamp(),
                billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc).timestamp(),
                discount=None, 
                discounts=[]
            ),
            dict(
                subscription_status="paused",
                start_date=datetime(2024, 2, 1, tzinfo=datetime_tz.utc),
                subscription_start_date=datetime(2024, 1, 12, tzinfo=datetime_tz.utc),
                end_date=None,
                subscription_end_date=None,
                subscription_billing_cycle_anchor=datetime(2024, 1, 25, tzinfo=datetime_tz.utc)
            ),
        ),
    ]
)
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector")
def test_ensure_subscription_up_to_date(
    mock_view_connector, seller, configured_stripe_user, purchasable_membership, 
    user_membership_attrs, subscription, expected
):
    view_connector = MockConnector()
    mock_view_connector.return_value = view_connector
    baker.make(
        StripeSubscriptionVoucher, code="foo", promo_code_id="no_expire", amount_off=2, expiry_date=None
    )
    baker.make(
        StripeSubscriptionVoucher, code="bar", promo_code_id="expire", amount_off=2, expiry_date=datetime.now(datetime_tz.utc)
    )
    user_membership = baker.make(
        UserMembership, 
        user=configured_stripe_user, 
        membership=purchasable_membership, 
        subscription_id="sub-1",
        **user_membership_attrs,
    )

    ensure_subscription_up_to_date(user_membership, subscription, "sub-1")
    user_membership.refresh_from_db()
    for attr, value in expected.items():
        assert getattr(user_membership, attr) == value, attr
    
    if subscription.discount:
        if subscription.discount.promotion_code == "expire":
            view_connector.method_calls["remove_discount_from_subscription"]
        else:
            assert "remove_discount_from_subscription" not in view_connector.method_calls


@pytest.mark.parametrize(
    "code,active,redeem_by,new_only,membership,existing_sub_id,used,valid_on_stripe,expected",
    [
        (   
            # Valid
            "foo", True, None, False, # active, no expiry, valid for all
            "valid", None, # valid for membership, not existing sub
            False, True, # not used yet, valid on stripe
            (True, "Voucher valid: 10.0% off one month's membership")
        ),
        (   
            # Invalid, not valid on stripe
            "foo", True, None, False, # active, no expiry, valid for all
            "valid", None, # valid for membership, not existing sub
            False, False, # not used yet, not valid on stripe
            (False, "foo is not a valid code")
        ),
        (   
            # Invalid, not active
            "foo", False, None, False, # active, no expiry, valid for all
            "valid", None, # valid for membership, not existing sub
            False, True, # not used yet, valid on stripe
            (False, "foo is not a valid code")
        ),
        (   
            # Invalid, expired
            "foo", True, timezone.now() - timedelta(1), False, # active, has expired, valid for all
            "valid", None, # valid for membership, not existing sub
            False, True, # not used yet, valid on stripe
            (False, "foo is not a valid code")
        ),
        (   
            # Invalid, voucher doesn't exist
            "bar", True, None, False, # active, no expiry, valid for all
            "valid", None, # valid for membership, not existing sub
            False, True, # not used yet, valid on stripe
            (False, "bar is not a valid code")
        ),
        (   
            # Valid, only valid for first
            "foo", True, None, True, # active, no expiry, valid for all
            "valid", None, # valid for membership, not existing sub
            False, True, # not used yet, valid on stripe
            (True, "Voucher valid: 10.0% off one month's membership")
        ),
        (   
            # Invalid, only valid for first
            "foo", True, None, True, # active, no expiry, valid for first only
            "valid", "sub1", # valid for membership, existing sub
            False, True, # not used yet, valid on stripe
            (False, "foo is only valid for new memberships")
        ),
        (   
            # Invalid, already used
            "foo", True, None, False, # active, no expiry, valid for all
            "valid", "sub1", # valid for membership, existing sub
            True, True, # not used yet, valid on stripe
            (False, "foo has already been applied to this membership")
        ),
        (   
            # Invalid, wrong membership
            "foo", True, None, False, # active, no expiry, valid for all
            "other", None, # not valid for membership, no existing sub
            False, True, # not used yet, valid on stripe
            (False, "foo is not valid for the selected membership")
        ),
    ]
)
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector.get_promo_code")
def test_validate_voucher_code(mock_get_promo_code, seller, code, active, redeem_by, new_only, membership, existing_sub_id, used, valid_on_stripe, expected):
    mock_get_promo_code.return_value = Mock(active=valid_on_stripe)
    memberships = {
        "valid": baker.make(
            Membership, name="memb-1", description="a membership", price=10, visible=True
        ),
        "other": baker.make(
            Membership, name="memb-1", description="a membership", price=10, visible=True
        )
    }
    
    voucher = baker.make(
        StripeSubscriptionVoucher, 
        code="foo", 
        promo_code_id="p-1",
        percent_off=10,
        duration="once",
        active=active,
        redeem_by=redeem_by,
        new_memberships_only=new_only,
    )
    voucher.memberships.add(memberships["valid"])

    if used:
        baker.make(StripeSubscriptionInvoice, subscription_id=existing_sub_id, promo_code_id="p-1")

    _, voucher_valid, voucher_message = validate_voucher_code(code, memberships[membership], existing_sub_id)
    assert (voucher_valid, voucher_message) == expected


@pytest.mark.parametrize(
    "code,amount,percent,amount_charged_now,expected",
    [
        ("foo", 10, None, 10, {"voucher_valid": True, "next_amount": 10}),
        ("foo", None, 10, 10, {"voucher_valid": True, "next_amount": 18}),
        ("bar", 10, None, 10, {"voucher_valid": False, "next_amount": 20}),
        ("bar", None, 10, 10, {"voucher_valid": False, "next_amount": 20}),
        # amount_charged_now=0 means subscription is for next period; voucher expires
        ("expires", None, 10, 0, {"voucher_valid": False, "next_amount": 20, "voucher_message": "Voucher expires before next payment date"}),
        # amount_charged_now>0 None means subscription is for current period; voucher expires before next
        ("expires", None, 10, 10, {"voucher_valid": True, "next_amount": 18}),
    ]

)
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector.get_promo_code")
def test_membership_voucher_validate_view(mock_get_promo_code, client, seller, code, amount, percent, amount_charged_now, expected, configured_stripe_user):
    mock_get_promo_code.return_value = Mock(active=True)
    membership = baker.make(
        Membership, name="memb-1", description="a membership", price=20, visible=True
        )
    
    voucher = baker.make(
        StripeSubscriptionVoucher, 
        code="foo", 
        promo_code_id="p-1",
        percent_off=percent,
        amount_off=amount,
        duration="once",
        active=True,
    )
    voucher.memberships.add(membership)

    expiring_voucher = baker.make(
        StripeSubscriptionVoucher, 
        code="expires", 
        promo_code_id="p-2",
        percent_off=percent,
        amount_off=amount,
        duration="once",
        active=True,
        expiry_date=timezone.now()
    )
    expiring_voucher.memberships.add(membership)

    client.force_login(configured_stripe_user)
    post_data = {"membership_id": membership.id, "voucher_code": code, "amount": amount_charged_now}
    resp = client.post(reverse("membership_voucher_validate"), post_data)
    for k, v in expected.items():
        assert resp.context_data[k] == v


@pytest.mark.parametrize(
    "code,expected",
    [
        ("foo", True),
        ("bar", False),
    ]

)
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector.get_promo_code")
def test_membership_voucher_apply_validate_view(mock_get_promo_code, client, seller, code, expected, configured_stripe_user):
    mock_get_promo_code.return_value = Mock(active=True)
    membership = baker.make(
        Membership, name="memb-1", description="a membership", price=20, visible=True
        )
    user_membership = baker.make(UserMembership, membership=membership, user=configured_stripe_user)
    
    voucher = baker.make(
        StripeSubscriptionVoucher, 
        code="foo", 
        promo_code_id="p-1",
        duration="once",
        active=True,
    )
    voucher.memberships.add(membership)

    client.force_login(configured_stripe_user)
    post_data = {"user_membership_id": user_membership.id, "voucher_code": code}
    resp = client.post(reverse("membership_voucher_apply_validate"), post_data)
    assert resp.context_data["voucher_valid"] == expected


@pytest.mark.parametrize(
    "code,valid_code",
    [
        ("foo", True),
        ("bar", False),
    ]

)
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("booking.views.membership_views.StripeConnector.get_promo_code")
@patch("booking.views.membership_views.StripeConnector.add_discount_to_subscription")
def test_membership_voucher_apply_validate_view_apply(mock_get_promo_code, mock_add_discount, client, seller, code, valid_code, configured_stripe_user):
    mock_get_promo_code.return_value = Mock(active=True)
    membership = baker.make(
        Membership, name="memb-1", description="a membership", price=20, visible=True
        )
    user_membership = baker.make(UserMembership, membership=membership, user=configured_stripe_user)
    
    voucher = baker.make(
        StripeSubscriptionVoucher, 
        code="foo", 
        promo_code_id="p-1",
        duration="once",
        active=True,
    )
    voucher.memberships.add(membership)

    client.force_login(configured_stripe_user)
    post_data = {"user_membership_id": user_membership.id, "voucher_code": code, "apply": "Apply"}
    resp = client.post(reverse("membership_voucher_apply_validate"), post_data)

    if valid_code:
        assert resp.status_code == 302
    else:
        assert resp.status_code == 200
        assert resp.context_data["voucher_valid"] is False
    