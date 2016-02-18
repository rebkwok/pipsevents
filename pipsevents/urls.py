from django.conf.urls import include, url
from django.conf import settings
from django.contrib import admin
from django.views.generic import RedirectView
from django.conf.urls.static import static

from accounts.views import CustomLoginView, DisclaimerCreateView, \
    data_protection

urlpatterns = [
    url(r'^admin/', include(admin.site.urls)),
    url(r'^studioadmin/',
        include('studioadmin.urls', namespace='studioadmin')),
    url(r'^', include('booking.urls', namespace='booking')),
    url(
        r'^data-protection-statement/$', data_protection,
        name='data_protection'
    ),
    url(r'^accounts/profile/', include('accounts.urls', namespace='profile')),
    url(r'^accounts/login/$', CustomLoginView.as_view(), name='login'),
    url(
        r'^accounts/disclaimer/$', DisclaimerCreateView.as_view(),
        name='disclaimer_form'
    ),
    url(r'^accounts/', include('allauth.urls')),
    url(r'^ckeditor/', include('ckeditor_uploader.urls')),
    url(r'^payments/ipn-paypal-notify/', include('paypal.standard.ipn.urls')),
    url(r'payments/', include('payments.urls', namespace='payments')),
    url(r'^favicon.ico/$',
        RedirectView.as_view(url=settings.STATIC_URL+'favicon.ico',
                             permanent=False)),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:  # pragma: no cover
    import debug_toolbar
    urlpatterns.append(url(r'^__debug__/', include(debug_toolbar.urls)))

