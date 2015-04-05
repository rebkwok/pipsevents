from django.conf.urls import patterns, url
from django.views.generic import RedirectView
from booking.views import EventListView, EventDetailView, BookingListView, \
    BookingHistoryListView, BookingCreateView, BookingUpdateView, \
    BookingDetailView, BookingDeleteView, LessonListView, LessonDetailView, \
    BlockCreateView, BlockListView, BlockUpdateView


urlpatterns = patterns('',
    url(r'^bookings/$', BookingListView.as_view(), name='bookings'),
    url(r'^booking-history/$', BookingHistoryListView.as_view(),
        name='booking_history'),
    url(r'^booking/update/(?P<pk>\d+)/$', BookingUpdateView.as_view(),
        name='update_booking'),
    url(r'^booking/cancel/(?P<pk>\d+)/$', BookingDeleteView.as_view(),
        name='delete_booking'),
    url(r'^events/(?P<event_slug>[\w-]+)/cancellation-period-past/$',
        'booking.views.cancellation_period_past', name='cancellation_period_past'),
    url(r'^booking/(?P<pk>\d+)/$', BookingDetailView.as_view(),
        name='booking_detail'),
    url(r'^events/(?P<event_slug>[\w-]+)/duplicate/$',
        'booking.views.duplicate_booking', name='duplicate_booking'),
    url(r'^events/(?P<event_slug>[\w-]+)/full/$', 'booking.views.fully_booked',
        name='fully_booked'),
    url(r'^events/(?P<event_slug>[\w-]+)/book/$', BookingCreateView.as_view(),
        name='book_event'),
    url(r'^events/(?P<slug>[\w-]+)/$', EventDetailView.as_view(),
        name='event_detail'),
    url(r'^events/$', EventListView.as_view(), name='events'),
    url(r'^classes/(?P<slug>[\w-]+)/$', LessonDetailView.as_view(),
        name='lesson_detail'),
    url(r'^classes/$', LessonListView.as_view(), name='lessons'),
    url(r'^blocks/$', BlockListView.as_view(), name='block_list'),
    url(r'^blocks/new/$', BlockCreateView.as_view(), name='add_block'),
    url(r'^blocks/update/(?P<pk>\d+)/$', BlockUpdateView.as_view(),
        name='update_block'),
    url(r'^blocks/existing/$', 'booking.views.has_active_block',
        name='has_active_block'),
    url(r'^$', RedirectView.as_view(url='/classes/', permanent=True)),
    )
