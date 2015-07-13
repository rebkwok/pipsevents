from django.conf.urls import patterns, url
from accounts.views import ProfileUpdateView

urlpatterns = patterns('',
    url(r'^update/$', ProfileUpdateView.as_view(), name='update_profile'),
    url(r'^$', 'accounts.views.profile', name='profile'),
    )
