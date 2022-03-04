from django.shortcuts import render

from booking.views.event_views import EventDetailView, EventListView, OnlineTutorialListView, OnlineTutorialDetailView
from booking.views.booking_views import ajax_create_booking, \
    already_cancelled, already_paid, BookingDeleteView, \
    BookingHistoryListView, BookingListView, BookingUpdateView, \
    disclaimer_required, \
    duplicate_booking, update_booking_cancelled, fully_booked, \
    has_active_block, cancellation_period_past, update_shopping_basket_count, \
    update_booking_count, toggle_waiting_list, booking_details, PurchasedTutorialsListView
from booking.views.block_views import BlockCreateView, BlockDeleteView, \
    BlockListView, blocks_modal
from booking.views.gift_vouchers import GiftVoucherPurchaseView, gift_voucher_details, gift_voucher_delete
from booking.views.shopping_basket_views import shopping_basket, \
    update_block_bookings, submit_zero_booking_payment, submit_zero_block_payment, \
    ajax_shopping_basket_bookings_total, ajax_shopping_basket_blocks_total
from booking.views.ticketed_views import TicketBookingListView, \
    TicketedEventListView, TicketCreateView, TicketBookingHistoryListView, \
    TicketBookingView, TicketBookingCancelView, ticket_purchase_expired


__all__ = [
    'ajax_create_booking', 'already_cancelled', 'already_paid',
    'EventListView', 'EventDetailView', 'BookingListView',
    'BookingHistoryListView', 'BookingUpdateView',
    'BookingDeleteView',
    'disclaimer_required', 'duplicate_booking',
    'GiftVoucherPurchaseView', 'gift_voucher_details', 'gift_voucher_delete',
    'update_booking_cancelled', 'shopping_basket', 'update_block_bookings',
    'submit_zero_booking_payment', 'submit_zero_block_payment',
    'fully_booked', 'has_active_block', 'cancellation_period_past',
    'BlockCreateView', 'BlockDeleteView', 'BlockListView', 'permission_denied',
    'TicketedEventListView', 'TicketCreateView', 'TicketBookingListView',
    'TicketBookingHistoryListView', 'TicketBookingView',
    'TicketBookingCancelView', 'ticket_purchase_expired', 'update_shopping_basket_count',
    'update_booking_count', 'toggle_waiting_list', 'booking_details',
    'ajax_shopping_basket_bookings_total', 'ajax_shopping_basket_blocks_total',
    'blocks_modal',
    "OnlineTutorialListView", "PurchasedTutorialsListView", "OnlineTutorialDetailView",
]


def permission_denied(request):
    return render(request, 'booking/permission_denied.html')
