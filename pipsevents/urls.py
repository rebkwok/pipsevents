from django.urls import include, path, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.views.generic import RedirectView

from accounts.views import custom_email_view, CustomLoginView, \
    DisclaimerCreateView, data_privacy_policy, cookie_policy, subscribe_view, \
    NonRegisteredDisclaimerCreateView, nonregistered_disclaimer_submitted
from booking.views import stripe_checkout, membership_create, stripe_subscription_checkout, \
    subscription_create, membership_status, membership_change, MembershipListView, subscription_cancel

urlpatterns = [
    path('admin/', admin.site.urls),
    path('studioadmin/', include('studioadmin.urls')),
    path('', include('booking.urls')),
    path(
        'data-privacy-policy/', data_privacy_policy, name='data_privacy_policy'
    ),
    path(
        'cookie-policy/', cookie_policy, name='cookie_policy'
    ),
    path(
        'event-disclaimer/', NonRegisteredDisclaimerCreateView.as_view(),
        name='nonregistered_disclaimer_form'
    ),
    path(
        'event-disclaimer/complete', nonregistered_disclaimer_submitted,
        name='nonregistered_disclaimer_submitted'
    ),
    path('accounts/api/', include('accounts.api_urls')),
    path('accounts/profile/', include('accounts.urls')),
    path('accounts/login/', CustomLoginView.as_view(), name='login'),
    path(
        'accounts/disclaimer/', DisclaimerCreateView.as_view(),
        name='disclaimer_form'
    ),
    path('accounts/mailing-list/', subscribe_view, name='subscribe'),
    path('accounts/email/', custom_email_view, name="account_email"),
    path('accounts/', include('allauth.urls')),
    path('ckeditor/', include('ckeditor_uploader.urls')),
    path('payments/ipn-paypal-notify/', include('paypal.standard.ipn.urls')),
    path('payments/', include('payments.urls')),
    path('stripe/', include('stripe_payments.urls')),
    path('checkout/', stripe_checkout, name='stripe_checkout'),
    # memberships
    path('membership/checkout/', stripe_subscription_checkout, name='membership_checkout'),
    path('membership/create/', membership_create, name='membership_create'),
    path('membership/<str:subscription_id>/change/', membership_change, name='membership_change'),
    path('membership/<str:subscription_id>/', membership_status, name='membership_status'),
    path('membership/subscription/create/', subscription_create, name='subscription_create'),
    path('membership/subscription/<str:subscription_id>/cancel/', subscription_cancel, name='subscription_cancel'),
    path('memberships/', MembershipListView.as_view(), name='membership_list'),
    path('favicon.ico/',
        RedirectView.as_view(url=settings.STATIC_URL+'favicon.ico',
                             permanent=False)),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:  # pragma: no cover
    import debug_toolbar
    urlpatterns.append(path('__debug__/', include(debug_toolbar.urls)))
