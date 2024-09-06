from datetime import datetime
from datetime import timezone as datetime_tz
from unittest.mock import patch, Mock
import pytest

from django.conf import settings
from django.contrib.sites.models import Site
from django.core import mail
from django.shortcuts import reverse
from django.utils import timezone

import stripe
from model_bakery import baker

from booking.models import Block, Membership, UserMembership
from ..models import Seller, StripePaymentIntent, StripeSubscriptionInvoice
from .mock_connector import MockConnector

pytestmark = pytest.mark.django_db


# stripe_webhook view
webhook_url = reverse("stripe_payments:stripe_webhook")


@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_with_matching_invoice_and_block(
    mock_webhook, get_mock_webhook_event, client, invoice, configured_user
):
    assert StripePaymentIntent.objects.exists() is False
    block = baker.make(Block, paid=True, block_type__cost=10, invoice=invoice)
    metadata = {
        "invoice_id": "foo",
        "invoice_signature": invoice.signature(),
        **invoice.items_metadata(),
    }
    mock_webhook.construct_event.return_value = get_mock_webhook_event(metadata=metadata)

    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200
    block.refresh_from_db()
    invoice.refresh_from_db()

    assert block.paid is True
    assert invoice.paid is True
    payment_intent_obj = StripePaymentIntent.objects.latest("id")
    assert payment_intent_obj.invoice == invoice

    assert len(mail.outbox) == 2
    assert mail.outbox[0].to == [settings.DEFAULT_STUDIO_EMAIL]
    assert mail.outbox[1].to == [configured_user.email]
    assert "Your payment has been processed" in mail.outbox[1].subject


@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_with_refunded_invoice_and_block(
    mock_webhook, get_mock_webhook_event, client, invoice, configured_user
):
    assert StripePaymentIntent.objects.exists() is False
    invoice.paid = True
    invoice.save()
    block = baker.make(Block, paid=True, block_type__cost=10, invoice=invoice)
    metadata = {
        "invoice_id": "foo",
        "invoice_signature": invoice.signature(),
        **invoice.items_metadata(),
    }
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="charge.refund.updated",
        metadata=metadata
    )

    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200
    block.refresh_from_db()
    invoice.refresh_from_db()

    # still paid, we don't do any updates to refunded items
    assert block.paid is True
    assert invoice.paid is True

    # email to support only
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [settings.SUPPORT_EMAIL]
    assert "WARNING: Payment refund processed" in mail.outbox[0].subject


@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_already_processed(
    mock_webhook, get_mock_webhook_event, client, invoice
):
    baker.make(Block, paid=True, block_type__cost=10, invoice=invoice)
    invoice.paid = True
    invoice.save()
    metadata = {
        "invoice_id": "foo",
        "invoice_signature": invoice.signature(),
        **invoice.items_metadata(),
    }
    mock_webhook.construct_event.return_value = get_mock_webhook_event(metadata=metadata)
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")

    assert resp.status_code == 200
    # already processed, no emails sent
    assert len(mail.outbox) == 0


@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_exceptions(mock_webhook, client):
    mock_webhook.construct_event.side_effect = stripe.error.SignatureVerificationError("", "foo")
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    # stripe verification error returns 400 so stripe will try again
    assert resp.status_code == 400

    mock_webhook.construct_event.side_effect = ValueError
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    # value error means payload is invalid; returns 400 so stripe will try again
    assert resp.status_code == 400


@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_exception_retrieving_invoice(
    mock_webhook, get_mock_webhook_event, client, invoice
):
    block = baker.make(Block, paid=False, block_type__cost=10, invoice=invoice)
    # invalid invoice signature
    metadata = {
        "invoice_id": "bar",
        **invoice.items_metadata(),
    }
    mock_webhook.construct_event.return_value = get_mock_webhook_event(metadata=metadata)
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200

    # invoice and block is still unpaid
    assert block.paid is False
    assert invoice.paid is False

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [settings.SUPPORT_EMAIL]
    assert "WARNING: Something went wrong processing a stripe event!" in mail.outbox[0].subject
    assert "could not find invoice" in mail.outbox[0].body


