from datetime import timedelta
from unittest.mock import patch, call
import pytest
import re

from django.urls import reverse
from django.utils import timezone

from model_bakery import baker

from booking.models import Membership, MembershipItem, UserMembership
from stripe_payments.tests.mock_connector import MockConnector
from conftest import get_mock_subscription

pytestmark = pytest.mark.django_db

memberships_url = reverse("studioadmin:memberships_list")
membership_create_url = reverse("studioadmin:membership_add")


@pytest.fixture()
def purchasable_membership(seller):
    with patch("booking.models.membership_models.StripeConnector", MockConnector):
        mem = baker.make(Membership, name="m")
    baker.make(MembershipItem, membership=mem, quantity=5)
    yield mem


def test_membership_list_staff_only(client, configured_user, staff_user, instructor_user):
    resp = client.get(memberships_url)
    assert resp.status_code == 302

    client.force_login(configured_user)
    resp = client.get(memberships_url)
    assert resp.status_code == 302

    client.force_login(instructor_user)
    resp = client.get(memberships_url)
    assert resp.status_code == 302

    client.force_login(staff_user)
    resp = client.get(memberships_url)
    assert resp.status_code == 200


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_list(client, staff_user, purchasable_membership):
    client.force_login(staff_user)

    # inactive but configured
    inactive_membership = baker.make(Membership, name="unp", active=False)
    baker.make(MembershipItem, membership=inactive_membership, quantity=5)

    # active but unconfigured
    baker.make(Membership, name="unc", active=True)

    # active and purchased
    purchased = baker.make(Membership, name="purchased")
    baker.make(MembershipItem, membership=purchased, quantity=5)
    baker.make(UserMembership, membership=purchased)

    resp = client.get(memberships_url)

    assert resp.context_data["memberships"].count() == 4

    # 1 membership is unconfigured
    assert len(re.findall("fa-exclamation-triangle", resp.rendered_content)) == 1

    # 1 membership is undeleteable
    assert len(re.findall("fa-ban", resp.rendered_content)) == 1


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_list_user_memberships(client, staff_user, purchasable_membership):
    client.force_login(staff_user)

    baker.make(UserMembership, membership=purchasable_membership, subscription_status="canceled")
    baker.make(UserMembership, membership=purchasable_membership, subscription_status="active", _quantity=2)
    baker.make(UserMembership, membership=purchasable_membership, subscription_status="active", end_date=timezone.now() + timedelta(1))
    resp = client.get(memberships_url)
    assert "2 (1)" in resp.rendered_content


def test_membership_create_get_staff_only(client,  configured_user, staff_user, instructor_user):
    resp = client.get(membership_create_url)
    assert resp.status_code == 302

    client.force_login(configured_user)
    resp = client.get(membership_create_url)
    assert resp.status_code == 302

    client.force_login(instructor_user)
    resp = client.get(membership_create_url)
    assert resp.status_code == 302

    client.force_login(staff_user)
    resp = client.get(membership_create_url)
    assert resp.status_code == 200


