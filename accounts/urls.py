from django.urls import path
from accounts.views import ProfileUpdateView, profile, \
    SignedDataPrivacyCreateView


app_name = 'profile'


urlpatterns = [
    path('update/', ProfileUpdateView.as_view(), name='update_profile'),
    path(
        'data-privacy-review/', SignedDataPrivacyCreateView.as_view(),
         name='data_privacy_review'
    ),
    path('', profile, name='profile'),
]
