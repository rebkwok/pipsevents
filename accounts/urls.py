from django.urls import path
from accounts.views import ProfileUpdateView, profile, \
    SignedDataProtectionCreateView


app_name = 'profile'


urlpatterns = [
    path('update/', ProfileUpdateView.as_view(), name='update_profile'),
    path(
        'data-protection-review/', SignedDataProtectionCreateView.as_view(),
         name='data_protection_review'
    ),
    path('', profile, name='profile'),
]
