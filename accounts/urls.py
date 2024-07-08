from django.urls import path
from accounts.views import ProfileUpdateView, profile, \
    SignedDataPrivacyCreateView, user_disclaimer


app_name = 'profile'


urlpatterns = [
    path('update/', ProfileUpdateView.as_view(), name='update_profile'),
    path(
        'data-privacy-review/', SignedDataPrivacyCreateView.as_view(),
         name='data_privacy_review'
    ),
    path("disclaimer", user_disclaimer, name='view_latest_disclaimer'),
    path('', profile, name='profile'),
]
