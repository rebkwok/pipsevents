from django.urls import path
from accounts.views import ProfileUpdateView, profile


app_name = 'profile'


urlpatterns = [
    path('update', ProfileUpdateView.as_view(), name='update_profile'),
    path('', profile, name='profile'),
    ]
