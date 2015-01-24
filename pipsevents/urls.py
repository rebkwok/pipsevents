from django.conf.urls import patterns, include, url
from django.contrib import admin

urlpatterns = patterns('',
    url(r'^admin/', include(admin.site.urls)),
    url(r'^', include('booking.urls', namespace='booking')),
    (r'^accounts/', include('allauth.urls')),
    url(r'^accounts/profile/', include('accounts.urls', namespace='profile')),
)