def test_membership_create_get_event_type_options(client, staff_user):

    event_type = baker.make_recipe("booking.event_type_PC")
    event_type1 = baker.make_recipe("booking.event_type_OC")
    event_type2 = baker.make_recipe("booking.event_type_PP")

    client.force_login(staff_user)
    resp = client.get(membership_create_url)
    formset = resp.context_data["formset"]
    assert set(formset.forms[0].fields["event_type"].queryset) == {event_type, event_type1, event_type2}


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_create_no_items(client, seller, staff_user):
    client.force_login(staff_user)
    assert not Membership.objects.exists()
    resp = client.post(
        membership_create_url,
        {
            "name": "Test", 
            "description": "A description", 
            "price": 10, 
            "active": True
        }    
    )
    assert resp.status_code == 200
    assert Membership.objects.count() == 1 


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_create_with_items(client, seller, staff_user):
    client.force_login(staff_user)
    assert not Membership.objects.exists()
    event_type = baker.make_recipe("booking.event_type_PC")
    baker.make_recipe("booking.event_type_OC")

    resp = client.post(
        membership_create_url,
        {
            "name": "Test", 
            "description": "A description", 
            "price": 10, 
            "active": True,
            'membership_items-TOTAL_FORMS': 2,
            'membership_items-INITIAL_FORMS': 0,
            'membership_items-0-event_type': event_type.id,
            'membership_items-0-quantity': 2,
            'membership_items-0-membership': '',
            'membership_items-1-event_type': '',
            'membership_items-1-quantity': '',
            'membership_items-1-membership': '',
        }    
    )
    assert resp.status_code == 302
    assert resp.url == memberships_url
    assert Membership.objects.count() == 1 
    assert Membership.objects.first().membership_items.count() == 1


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_create_with_form_errors(client, seller, staff_user):
    client.force_login(staff_user)
    assert not Membership.objects.exists()
    event_type = baker.make_recipe("booking.event_type_PC")
    baker.make_recipe("booking.event_type_OC")

    resp = client.post(
        membership_create_url,
        {
            "name": "Test", 
            "description": "", 
            "price": 10, 
            "active": True,
            'membership_items-TOTAL_FORMS': 1,
            'membership_items-INITIAL_FORMS': 0,
            'membership_items-0-event_type': event_type.id,
            'membership_items-0-quantity': 2,
            'membership_items-0-membership': '',
        }    
    )
    assert resp.status_code == 200
    assert not resp.context_data["form"].is_valid()    
    assert resp.context_data["form"].errors == {"description": ["This field is required."]}


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_create_with_formset_errors(client, seller, staff_user):
    client.force_login(staff_user)
    assert not Membership.objects.exists()
    event_type = baker.make_recipe("booking.event_type_PC")
    baker.make_recipe("booking.event_type_OC")

    resp = client.post(
        membership_create_url,
        {
            "name": "Test", 
            "description": "A description", 
            "price": 10, 
            "active": True,
            'membership_items-TOTAL_FORMS': 1,
            'membership_items-INITIAL_FORMS': 0,
            'membership_items-0-event_type': event_type.id,
            'membership_items-0-quantity': '',
            'membership_items-0-membership': '',
        }    
    )
    assert resp.status_code == 200
    assert resp.context_data["form"].is_valid()
    assert not resp.context_data["formset"].is_valid()
    assert resp.context_data["formset"].errors == [{"quantity": ["This field is required."]}]


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_edit(client, seller, staff_user, purchasable_membership):
    client.force_login(staff_user)
    assert Membership.objects.count() == 1 
    event_type = baker.make_recipe("booking.event_type_PC")

    resp = client.post(
        reverse("studioadmin:membership_edit", args=(purchasable_membership.id,)),
        {   
            "id": purchasable_membership.id,
            "name": "Test", 
            "description": "A description", 
            "price": 10, 
            "active": True,
            'membership_items-TOTAL_FORMS': 1,
            'membership_items-INITIAL_FORMS': 1,
            'membership_items-0-id': purchasable_membership.membership_items.first().id,
            'membership_items-0-event_type': event_type.id,
            'membership_items-0-quantity': 2,
            'membership_items-0-membership': str(purchasable_membership.id),
        }    
    )
    assert resp.status_code == 302
    assert resp.url == memberships_url
    assert Membership.objects.count() == 1 

    membership = Membership.objects.get(id=purchasable_membership.id)
    assert membership.name == "Test"
    assert membership.membership_items.count() == 1
    assert membership.membership_items.first().event_type == event_type


