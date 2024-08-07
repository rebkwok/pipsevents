from django.urls import path
from django.views.generic import RedirectView
from booking.views import ajax_create_booking, blocks_modal, \
    already_cancelled, already_paid, \
    GiftVoucherPurchaseView, gift_voucher_details, gift_voucher_delete, \
    disclaimer_required,  \
    EventListView, EventDetailView, BookingListView, \
    BookingHistoryListView, BookingUpdateView, \
    BookingDeleteView, BlockCreateView, BlockDeleteView, \
    BlockListView, TicketBookingListView, \
    TicketedEventListView, TicketCreateView, TicketBookingHistoryListView, \
    TicketBookingView, TicketBookingCancelView, update_booking_cancelled, \
    cancellation_period_past, duplicate_booking, fully_booked, \
    has_active_block, permission_denied, ticket_purchase_expired, \
    shopping_basket, update_block_bookings, submit_zero_block_payment, \
    submit_zero_booking_payment, update_shopping_basket_count, \
    toggle_waiting_list, \
    OnlineTutorialListView, PurchasedTutorialsListView, OnlineTutorialDetailView, \
    check_total, toggle_ticketed_event_waiting_list, payment_plans
app_name = 'booking'


urlpatterns = [
    path('bookings/', BookingListView.as_view(), name='bookings'),
    path(
        'booking-history/', BookingHistoryListView.as_view(),
        name='booking_history'
    ),
    path('online-tutorials/purchased/', PurchasedTutorialsListView.as_view(), name='purchased_tutorials'),
    path('booking/update/<int:pk>/', BookingUpdateView.as_view(),
        name='update_booking'),
    path('booking/update/<int:pk>/cancelled/',
        update_booking_cancelled,
        name='update_booking_cancelled'),
    path('booking/update/<int:pk>/paid/',
        already_paid, name='already_paid'),
    path('booking/update-block-bookings/',
        update_block_bookings, name='update_block_bookings'),
    path('booking/cancel/<int:pk>/', BookingDeleteView.as_view(),
        name='delete_booking'),
    path('booking/cancel/<int:pk>/already_cancelled/',
        already_cancelled,
        name='already_cancelled'),
    path('booking/ajax-create/<int:event_id>/',
        ajax_create_booking,
        name='ajax_create_booking'),
    path('events/<slug:event_slug>/cancellation-period-past/',
        cancellation_period_past, name='cancellation_period_past'),
    path('events/<slug:event_slug>/duplicate/',
        duplicate_booking, name='duplicate_booking'),
    path('events/<slug:event_slug>/full/', fully_booked,
        name='fully_booked'),
    path(
        'events/<slug:slug>/', EventDetailView.as_view(),
        {'ev_type': 'event'}, name='event_detail'
    ),
    path(
        'events/', EventListView.as_view(), {'ev_type': 'events'},
        name='events'
    ),
    path(
        'classes/<slug:slug>/',  EventDetailView.as_view(),
        {'ev_type': 'lesson'}, name='lesson_detail'),
    path(
        'classes/', EventListView.as_view(), {'ev_type': 'lessons'},
        name='lessons'
    ),
    path(
        'online-tutorials/<slug:slug>/',  OnlineTutorialDetailView.as_view(), name='tutorial_detail'),
    path(
        'online-tutorials/', OnlineTutorialListView.as_view(), {'ev_type': 'online_tutorials'},
        name='online_tutorials'
    ),
    path(
        'room-hire/<slug:slug>/',  EventDetailView.as_view(),
        {'ev_type': 'room_hire'}, name='room_hire_detail'),
    path(
        'room-hire/', EventListView.as_view(), {'ev_type': 'room_hires'},
        name='room_hires'
    ),
    path('blocks/', BlockListView.as_view(), name='block_list'),
    path('blocks/new/', BlockCreateView.as_view(), name='add_block'),
    path('blocks/<int:pk>/delete/', BlockDeleteView.as_view(),
        name='delete_block'),
    path('blocks/existing/', has_active_block,
        name='has_active_block'),
    path('not-available/', permission_denied,
        name='permission_denied'),
    path(
        'ticketed-events/', TicketedEventListView.as_view(),
        name='ticketed_events'
    ),
    path('ticketed-events/<slug:event_slug>/purchase/',
        TicketCreateView.as_view(),
        name='book_ticketed_event'),
    path(
        'ticketed-events/toggle-waiting-list/<int:event_id>/',
        toggle_ticketed_event_waiting_list, name='toggle_ticketed_event_waiting_list'
    ),
    path(
        'ticket-bookings/', TicketBookingListView.as_view(),
        name='ticket_bookings'
    ),
    path(
        'ticket-bookings/<str:ref>/', TicketBookingView.as_view(),
        name='ticket_booking'
    ),
    path(
        'ticket-bookings/<int:pk>/cancel/',
        TicketBookingCancelView.as_view(), name='cancel_ticket_booking'
    ),
    path(
        'ticket-bookings/<slug:slug>/expired/',
        ticket_purchase_expired, name='ticket_purchase_expired'
    ),
    path('ticket-booking-history/', TicketBookingHistoryListView.as_view(),
        name='ticket_booking_history'),
    path(
        'disclaimer-required/', disclaimer_required,
        name='disclaimer_required'
    ),
    path(
        'bookings/shopping-basket/', shopping_basket,
        name='shopping_basket'
    ),
    path(
        'bookings/shopping-basket/submit-block/', submit_zero_block_payment,
        name='submit_zero_block_payment'
    ),
    path(
        'bookings/shopping-basket/submit-booking/', submit_zero_booking_payment,
        name='submit_zero_booking_payment'
    ),
    path(
        'bookings/ajax-update-shopping-basket/',
        update_shopping_basket_count, name='update_shopping_basket_count'
    ),
    path(
        'bookings/ajax-toggle-waiting-list/<int:event_id>/',
        toggle_waiting_list, name='toggle_waiting_list'
    ),
    path('check-total/', check_total, name="check_total"),
    path(
        'blocks_modal/',
        blocks_modal, name='blocks_modal'
    ),
    path('payment-plans/', payment_plans, name='payment_plans'),
    path('gift-vouchers/', GiftVoucherPurchaseView.as_view(), name='buy_gift_voucher'),
    path('gift-voucher/<voucher_code>/', gift_voucher_details, name='gift_voucher_details'),
    path('gift-voucher/<voucher_code>/update/', GiftVoucherPurchaseView.as_view(), name='gift_voucher_update'),
    path('gift-voucher/<voucher_code>/delete/', gift_voucher_delete, name='gift_voucher_delete'),
    path('', RedirectView.as_view(url='/classes/', permanent=True)),
    ]
