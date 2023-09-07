from unittest.mock import patch, Mock

from django.core import mail
from django.urls import reverse

from model_bakery import baker
import pytest

from ..models import Seller

pytestmark = pytest.mark.django_db


# connect stripe
connect_url = reverse("stripe_payments:connect_stripe")

def test_connect_stripe_view_superuser_required(client, configured_user, superuser):
    resp = client.get(connect_url)
    assert resp.status_code == 302

    client.force_login(configured_user)
    resp = client.get(connect_url)
    assert resp.status_code == 302
    
    configured_user.is_staff = True
    configured_user.save()
    resp = client.get(connect_url)
    assert resp.status_code == 200
    assert "You do not have permission to connect a Stripe account" in resp.content.decode()

    client.force_login(superuser)
    resp = client.get(connect_url)
    assert resp.status_code == 200


def test_connect_stripe_view_not_connected(client, superuser):
    assert not Seller.objects.exists()
    client.force_login(superuser)
    resp = client.get(connect_url)
    assert resp.context["site_seller"] is None
    assert "Connect Stripe Account" in resp.content.decode()


def test_connect_stripe_view_connected(client, superuser, seller):
    seller.user = superuser
    seller.stripe_user_id = "stripe-account-id"
    seller.save()
    client.force_login(superuser)
    resp = client.get(connect_url)
    assert resp.context["site_seller"] == seller
    assert f"Your Stripe account id <strong>{seller.stripe_user_id}</strong> is connected" in resp.content.decode()


def test_connect_stripe_view_other_user_connected(client, superuser, seller):
    client.force_login(superuser)
    resp = client.get(connect_url)
    assert resp.context["site_seller"] == seller
    assert f"A Stripe account is already connected for this site" in resp.content.decode()


# StripeAuthorizeView
authorize_url = reverse("stripe_payments:authorize_stripe")

def test_stripe_authorize_view_superuser_required(client, configured_user, superuser):
    resp = client.get(authorize_url)
    assert resp.status_code == 302
    assert reverse("account_login") in resp.url

    client.force_login(configured_user)
    resp = client.get(authorize_url)
    assert resp.status_code == 302
    
    client.force_login(superuser)
    resp = client.get(authorize_url)
    assert resp.status_code == 302
    assert "https://connect.stripe.com/oauth/authorize" in resp.url


# StripeAuthorizeCallbackView
authorize_callback_url = reverse("stripe_payments:authorize_stripe_callback")


@patch("stripe_payments.connection_views.requests")
def test_stripe_authorize_callback_view(mock_requests, client, superuser):
    client.force_login(superuser)
    assert not Seller.objects.exists()

    class MockJsonResponse:
        def json(self):
            return {
        'stripe_user_id': "test-id",
        'access_token': "token-1",
        'refresh_token': "token-2"
    }

    mock_requests.post.return_value = MockJsonResponse()
    resp = client.get(authorize_callback_url + "?code=foo", follow=True)
    assert Seller.objects.exists()
    # redirects to connect view
    assert "Your Stripe account id <strong>test-id</strong> is connected" in resp.content.decode()


@patch("stripe_payments.connection_views.requests")
def test_stripe_authorize_callback_view_no_code(mock_requests, client, superuser):
    client.force_login(superuser)
    assert not Seller.objects.exists()
    resp = client.get(authorize_callback_url, follow=True)
    assert not Seller.objects.exists()
    # redirects to connect view
    assert "Connect Stripe Account" in resp.content.decode()