@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_exception_invalid_invoice_signature(
    mock_webhook, get_mock_webhook_event, client, invoice
):
    block = baker.make(Block, paid=False, block_type__cost=10, invoice=invoice)

    # invalid invoice signature
    metadata = {
        "invoice_id": "foo",
        "invoice_signature": "foo",
        **invoice.items_metadata(),
    }
    mock_webhook.construct_event.return_value = get_mock_webhook_event(metadata=metadata)
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200

    # invoice and block is still unpaid
    assert block.paid is False
    assert invoice.paid is False

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [settings.SUPPORT_EMAIL]
    assert "WARNING: Something went wrong processing a stripe event!" in mail.outbox[0].subject
    assert "Error: Could not verify invoice signature: payment intent mock-intent-id; invoice id foo" \
            in mail.outbox[0].body


@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_exception_no_invoice(
    mock_webhook, get_mock_webhook_event, client, invoice
):
    block = baker.make(Block, paid=False, block_type__cost=10, invoice=invoice)

    # no invoice id or signature in metadata
    metadata = invoice.items_metadata()
    mock_webhook.construct_event.return_value = get_mock_webhook_event(metadata=metadata)
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200

    # invoice and block is still unpaid
    assert block.paid is False
    assert invoice.paid is False

    assert len(mail.outbox) == 0
    # No error emails sent as this is assumed to be a subscription (no invoice info in metadata)


@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_payment_failed(
    mock_webhook, get_mock_webhook_event, client, invoice
):
    block = baker.make(Block, paid=False, block_type__cost=10, invoice=invoice)
    metadata = {
        "invoice_id": "foo",
        "invoice_signature": invoice.signature(),
        **invoice.items_metadata(),
    }
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="payment_intent.payment_failed", metadata=metadata
    )
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200
    block.refresh_from_db()
    invoice.refresh_from_db()
    # invoice and block is still unpaid
    assert block.paid is False
    assert invoice.paid is False
    # no emails sent; payment failed for a one-off invoice is due to synchronous user data entry and
    # will be reported to the user to try again
    assert len(mail.outbox) == 0


@patch("stripe_payments.views.webhook.stripe.Webhook")
@patch("stripe_payments.views.webhook.stripe.Account")
def test_webhook_authorized_account(
    mock_account, mock_webhook, get_mock_webhook_event, client
):
    # mock the seller that should have been created in the StripeAuthorizeCallbackView
    baker.make(Seller, stripe_user_id="stripe-account-1")
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="account.application.authorized"
    )
    mock_account.list.return_value = Mock(data=[Mock(id="stripe-account-1")])

    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200


@patch("stripe_payments.views.webhook.stripe.Webhook")
@patch("stripe_payments.views.webhook.stripe.Account")
def test_webhook_authorized_account_no_seller(
    mock_account, mock_webhook, get_mock_webhook_event, client
):
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="account.application.authorized"
    )
    mock_account.list.return_value = Mock(data=[Mock(id="stripe-account-1")])
    Seller.objects.all().delete()
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200
    assert "Stripe account has no associated seller on this site" in resp.content.decode()


@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_payment_intent_succeeded_mismatched_seller(
    mock_webhook, get_mock_webhook_event, client, invoice
):     
    baker.make(Block, paid=True, block_type__cost=10, invoice=invoice)
    metadata = {
        "invoice_id": "foo",
        "invoice_signature": invoice.signature(),
        **invoice.items_metadata(),
    }
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        metadata=metadata, seller_id="other-seller-id"
    )

    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200
    assert resp.content.decode() == "Ignored: Mismatched seller account"


@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_payment_intent_succeeded_no_seller(
    mock_webhook, get_mock_webhook_event, client, invoice
):  
    baker.make(Block, paid=True, block_type__cost=10, invoice=invoice)
    metadata = {
        "invoice_id": "foo",
        "invoice_signature": invoice.signature(),
        **invoice.items_metadata(),
    }
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        metadata=metadata, seller_id="other-seller-id"
    )
    Seller.objects.all().delete()

    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200
    assert resp.content.decode() == "Ignored: No seller account set up for site"


@patch("stripe_payments.views.webhook.stripe.Webhook")
@patch("stripe_payments.views.webhook.stripe.Account")
def test_webhook_deauthorized_account(
    mock_account, mock_webhook, get_mock_webhook_event, seller, client
):
    assert seller.site == Site.objects.get_current()
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="account.application.deauthorized"
    )
    mock_account.list.return_value = Mock(data=[])

    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200
    seller.refresh_from_db()
    assert seller.site is None


# Memberships
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_subscription_created(
    mock_webhook, get_mock_webhook_event, client, configured_stripe_user
):
    membership = baker.make(Membership, name="membership1")
    assert not membership.user_memberships.exists()
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="customer.subscription.created",
        start_date = datetime(2024, 6, 25).timestamp()
    )
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200
    # no emails sent for initial creation with no default payment method (i.e. setup but not paid/confirmed yet)
    assert len(mail.outbox) == 0
    # membership created, with start date as first of next month
    assert membership.user_memberships.count() == 1
    assert membership.user_memberships.first().start_date.date() == datetime(2024, 7, 1).date()


