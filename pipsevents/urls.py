from django.conf.urls import patterns, include, url
from django.conf import settings
from django.contrib import admin

urlpatterns = patterns('',
    url(r'^admin/', include(admin.site.urls)),
    url(r'^', include('booking.urls', namespace='booking')),
    (r'^accounts/', include('allauth.urls')),
    url(r'^accounts/profile/', include('accounts.urls', namespace='profile')),
)

if settings.DEBUG:
    import debug_toolbar
    urlpatterns += patterns('',
        url(r'^__debug__/', include(debug_toolbar.urls)),
    )