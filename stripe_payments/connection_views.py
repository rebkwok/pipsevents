from urllib.parse import urlencode
import logging

import requests

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.sites.models import Site
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.generic import View

from braces.views import LoginRequiredMixin, StaffuserRequiredMixin

from activitylog.models import ActivityLog
from stripe_payments.models import Seller


logger = logging.getLogger(__name__)


@staff_member_required
def connect_stripe_view(request):
    site_sellers = Seller.objects.filter(site=Site.objects.get_current(request))
    site_seller = site_sellers.first() if site_sellers else None
    return render(request, "stripe_payments/connect_stripe.html", {"site_seller": site_seller})


class StripeAuthorizeView(LoginRequiredMixin, StaffuserRequiredMixin, View):

    def get(self, request):
        url = 'https://connect.stripe.com/oauth/authorize'
        params = {
            'response_type': 'code',
            'scope': 'read_write',
            'client_id': settings.STRIPE_CONNECT_CLIENT_ID,
            'redirect_uri': request.build_absolute_uri(reverse("stripe_payments:authorize_stripe_callback")),
        }
        url = f'{url}?{urlencode(params)}'
        return redirect(url)


class StripeAuthorizeCallbackView(View):

    def get(self, request):
        code = request.GET.get('code')
        if code:
            data = {
                'client_secret': settings.STRIPE_SECRET_KEY,
                'grant_type': 'authorization_code',
                'client_id': settings.STRIPE_CONNECT_CLIENT_ID,
                'code': code
            }
            url = 'https://connect.stripe.com/oauth/token'
            resp = requests.post(url, params=data)
            # add stripe info to the seller
            resp_data = resp.json()
            stripe_user_id = resp_data['stripe_user_id']
            stripe_access_token = resp_data['access_token']
            stripe_refresh_token = resp_data['refresh_token']
            seller, _ = Seller.objects.get_or_create(user_id=self.request.user.id)
            seller.site = Site.objects.get_current(request)
            seller.stripe_access_token = stripe_access_token
            seller.stripe_refresh_token = stripe_refresh_token
            seller.stripe_user_id = stripe_user_id
            seller.save()
            logger.info(f"Stripe account connected: %s", seller.stripe_user_id)
            ActivityLog.objects.create(log=f"Stripe account connected: {seller.stripe_user_id}")
        return redirect(reverse('stripe_payments:connect_stripe'))