@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_subscription_created_setup_pending(
    mock_webhook, get_mock_webhook_event, client, configured_stripe_user
):
    membership = baker.make(Membership, name="membership1")
    assert not membership.user_memberships.exists()
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="customer.subscription.created",
        start_date = datetime(2024, 6, 25).timestamp(),
        pending_setup_intent="su_123",
        status="active",
    )
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200
    # no emails sent for initial creation with no default payment method (i.e. setup but not paid/confirmed yet)
    assert len(mail.outbox) == 0
    # membership created, with start date as first of next month
    assert membership.user_memberships.count() == 1
    user_membership = membership.user_memberships.first()
    assert user_membership.start_date.date() == datetime(2024, 7, 1).date()
    assert user_membership.subscription_status == "setup_pending"


@pytest.mark.parametrize(
    "studio_email",
    (
        True, False
    )
)
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_setup_intent_succeeded_for_subscription_with_user_membership(
    mock_webhook, get_mock_webhook_event, client, configured_stripe_user, settings, studio_email
):
    settings.NOTIFY_STUDIO_FOR_NEW_MEMBERSHIPS = studio_email
    membership = baker.make(Membership, name="membership")
    user_membership = baker.make(
        UserMembership, 
        user=configured_stripe_user,
        pending_setup_intent="su_123",
        subscription_status="setup_pending",
        membership=membership
    )
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
       webhook_event_type="setup_intent.succeeded",
       id="su_123"

    )
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200, resp.content
    if studio_email:
        assert len(mail.outbox) == 2
        assert "A new membership has been set up" in mail.outbox[1].subject
        assert mail.outbox[1].to == [settings.DEFAULT_STUDIO_EMAIL]
    else:
        assert len(mail.outbox) == 1
    assert "Your membership has been set up" in mail.outbox[0].subject
    user_membership.refresh_from_db()
    assert user_membership.pending_setup_intent is None
    assert user_membership.subscription_status == "active"


@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_subscription_deleted(
    mock_webhook, get_mock_webhook_event, client, configured_stripe_user
):
    membership = baker.make(Membership, name="membership1")
    user_membership = baker.make(
        UserMembership, membership=membership, user=configured_stripe_user, subscription_id="id"
    )
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="customer.subscription.deleted", 
        canceled_at=datetime(2024, 3, 1).timestamp(),
        status="canceled"
    )
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200, resp.content
    user_membership.refresh_from_db()
    assert user_membership.subscription_status == "canceled"
    assert user_membership.subscription_end_date == datetime(2024, 3, 1, tzinfo=datetime_tz.utc)
    assert user_membership.end_date == datetime(2024, 4, 1, tzinfo=datetime_tz.utc)
    # No emails sent
    assert len(mail.outbox) == 0


@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_subscription_deleted_no_user_membership(
    mock_webhook, get_mock_webhook_event, client, configured_stripe_user
):
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="customer.subscription.deleted", 
        canceled_at=datetime(2024, 3, 1).timestamp(),
        status="canceled"
    )
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200, resp.content

    # No emails sent
    assert len(mail.outbox) == 0


@pytest.mark.freeze_time("2024-02-26")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_subscription_updated_status_changed_to_past_due(
    mock_webhook, get_mock_webhook_event, client, configured_stripe_user
):
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="customer.subscription.updated"
    )
    # status active, cancelled in future
    # status changed to active from cancelled
    # price changed (only if changed from stripe) - sends emails to support and changes membersip
    membership = baker.make(Membership, name="membership1")
    # freeze time; start user membership in past
    # make booking for next month and allocate user membership
    booking = baker.make_recipe("booking.booking", user=configured_stripe_user, event__date=datetime(2024, 3, 10, tzinfo=datetime_tz.utc))
    baker.make("booking.MembershipItem", event_type=booking.event.event_type, quantity=4, membership=membership)
    user_membership = baker.make(
        UserMembership, membership=membership, user=configured_stripe_user, subscription_id="id",
        start_date=datetime(2024, 1, 25, tzinfo=datetime_tz.utc)
    )
    booking.membership = user_membership
    booking.save()
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="customer.subscription.updated", 
        status="past_due",
        canceled_at=None,
    )
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200, resp.content

    assert len(mail.outbox) == 1
    assert "Action required - Complete your membership payment" in mail.outbox[0].subject

    # booking still has membership
    booking.refresh_from_db()
    assert booking.membership == user_membership


