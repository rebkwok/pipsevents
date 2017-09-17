from django.conf.urls import url
from accounts.api_views import MailingListAPIView
from accounts.views import ProfileUpdateView, profile

urlpatterns = [
    url(r'^update/$', ProfileUpdateView.as_view(), name='update_profile'),
    url(r'^$', profile, name='profile'),
    ]