@patch("booking.models.membership_models.StripeConnector")
def test_membership_delete(mock_connector, client, seller, staff_user, purchasable_membership):
    conn = MockConnector()
    mock_connector.return_value = conn

    client.force_login(staff_user)
    assert Membership.objects.count() == 1 
    resp = client.post(reverse("studioadmin:membership_delete", args=(purchasable_membership.id,)))
    assert resp.status_code == 302
    assert resp.url == memberships_url
    assert not Membership.objects.exists()
    assert conn.method_calls == {'archive_stripe_product': [{'args': ('m', 'price_1234'), 'kwargs': {}}]}


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_purchased_membership_cannot_delete(client, seller, staff_user, purchasable_membership):
    baker.make(UserMembership, membership=purchasable_membership)
    client.force_login(staff_user)
    assert Membership.objects.count() == 1
    resp = client.post(reverse("studioadmin:membership_delete", args=(purchasable_membership.id,)))
    assert resp.status_code == 302
    assert resp.url == memberships_url
    assert Membership.objects.count() == 1 


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_deactivate_get(client, seller, staff_user, purchasable_membership):
    client.force_login(staff_user)
    resp = client.get(reverse("studioadmin:membership_deactivate", args=(purchasable_membership.id,)))
    assert resp.status_code == 200


@patch("booking.models.membership_models.StripeConnector")
def test_membership_deactivate_no_user_memberships(mock_connector, client, seller, staff_user, purchasable_membership):
    conn = MockConnector()
    mock_connector.return_value = conn

    client.force_login(staff_user)
    assert Membership.objects.count() == 1 
    resp = client.post(reverse("studioadmin:membership_deactivate", args=(purchasable_membership.id,)))
    assert resp.status_code == 302
    assert resp.url == memberships_url
    
    # membership still exists
    assert Membership.objects.exists()
    # called to archive (active = False)
    assert conn.method_calls == {
        'update_stripe_product': [
            {
                'args': (), 
                'kwargs': {
                    'product_id': 'm', 
                    'name': 'm', 
                    'description': None, 
                    'active': False, 
                    'price_id': 'price_1234'
                }
            }
        ]
    }


@patch("booking.models.membership_models.StripeConnector")
def test_membership_deactivate_no_active_user_memberships(mock_connector, client, seller, staff_user, purchasable_membership):
    conn = MockConnector()
    mock_connector.return_value = conn

    baker.make(UserMembership, membership=purchasable_membership, subscription_status="canceled")
    client.force_login(staff_user)
    resp = client.post(reverse("studioadmin:membership_deactivate", args=(purchasable_membership.id,)))
    assert resp.status_code == 302
    assert resp.url == memberships_url
    
    # membership still exists
    assert Membership.objects.exists()
    # called to archive (active = False)
    assert conn.method_calls == {
        'update_stripe_product': [
            {
                'args': (), 
                'kwargs': {
                    'product_id': 'm', 
                    'name': 'm', 
                    'description': None, 
                    'active': False, 
                    'price_id': 'price_1234'
                }
            }
        ]
    }


@patch("booking.models.membership_models.StripeConnector")
@patch("studioadmin.views.memberships.StripeConnector.get_subscription")
@patch("studioadmin.views.memberships.StripeConnector.cancel_subscription")
def test_membership_deactivate_active_user_memberships(mock_cancel, mock_get_sub, mock_connector, client, seller, staff_user, purchasable_membership):
    conn = MockConnector()
    mock_connector.return_value = conn

    mock_start = timezone.now() - timedelta(30)
    mock_end = timezone.now() + timedelta(30)
    mock_future_start = timezone.now() + timedelta(10)
    # active subscriptions are in reverse order by id
    mock_get_sub.side_effect = [
        get_mock_subscription(None, id="s4", status="active", cancel_at=None, canceled_at=None, start_date=mock_future_start.timestamp()),
        get_mock_subscription(None, id="s3", status="active", cancel_at=mock_end.timestamp(), canceled_at=None, start_date=mock_start.timestamp()),
        get_mock_subscription(None, id="s2", status="active", cancel_at=None, canceled_at=None),
    ]

    # cancelled already
    baker.make(UserMembership, subscription_id="s1", membership=purchasable_membership, subscription_status="canceled", subscription_start_date=timezone.now() - timedelta(30))
    # ongoing
    baker.make(UserMembership, subscription_id="s2", membership=purchasable_membership, subscription_status="active", subscription_start_date=timezone.now() - timedelta(30))
    # cancelling already in future
    baker.make(
        UserMembership, subscription_id="s3", membership=purchasable_membership, 
        subscription_status="active", subscription_start_date=mock_start, subscription_end_date=mock_end
    )
    # starting in future, cancel immediately
    baker.make(
        UserMembership, subscription_id="s4", 
        membership=purchasable_membership, subscription_status="active", 
        subscription_start_date=mock_future_start
    )

    client.force_login(staff_user)
    resp = client.post(reverse("studioadmin:membership_deactivate", args=(purchasable_membership.id,)))
    assert resp.status_code == 302
    assert resp.url == memberships_url
    
    # membership still exists
    assert Membership.objects.exists()
    # called to archive (active = False)
    assert conn.method_calls == {
        'update_stripe_product': [
            {
                'args': (), 
                'kwargs': {
                    'product_id': 'm', 
                    'name': 'm', 
                    'description': None, 
                    'active': False, 
                    'price_id': 'price_1234'
                }
            }
        ]
    }
    assert mock_cancel.call_count == 2
    mock_cancel.assert_has_calls(
        [
            call(subscription_id="s4", cancel_immediately=True),
            call(subscription_id="s2", cancel_immediately=False),
        ]
    )