@pytest.mark.freeze_time("2024-02-26")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_subscription_updated_status_changed_to_active_from_cancelled(
    mock_webhook, get_mock_webhook_event, client, configured_stripe_user
):
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="customer.subscription.updated"
    )

    membership = baker.make(Membership, name="membership1")
    # booking with no membership yet
    unpaid_booking = baker.make_recipe(
        "booking.booking", 
        user=configured_stripe_user, 
        event__date=datetime(2024, 3, 10, tzinfo=datetime_tz.utc), paid=False
    )
    # paid booking that otherwise would be valid for membership
    paid_booking = baker.make_recipe(
        "booking.booking", 
        user=configured_stripe_user, 
        event__event_type=unpaid_booking.event.event_type, 
        event__date=datetime(2024, 3, 10, tzinfo=datetime_tz.utc), paid=True
    )
    baker.make("booking.MembershipItem", event_type=unpaid_booking.event.event_type, quantity=4, membership=membership)
    user_membership = baker.make(
        UserMembership, membership=membership, user=configured_stripe_user, subscription_id="id",
        subscription_status="canceled", start_date=datetime(2024, 1, 25, tzinfo=datetime_tz.utc)
    )
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="customer.subscription.updated", 
        status="active",
        canceled_at=None,
        cancel_at=None,
    )
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200, resp.content
    assert len(mail.outbox) == 0
    user_membership.refresh_from_db()
    assert user_membership.subscription_status == "active"

    unpaid_booking.refresh_from_db()
    paid_booking.refresh_from_db()
    assert unpaid_booking.membership == user_membership
    assert unpaid_booking.paid == True
    assert paid_booking.membership is None


@pytest.mark.parametrize(
    "studio_email",
    [
        True, False
    ]
)
@pytest.mark.freeze_time("2024-02-26")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_subscription_updated_status_changed_to_active_from_incomplete(
    mock_webhook, get_mock_webhook_event, client, configured_stripe_user, settings, studio_email
):
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="customer.subscription.updated"
    )
    settings.NOTIFY_STUDIO_FOR_NEW_MEMBERSHIPS = studio_email

    membership = baker.make(Membership, name="membership1")
    # booking with no membership yet
    unpaid_booking = baker.make_recipe(
        "booking.booking", 
        user=configured_stripe_user, 
        event__date=datetime(2024, 3, 10, tzinfo=datetime_tz.utc), paid=False
    )
    # paid booking that otherwise would be valid for membership
    paid_booking = baker.make_recipe(
        "booking.booking", 
        user=configured_stripe_user, 
        event__event_type=unpaid_booking.event.event_type, 
        event__date=datetime(2024, 3, 10, tzinfo=datetime_tz.utc), paid=True
    )
    baker.make("booking.MembershipItem", event_type=unpaid_booking.event.event_type, quantity=4, membership=membership)
    user_membership = baker.make(
        UserMembership, membership=membership, user=configured_stripe_user, subscription_id="id",
        subscription_status="incomplete", start_date=datetime(2024, 1, 25, tzinfo=datetime_tz.utc)
    )
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="customer.subscription.updated", 
        status="active",
        canceled_at=None,
        cancel_at=None,
    )
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200, resp.content
    if studio_email:
        assert len(mail.outbox) == 2
        assert "A new membership has been set up" in mail.outbox[1].subject
        assert mail.outbox[1].to == [settings.DEFAULT_STUDIO_EMAIL]
    else:
        assert len(mail.outbox) == 1
    assert "Your membership has been set up" in mail.outbox[0].subject
    user_membership.refresh_from_db()
    assert user_membership.subscription_status == "active"

    unpaid_booking.refresh_from_db()
    paid_booking.refresh_from_db()
    assert unpaid_booking.membership == user_membership
    assert unpaid_booking.paid == True
    assert paid_booking.membership is None



@pytest.mark.freeze_time("2024-02-26")
@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_subscription_updated_status_changed_to_incomplete_expired(
    mock_webhook, get_mock_webhook_event, client, configured_stripe_user
):
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="customer.subscription.updated"
    )
    # status incomplete, changed to incomplete_expired deletes UserMembership
    membership = baker.make(Membership, name="membership1")
    baker.make(
        UserMembership, membership=membership, user=configured_stripe_user, subscription_id="id",
        start_date=datetime(2024, 1, 25, tzinfo=datetime_tz.utc), subscription_status="incomplete"
    )
    assert membership.user_memberships.count() == 1
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="customer.subscription.updated", 
        status="incomplete_expired",
        canceled_at=None,
    )
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200, resp.content

    assert not membership.user_memberships.exists()


