from django.conf.urls import patterns, url

urlpatterns = patterns(
    'accounts.views',
    url(r'$', 'profile', name='profile'),
    )