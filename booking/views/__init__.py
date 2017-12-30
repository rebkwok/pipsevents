from django.shortcuts import render

from booking.views.event_views import EventDetailView, EventListView
from booking.views.booking_views import already_cancelled, already_paid, \
    BookingCreateView, BookingDeleteView, BookingMultiCreateView, \
    BookingHistoryListView, BookingListView, BookingUpdateView, \
    disclaimer_required, \
    duplicate_booking, update_booking_cancelled, fully_booked, \
    has_active_block, cancellation_period_past
from booking.views.block_views import BlockCreateView, BlockDeleteView, \
    BlockListView
from booking.views.ticketed_views import TicketBookingListView, \
    TicketedEventListView, TicketCreateView, TicketBookingHistoryListView, \
    TicketBookingView, TicketBookingCancelView, ticket_purchase_expired


__all__ = [
    'already_cancelled', 'already_paid',
    'EventListView', 'EventDetailView', 'BookingListView',
    'BookingHistoryListView', 'BookingCreateView', 'BookingUpdateView',
    'BookingMultiCreateView',
    'BookingDeleteView', 'disclaimer_required', 'duplicate_booking',
    'update_booking_cancelled',
    'fully_booked', 'has_active_block', 'cancellation_period_past',
    'BlockCreateView', 'BlockDeleteView', 'BlockListView', 'permission_denied',
    'TicketedEventListView', 'TicketCreateView', 'TicketBookingListView',
    'TicketBookingHistoryListView', 'TicketBookingView',
    'TicketBookingCancelView', 'ticket_purchase_expired'
]


def permission_denied(request):
    return render(request, 'booking/permission_denied.html')