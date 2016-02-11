from django.conf.urls import url
from django.views.generic import RedirectView
from booking.views import already_cancelled, already_paid, \
    EventListView, EventDetailView, BookingListView, \
    BookingHistoryListView, BookingCreateView, BookingUpdateView, \
    BookingDeleteView, BlockCreateView, BlockDeleteView, \
    BlockListView, TicketBookingListView, \
    TicketedEventListView, TicketCreateView, TicketBookingHistoryListView, \
    TicketBookingView, TicketBookingCancelView, update_booking_cancelled, \
    cancellation_period_past, duplicate_booking, fully_booked, \
    has_active_block, permission_denied, ticket_purchase_expired

urlpatterns = [
    url(r'^bookings/$', BookingListView.as_view(), name='bookings'),
    url(r'^booking-history/$', BookingHistoryListView.as_view(),
        name='booking_history'),
    url(r'^booking/update/(?P<pk>\d+)/$', BookingUpdateView.as_view(),
        name='update_booking'),
    url(r'^booking/update/(?P<pk>\d+)/cancelled/$',
        update_booking_cancelled,
        name='update_booking_cancelled'),
    url(r'^booking/update/(?P<pk>\d+)/paid/$',
        already_paid, name='already_paid'),
    url(r'^booking/cancel/(?P<pk>\d+)/$', BookingDeleteView.as_view(),
        name='delete_booking'),
    url(r'^booking/cancel/(?P<pk>\d+)/already_cancelled/$',
        already_cancelled,
        name='already_cancelled'),
    url(r'^events/(?P<event_slug>[\w-]+)/cancellation-period-past/$',
        cancellation_period_past, name='cancellation_period_past'),
    url(r'^events/(?P<event_slug>[\w-]+)/duplicate/$',
        duplicate_booking, name='duplicate_booking'),
    url(r'^events/(?P<event_slug>[\w-]+)/full/$', fully_booked,
        name='fully_booked'),
    url(r'^events/(?P<event_slug>[\w-]+)/book/$', BookingCreateView.as_view(),
        name='book_event'),
    url(
        r'^events/(?P<slug>[\w-]+)/$', EventDetailView.as_view(),
        {'ev_type': 'event'}, name='event_detail'
    ),
    url(
        r'^events/$', EventListView.as_view(), {'ev_type': 'events'},
        name='events'
    ),
    url(
        r'^classes/(?P<slug>[\w-]+)/$',  EventDetailView.as_view(),
        {'ev_type': 'lesson'}, name='lesson_detail'),
    url(
        r'^classes/$', EventListView.as_view(), {'ev_type': 'lessons'},
        name='lessons'
    ),
    url(
        r'^room-hire/(?P<slug>[\w-]+)/$',  EventDetailView.as_view(),
        {'ev_type': 'room_hire'}, name='room_hire_detail'),
    url(
        r'^room-hire/$', EventListView.as_view(), {'ev_type': 'room_hire'},
        name='room_hires'
    ),
    url(r'^blocks/$', BlockListView.as_view(), name='block_list'),
    url(r'^blocks/new/$', BlockCreateView.as_view(), name='add_block'),
    url(r'^blocks/(?P<pk>\d+)/delete/$', BlockDeleteView.as_view(),
        name='delete_block'),
    url(r'^blocks/existing/$', has_active_block,
        name='has_active_block'),
    url(r'^not-available/$', permission_denied,
        name='permission_denied'),
    url(
        r'^ticketed-events/$', TicketedEventListView.as_view(),
        name='ticketed_events'
    ),
    url(r'^ticketed-events/(?P<event_slug>[\w-]+)/purchase/$',
        TicketCreateView.as_view(),
        name='book_ticketed_event'),
    url(
        r'^ticket-bookings/$', TicketBookingListView.as_view(),
        name='ticket_bookings'
    ),
    url(
        r'^ticket-bookings/(?P<ref>[\w-]+)/$', TicketBookingView.as_view(),
        name='ticket_booking'
    ),
    url(
        r'^ticket-bookings/(?P<pk>\d+)/cancel/$',
        TicketBookingCancelView.as_view(), name='cancel_ticket_booking'
    ),
    url(
        r'^ticket-bookings/(?P<slug>[\w-]+)/expired/$',
        ticket_purchase_expired, name='ticket_purchase_expired'
    ),
    url(r'^ticket-booking-history/$', TicketBookingHistoryListView.as_view(),
        name='ticket_booking_history'),
    url(r'^$', RedirectView.as_view(url='/classes/', permanent=True)),
    ]