@patch("booking.models.membership_models.StripeConnector")
@patch("studioadmin.views.memberships.StripeConnector.get_subscription")
def test_membership_deactivate_cancelled_not_up_to_date_user_memberships(mock_get_sub, mock_connector, client, seller, staff_user, purchasable_membership):
    conn = MockConnector()
    mock_connector.return_value = conn
    mock_get_sub.return_value = get_mock_subscription(None, id="s1", status="canceled", cancel_at=None, canceled_at=None)

    # active, but ensure_subscription_up_to_date will return it cancelled
    baker.make(
        UserMembership, subscription_id="s1", membership=purchasable_membership, subscription_status="active", subscription_start_date=timezone.now() - timedelta(30)
    )

    client.force_login(staff_user)
    resp = client.post(reverse("studioadmin:membership_deactivate", args=(purchasable_membership.id,)))
    assert resp.status_code == 302
    assert resp.url == memberships_url
    
    # called to archive (active = False)
    # no call to cancel subscription because it's already cancelled
    assert conn.method_calls == {
        'update_stripe_product': [
            {
                'args': (), 
                'kwargs': {
                    'product_id': 'm', 
                    'name': 'm', 
                    'description': None, 
                    'active': False, 
                    'price_id': 'price_1234'
                }
            }
        ],
    }


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_users(client, seller, staff_user, purchasable_membership):
    baker.make(UserMembership, membership=purchasable_membership, _quantity=3)
    client.force_login(staff_user)

    resp = client.get(
        reverse("studioadmin:membership_users", args=(purchasable_membership.id,)), 
    )
    assert resp.status_code == 200
    assert resp.context_data["membership"] == purchasable_membership


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_email_members(client, seller, staff_user, purchasable_membership):
    baker.make(UserMembership, membership=purchasable_membership, subscription_status="active", _quantity=3)
    baker.make(UserMembership, membership=purchasable_membership, subscription_status="incomplete", _quantity=1)
    client.force_login(staff_user)

    resp = client.get(
        reverse("studioadmin:email_members", args=(purchasable_membership.id,)), 
    )
    assert resp.status_code == 302
    assert resp.url == reverse("studioadmin:email_users_view") + f"?membership={purchasable_membership.id}"
    assert len(client.session["users_to_email"]) == 3


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_email_all_members(client, seller, staff_user):
    baker.make(UserMembership, membership__name="foo", subscription_status="active", _quantity=3)
    baker.make(UserMembership, membership__name="bar", subscription_status="past_due", _quantity=3)
    baker.make(UserMembership, membership__name="baz", subscription_status="incomplete", _quantity=3)
    client.force_login(staff_user)

    resp = client.get(reverse("studioadmin:email_all_members"))
    assert resp.status_code == 302
    assert resp.url == reverse("studioadmin:email_users_view")
    assert len(client.session["users_to_email"]) == 6