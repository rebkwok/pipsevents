from django.conf.urls import url
from accounts.api_views import MailingListAPIView


urlpatterns = [
    url(
        r'^mailinglist/$', MailingListAPIView.as_view(),
        name='mailing_list_api'
    ),
]
