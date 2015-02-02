from django.conf.urls import patterns, url
from django.views.generic import RedirectView
from booking.views import EventListView, EventDetailView, BookingListView, \
    BookingHistoryListView, BookingCreateView, BookingUpdateView, \
    BookingDetailView, BookingDeleteView, LessonListView, LessonDetailView


urlpatterns = patterns('',
    url(r'^bookings/$', BookingListView.as_view(), name='bookings'),
    url(r'^booking-history/$', BookingHistoryListView.as_view(), name='booking_history'),
    url(r'^booking/update/(?P<pk>\d+)/$', BookingUpdateView.as_view(), name='update_booking'),
    url(r'^booking/delete/(?P<pk>\d+)/$', BookingDeleteView.as_view(), name='delete_booking'),
    url(r'^booking/(?P<pk>\d+)/$', BookingDetailView.as_view(), name='booking_detail'),
    url(r'^events/(?P<event_slug>[\w-]+)/duplicate/$', 'booking.views.duplicate_booking', name='duplicate_booking'),
    url(r'^events/(?P<event_slug>[\w-]+)/full/$', 'booking.views.fully_booked', name='fully_booked'),
    url(r'^events/(?P<event_slug>[\w-]+)/book/$', BookingCreateView.as_view(), name='book_event'),
    url(r'^events/(?P<slug>[\w-]+)/$', EventDetailView.as_view(), name='event_detail'),
    url(r'^events/$', EventListView.as_view(), name='events'),
    url(r'^classes/(?P<slug>[\w-]+)/$', LessonDetailView.as_view(), name='lesson_detail'),
    url(r'^classes/$', LessonListView.as_view(), name='lessons'),
    url(r'^$', RedirectView.as_view(url='/events/')),
    )