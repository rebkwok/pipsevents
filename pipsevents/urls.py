from django.urls import include, path, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.views.generic import RedirectView

from accounts.views import custom_email_view, CustomLoginView, \
    DisclaimerCreateView, data_protection, subscribe_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('studioadmin/', include('studioadmin.urls')),
    path('', include('booking.urls')),
    path(
        'data-protection-statement/', data_protection, name='data_protection'
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
    path('favicon.ico/',
        RedirectView.as_view(url=settings.STATIC_URL+'favicon.ico',
                             permanent=False)),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:  # pragma: no cover
    import debug_toolbar
    urlpatterns.append(path('__debug__/', include(debug_toolbar.urls)))
