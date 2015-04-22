from django.conf.urls import patterns, include, url
from django.conf import settings
from django.contrib import admin
from django.views.generic import RedirectView
from django.conf.urls.static import static

urlpatterns = patterns('',
    url(r'^admin/', include(admin.site.urls)),
    url(r'^', include('booking.urls', namespace='booking')),
    url(r'^accounts/profile/', include('accounts.urls', namespace='profile')),
    (r'^accounts/', include('allauth.urls')),
    (r'^ckeditor/', include('ckeditor.urls')),
    (r'^payments/ipn-paypal-notify/', include('paypal.standard.ipn.urls')),
    url(r'payments/', include('payments.urls', namespace='payments')),
    url(r'^favicon.ico/$',
        RedirectView.as_view(url=settings.STATIC_URL+'favicon.ico',
                             permanent=False)),
) + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    import debug_toolbar
    urlpatterns += patterns('',
        url(r'^__debug__/', include(debug_toolbar.urls)),
    )
