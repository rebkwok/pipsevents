from django.urls import path, re_path
from django.views.generic import RedirectView
from django.views.i18n import JavaScriptCatalog
from studioadmin.views import (BookingEditView,
                               BookingEditPastView,
                               ConfirmRefundView,
                               ConfirmTicketBookingRefundView,
                               ConfirmPaymentView,
                               DisclaimerDeleteView,
                               DisclaimerUpdateView,
                               DisclaimerContentCreateView,
                               DisclaimerContentListView,
                               disclaimer_content_view,
                               DisclaimerContentUpdateView,
                               expire_user_disclaimer,
                               NonRegisteredDisclaimersListView,
                               nonregistered_disclaimer,
                               EventAdminUpdateView,
                               EventAdminCreateView,
                               EventRegisterListView,
                               MailingListView,
                               TimetableSessionUpdateView,
                               TimetableSessionCreateView,
                               UserListView,
                               BlockListView,
                               ActivityLogListView,
                               TicketedEventAdminListView,
                               TicketedEventAdminCreateView,
                               TicketedEventAdminUpdateView,
                               TicketedEventBookingsListView,
                               cancel_event_view,
                               register_view,
                               register_print_day,
                               event_admin_list,
                               timetable_admin_list,
                               toggle_subscribed,
                               unsubscribe,
                               upload_timetable_view,
                               choose_users_to_email,
                               user_bookings_view_old,
                               user_modal_bookings_view,
                               user_blocks_view,
                               email_users_view,
                               event_waiting_list_view,
                               cancel_ticketed_event_view,
                               print_tickets_list,
                               test_paypal_view,
                               user_disclaimer,
                               VoucherCreateView,
                               VoucherListView,
                               VoucherUpdateView,
                               BlockVoucherListView,
                               BlockVoucherUpdateView,
                               BlockVoucherCreateView,
                               BlockVoucherDetailView,
                               EventVoucherDetailView,
                               export_mailing_list,
                               BookingAddView,
                               booking_register_add_view,
                               ajax_toggle_attended,
                               ajax_toggle_paid,
                               ajax_assign_block,
                               GiftVoucherListView,
                               open_all_events,
                               clone_event,
                               reactivated_block_status,
                               users_status,
                               email_waiting_list,
                               all_users_banner_view, 
                               new_users_banner_view, 
                               popup_notification_view,
                               InvoiceListView,
                               stripe_test,
                               ticketed_event_waiting_list_view,
                               email_ticketed_event_waiting_list,
                               toggle_permission,
                               AllowedGroupListView,
                               EventTypeListView,
                               )

app_name = 'studioadmin'