@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_subscription_updated_status_scheduled_to_cancel(
    mock_webhook, get_mock_webhook_event, client, configured_stripe_user
):
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="customer.subscription.updated"
    )
    membership = baker.make(Membership, name="membership1")
    # booking before end date
    booking = baker.make_recipe(
        "booking.booking", 
        user=configured_stripe_user, 
        event__date=datetime(2024, 1, 10, tzinfo=datetime_tz.utc)
    )
    booking1 = baker.make_recipe(
        "booking.booking", 
        user=configured_stripe_user, 
        event__event_type=booking.event.event_type,
        event__date=datetime(2024, 2, 10, tzinfo=datetime_tz.utc)
    )
    baker.make("booking.MembershipItem", event_type=booking.event.event_type, quantity=4, membership=membership)
    user_membership = baker.make(
        UserMembership, membership=membership, user=configured_stripe_user, subscription_id="id",
        subscription_status="active"
    )
    booking.membership = user_membership
    booking.save()
    booking1.membership = user_membership
    booking1.save()

    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="customer.subscription.updated", 
        status="active",
        canceled_at=None,
        cancel_at=(datetime(2024, 1, 25)).timestamp(),
    )
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200, resp.content
    assert len(mail.outbox) == 0
    user_membership.refresh_from_db()
    assert user_membership.subscription_status == "active"
    assert user_membership.subscription_end_date == datetime(2024, 1, 25, tzinfo=datetime_tz.utc)
    assert user_membership.end_date == datetime(2024, 2, 1, tzinfo=datetime_tz.utc)

    booking.refresh_from_db()
    booking1.refresh_from_db()
    assert booking.membership == user_membership
    assert booking1.membership is None
    assert booking1.paid is False


@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_subscription_updated_status_scheduled_to_cancel_removed(
    mock_webhook, get_mock_webhook_event, client, configured_stripe_user
):
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="customer.subscription.updated"
    )
    membership = baker.make(Membership, name="membership1")
    user_membership = baker.make(
        UserMembership, membership=membership, user=configured_stripe_user, subscription_id="id",
        subscription_status="active", 
        subscription_end_date=datetime(2024, 4, 25, tzinfo=datetime_tz.utc),
        end_date=datetime(2024, 5, 1, tzinfo=datetime_tz.utc),

    )
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="customer.subscription.updated", 
        status="active",
        canceled_at=None,
        cancel_at=None,
    )
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200, resp.content
    assert len(mail.outbox) == 0
    user_membership.refresh_from_db()
    assert user_membership.subscription_status == "active"
    assert user_membership.subscription_end_date is None
    assert user_membership.end_date is None


@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_subscription_updated_price_changed(
    mock_webhook, get_mock_webhook_event, client, configured_stripe_user
):
    # price changed (only if changed from stripe, user changes create a schedule)
    # If changed by admin user, also creates schedule, but the new price_id should
    # already be set on the UserMembership
    # sends emails to support and changes membersip
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="customer.subscription.updated"
    )
    membership = baker.make(Membership, name="membership1")
    membership1 = baker.make(Membership, name="membership1")
    membership1.stripe_price_id = "price_abc"
    membership1.save()

    assert membership.stripe_price_id == "price_1234"
    assert membership1.stripe_price_id == "price_abc"

    user_membership = baker.make(
        UserMembership, membership=membership, user=configured_stripe_user, subscription_id="id",
        subscription_status="active",
    )
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
        webhook_event_type="customer.subscription.updated", 
        status="active",
        items=Mock(data=[Mock(price=Mock(id="price_abc"))]),
        cancel_at=None,
    )
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200, resp.content
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [settings.SUPPORT_EMAIL]
    user_membership.refresh_from_db()
    assert user_membership.membership == membership1


@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_source_expiring(
    mock_webhook, get_mock_webhook_event, client, configured_stripe_user
):
    webhook_event = get_mock_webhook_event(
       webhook_event_type="customer.source.expiring",
       object="card",
       customer="cus-1"
    )
    mock_webhook.construct_event.return_value = webhook_event
    # sends email to user with link to membership page to update payment method
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200, resp.content
    assert len(mail.outbox) == 1
    assert "Action required - Update your membership payment method" in mail.outbox[0].subject


