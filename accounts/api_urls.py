from django.urls import path
from accounts.api_views import MailingListAPIView


app_name = 'accounts_api'


urlpatterns = [
    path(
        'mailinglist/', MailingListAPIView.as_view(),
        name='mailing_list_api'
    ),
]