urlpatterns = [
    path('reactivated-credit-status', reactivated_block_status, name="reactivated_block_status"),
    path('confirm-payment/<int:pk>/', ConfirmPaymentView.as_view(),
        name='confirm-payment'),
    path('confirm-refunded/<int:pk>/', ConfirmRefundView.as_view(),
        name='confirm-refund'),
    path('events/<slug:slug>/edit', EventAdminUpdateView.as_view(),
        {'ev_type': 'event'}, name='edit_event'),
    path('events/', event_admin_list,
        {'ev_type': 'events'}, name='events'),
    path('events/<slug:slug>/cancel', cancel_event_view,
        name='cancel_event'),
    path('event-registers/', EventRegisterListView.as_view(),
        {'ev_type': 'events'}, name='event_register_list'),
    path('event-registers/print-registers-by-date/', register_print_day,
        name='register-day'),
    path('event-registers/<slug:event_slug>/', register_view, name='event_register'),
    path('events/new/', EventAdminCreateView.as_view(),
        {'ev_type': 'event'}, name='add_event'),
    path('classes/<slug:slug>/edit/', EventAdminUpdateView.as_view(),
        {'ev_type': 'lesson'}, name='edit_lesson'),
    path('classes/', event_admin_list,
        {'ev_type': 'lessons'}, name='lessons'),
    path('class-registers/', EventRegisterListView.as_view(),
        {'ev_type': 'lessons'}, name='class_register_list'),
    path('classes/new/', EventAdminCreateView.as_view(),
        {'ev_type': 'lesson'}, name='add_lesson'),
    path('online-tutorials/<slug:slug>/edit/', EventAdminUpdateView.as_view(),
         {'ev_type': 'online_tutorial'}, name='edit_online_tutorial'),
    path('online-tutorials/', event_admin_list,
         {'ev_type': 'online_tutorials'}, name='online_tutorials'),
    path('online-tutorial-registers/', EventRegisterListView.as_view(),
         {'ev_type': 'online_tutorials'}, name='online_tutorials_register_list'),
    path('online-tutorials/new/', EventAdminCreateView.as_view(),
         {'ev_type': 'online_tutorial'}, name='add_online_tutorial'),
    path('event/clone/<slug:slug>/', clone_event, name='clone_event'),
    path('events/<str:event_type>/open/', open_all_events, name='open_all_events'),
    path('timetable', timetable_admin_list, name='timetable'),
    path('timetable/session/<int:pk>/edit/',
        TimetableSessionUpdateView.as_view(), name='edit_session'
    ),
    path(
        'timetable/session/new/',
        TimetableSessionCreateView.as_view(), name='add_session'
    ),
    path('timetable/upload/', upload_timetable_view,
        name='upload_timetable'),
    path('users/attendance/', users_status, name="users_status"),
    path('users/', UserListView.as_view(), name="users"),
    path('blocks/', BlockListView.as_view(), name="blocks"),
    path('users/email/', choose_users_to_email,
        name="choose_email_users"),
    path('users/email/emailform/', email_users_view,
        name="email_users_view"),
    path('users/email/mailing-list-email/', email_users_view,
        {'mailing_list': True}, name="mailing_list_email"),
    path(
        'users/mailing-list/', MailingListView.as_view(),
         name='mailing_list'
    ),
    path('users/mailing-list/export/', export_mailing_list,
        name='export_mailing_list'
    ),
    path('users/<int:user_id>/mailing-list/unsubscribe/',
        unsubscribe, name='unsubscribe'
    ),
    path('users/<int:user_id>/bookings/old/',
        user_bookings_view_old, name='user_bookings_list'
    ),
    path(
        'users/<int:user_id>/bookings/',
        user_modal_bookings_view, {'past': False},
        name='user_upcoming_bookings_list'
    ),
    path(
        'users/<int:user_id>/bookings/past/',
        user_modal_bookings_view, {'past': True},
        name='user_past_bookings_list'
    ),
    path('users/<int:user_id>/blocks/',
        user_blocks_view, name='user_blocks_list'
    ),
    path(
        'users/<int:user_id>/toggle_permission/<int:event_type_id>/',
        toggle_permission, name='toggle_permission'
    ),
    path(
        'users/<int:user_id>/toggle_subscribed/',
        toggle_subscribed, name='toggle_subscribed'
    ),
    path(
        'users/<str:encoded_user_id>/disclaimer/',
        user_disclaimer, name='user_disclaimer'
    ),
    path(
        'users/<str:encoded_user_id>/disclaimer/update/',
        DisclaimerUpdateView.as_view(),
        name='update_user_disclaimer'),
    path(
        'users/<str:encoded_user_id>/disclaimer/delete/',
        DisclaimerDeleteView.as_view(), name='delete_user_disclaimer'
    ),
    path(
        'users/<str:encoded_user_id>/disclaimer/<int:disclaimer_id>/expire/',
        expire_user_disclaimer, name='expire_user_disclaimer'
    ),
    path(
        'activitylog/', ActivityLogListView.as_view(), name='activitylog'
    ),
    path(
        'waitinglists/<int:event_id>/',
        event_waiting_list_view, name='event_waiting_list'
    ),
    path(
        'waitinglists/<int:event_id>/email/',
        email_waiting_list, name='email_waiting_list'
    ),
    path(
        'ticketed-events/', TicketedEventAdminListView.as_view(),
        name='ticketed_events'
    ),
    path(
        'ticketed-events/new/', TicketedEventAdminCreateView.as_view(),
        name='add_ticketed_event'
    ),
    path(
        'ticketed-events/<slug:slug>/edit/',
        TicketedEventAdminUpdateView.as_view(), name='edit_ticketed_event'
    ),
    path(
        'ticketed-events/<slug:slug>/ticket-bookings/',
        TicketedEventBookingsListView.as_view(),
        name='ticketed_event_bookings'
    ),
    path(
        'ticketed-events/<slug:slug>/cancel/',
        cancel_ticketed_event_view, name='cancel_ticketed_event'
    ),
    path(
        'ticketed-events/<slug:ticketed_event_slug>/waiting-list/',
        ticketed_event_waiting_list_view, name='ticketed_event_waiting_list_view'
    ),
    path(
        'ticketed-events/waitinglists/<int:ticketed_event_id>/email/',
        email_ticketed_event_waiting_list, name='email_ticketed_event_waiting_list'
    ),
    path(
        'confirm-ticket-booking-refunded/<int:pk>/',
        ConfirmTicketBookingRefundView.as_view(),
        name='confirm_ticket_booking_refund'
    ),
    path(
        'ticketed-events/print-tickets-list/', print_tickets_list,
        name='print_tickets_list'
    ),
    path('vouchers/', VoucherListView.as_view(), name='vouchers'),
    path('vouchers/new/', VoucherCreateView.as_view(), name='add_voucher'),
    path(
        'vouchers/<int:pk>/edit/', VoucherUpdateView.as_view(),
        name='edit_voucher'
    ),
    path(
        'block-vouchers/', BlockVoucherListView.as_view(), name='block_vouchers'
    ),
    path(
        'block-vouchers/new/', BlockVoucherCreateView.as_view(),
        name='add_block_voucher'
    ),
    path(
        'block-vouchers/<int:pk>/edit/', BlockVoucherUpdateView.as_view(),
        name='edit_block_voucher'
    ),
        path(
        'gift-vouchers/', GiftVoucherListView.as_view(), name='gift_vouchers'
    ),
    path('test-paypal-email/', test_paypal_view, name='test_paypal_email'),
    path(
        'voucher/<int:pk>/uses/', EventVoucherDetailView.as_view(),
        name='voucher_uses'
    ),
    path(
        'block-voucher/<int:pk>/uses/', BlockVoucherDetailView.as_view(),
        name='block_voucher_uses'
    ),
    path(
        'bookingeditpast/<int:pk>/', BookingEditPastView.as_view(),
        name='bookingeditpast'
    ),
    path(
        'bookingedit/<int:pk>/', BookingEditView.as_view(),
        name='bookingedit'
    ),
    path(
        'bookingadd/<int:user_id>/', BookingAddView.as_view(),
        name='bookingadd'
    ),
    path(
        'bookingregisteradd/<int:event_id>/', booking_register_add_view,
        name='bookingregisteradd'
    ),
    path(
        'register/<int:booking_id>/toggle_attended/', ajax_toggle_attended,
        name='toggle_attended'
    ),
    path(
        'register/<int:booking_id>/toggle_paid/', ajax_toggle_paid,
        name='toggle_paid'
    ),
    path(
        'register/<int:booking_id>/assign_block/', ajax_assign_block,
        name='assign_block'
    ),
    path(
        'event-disclaimers/', NonRegisteredDisclaimersListView.as_view(),
        name='event_disclaimers'
    ),
    path(
        'event-disclaimer/<uuid:user_uuid>/', nonregistered_disclaimer,
        name='event_disclaimer'
    ),
    path(
        'disclaimer-version/list/', DisclaimerContentListView.as_view(),
        name='disclaimer_content_list'
    ),
    path(
        'disclaimer-version/new/', DisclaimerContentCreateView.as_view(),
        name='disclaimer_content_new'
    ),
    re_path(
        r'^disclaimer-version/(?P<version>\d+\.\d+)/$',
        disclaimer_content_view, name='disclaimer_content_view'
    ),
    re_path(
        r'^disclaimer-version/edit/(?P<version>\d+\.\d+)/$',
        DisclaimerContentUpdateView.as_view(), name='disclaimer_content_edit'
    ),
    path(
        'notifications/all-users-banner/', all_users_banner_view,
        name='all_users_banner'
    ),
    path(
        'notifications/new-users-banner/', new_users_banner_view,
        name='new_users_banner'
    ),
    path(
        'notifications/pop-up-notification/', popup_notification_view,
        name='popup_notification'
    ),
    path("payment/transactions/", InvoiceListView.as_view(), name="invoices"),
    path("payment/stripe-test/", stripe_test, name="stripe_test"),
    path("setup/event-types/", EventTypeListView.as_view(), name="setup_event_types"),
    path("setup/allowed_groups/", AllowedGroupListView.as_view(), name="setup_allowed_groups"),
    path('jsi18n/', JavaScriptCatalog.as_view(), name='jsi18n'),
    path('', RedirectView.as_view(url='/studioadmin/class-registers/', permanent=True)),
    ]
