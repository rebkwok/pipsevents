from django.conf.urls import patterns, url

from booking.views import EventListView, EventDetailView, BookingListView, \
    BookingHistoryListView, BookingCreateView, BookingUpdateView, \
    BookingDetailView, BookingDeleteView


urlpatterns = patterns('',
    url(r'^bookings/$', BookingListView.as_view(), name='bookings'),
    url(r'^booking-history/$', BookingHistoryListView.as_view(), name='booking_history'),
    url(r'^booking/create/$', BookingCreateView.as_view(), name='create_booking'),
    url(r'^booking/update/(?P<pk>\d+)/$', BookingUpdateView.as_view(), name='update_booking'),
    url(r'^booking/delete/(?P<pk>\d+)/$', BookingDeleteView.as_view(), name='delete_booking'),
    url(r'^booking/(?P<pk>\d+)/$', BookingDetailView.as_view(), name='booking_detail'),
    url(r'^(?P<event_slug>[\w-]+)/book/$', BookingCreateView.as_view(), name='book_event'),
    url(r'^(?P<slug>[\w-]+)/$', EventDetailView.as_view(), name='event_detail'),
    url(r'^$', EventListView.as_view(), name='events'),
    )