from django.conf.urls import patterns, url

from booking.views import EventListView, EventDetailView, BookingListView, \
    BookingHistoryListView


urlpatterns = patterns('',
    url(r'^bookings/$', BookingListView.as_view(), name='bookings'),
    url(r'^booking-history/$', BookingHistoryListView.as_view(), name='booking_history'),
    url(r'^(?P<slug>[\w-]+)/$', EventDetailView.as_view(), name='event_detail'),
    url(r'^$', EventListView.as_view(), name='events'),
    )