from django.urls import path
from .views import (
    stripe_payment_complete, stripe_webhook, stripe_payment_status
)
from .connection_views import connect_stripe_view, StripeAuthorizeView, StripeAuthorizeCallbackView


app_name = 'stripe_payments'

urlpatterns = [
    # connecting stripe seller account
    path("connect/", connect_stripe_view, name="connect_stripe"),
    path("authorize/", StripeAuthorizeView.as_view(), name="authorize_stripe"),
    path("oauth/callback/", StripeAuthorizeCallbackView.as_view(), name="authorize_stripe_callback"),
    # transactions
    path('payment-complete/', stripe_payment_complete, name="stripe_payment_complete"),
    path('payment-status/<str:payment_intent_id>/', stripe_payment_status, name="stripe_payment_status"),
    path('webhook/', stripe_webhook, name="stripe_webhook"),
]
