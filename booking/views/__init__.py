from django.shortcuts import render

from booking.views.event_views import EventDetailView, EventListView
from booking.views.booking_views import BookingCreateView, BookingDeleteView, \
    BookingHistoryListView, BookingListView, BookingUpdateView, \
    duplicate_booking, update_booking_cancelled, fully_booked, \
    has_active_block, cancellation_period_past
from booking.views.block_views import BlockCreateView, BlockListView


__all__ = [
    'EventListView', 'EventDetailView', 'BookingListView',
    'BookingHistoryListView', 'BookingCreateView', 'BookingUpdateView',
    'BookingDeleteView', 'duplicate_booking', 'update_booking_cancelled',
    'fully_booked', 'has_active_block', 'cancellation_period_past',
    'BlockCreateView', 'BlockListView', 'permission_denied'
]


def permission_denied(request):
    return render(request, 'booking/permission_denied.html')