@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_invoice_upcoming(
    mock_webhook, get_mock_webhook_event, client, configured_stripe_user
):
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
       webhook_event_type="invoice.upcoming",
       object="card",
       customer="cus-1",
    )
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200, resp.content
    assert len(mail.outbox) == 1
    assert "Your membership will renew soon" in mail.outbox[0].subject


@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_invoice_finalised(
    mock_webhook, get_mock_webhook_event, client
):
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
       webhook_event_type="invoice.finalized",
       id="id",
       customer="cus-1",
       subscription="sub-1",
       status="finalized",
       total=1000, 
       effective_at=datetime(2024, 2, 25).timestamp(),
       discount=None,
    )
    assert not StripeSubscriptionInvoice.objects.exists()
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200, resp.content
    assert len(mail.outbox) == 0

    sub_inv = StripeSubscriptionInvoice.objects.first()
    assert sub_inv.total == 10
    assert sub_inv.invoice_date == datetime(2024, 2, 25, tzinfo=datetime_tz.utc)


@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_invoice_paid(
    mock_webhook, get_mock_webhook_event, client
):
    sub_inv = baker.make(StripeSubscriptionInvoice, invoice_id="foo", status="pendign")
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
       webhook_event_type="invoice.paid",
       id="foo",
       customer="cus-1",
       subscription="sub-1",
       status="paid",
       total=1000, 
       effective_at=datetime(2024, 2, 25).timestamp(),
       discount=None,
    )
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200, resp.content
    assert len(mail.outbox) == 0

    sub_inv.refresh_from_db()
    assert sub_inv.status == "paid"


@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_payment_intent_succeeded_for_subscription(
    mock_webhook, get_mock_webhook_event, client
):
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
       webhook_event_type="payment_intent.succeeded"
    )
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200, resp.content
    assert len(mail.outbox) == 0


@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_payment_intent_failed_for_subscription(
    mock_webhook, get_mock_webhook_event, client
):
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
       webhook_event_type="payment_intent.payment_failed"
    )
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200, resp.content
    assert len(mail.outbox) == 0

@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_refunded_for_subscription(
    mock_webhook, get_mock_webhook_event, client
):
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
       webhook_event_type="charge.refunded",
    )
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200, resp.content
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [settings.SUPPORT_EMAIL]


@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_refund_updated_for_subscription(
    mock_webhook, get_mock_webhook_event, client
):
    mock_webhook.construct_event.return_value = get_mock_webhook_event(
       webhook_event_type="charge.refund.updated",
    )
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200, resp.content
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [settings.SUPPORT_EMAIL]


@patch("stripe_payments.views.webhook.get_invoice_from_event_metadata")
@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_unexpected_exception(
    mock_webhook, mock_get_invoice, get_mock_webhook_event, client
):
    mock_webhook.construct_event.return_value = get_mock_webhook_event()
    mock_get_invoice.side_effect = Exception("err")
    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 400, resp.content
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [settings.SUPPORT_EMAIL]


@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_product_updated_for_subscription(
    mock_webhook, get_mock_webhook_event, client
):
    membership = baker.make(Membership, name="Membership-1", active=False)
    assert membership.stripe_product_id == "membership-1"
    event_object = get_mock_webhook_event(
       webhook_event_type="product.updated",
       active=True,
       id="membership-1",
       description="Test",
       name="Foo"
    )
    mock_webhook.construct_event.return_value = event_object

    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200, resp.content
    assert len(mail.outbox) == 0
    membership.refresh_from_db()
    assert membership.active is True
    assert membership.description == "Test"
    assert membership.name == "Foo"


@patch("booking.models.membership_models.StripeConnector", MockConnector)
@patch("stripe_payments.views.webhook.stripe.Webhook")
def test_webhook_product_updated_no_matching_subscription(
    mock_webhook, get_mock_webhook_event, client
):
    membership = baker.make(Membership, name="Membership-2", active=False)
    event_object = get_mock_webhook_event(
       webhook_event_type="product.updated",
       active=True,
       id="membership-1",
       description="Test",
       name="Foo"
    )
    mock_webhook.construct_event.return_value = event_object

    resp = client.post(webhook_url, data={}, HTTP_STRIPE_SIGNATURE="foo")
    assert resp.status_code == 200, resp.content
    assert len(mail.outbox) == 0
    membership.refresh_from_db()
    assert membership.active is False
    assert membership.name == "Membership-2"