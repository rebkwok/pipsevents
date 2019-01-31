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
                               register_list_view,
                               register_print_day,
                               event_admin_list,
                               timetable_admin_list,
                               toggle_regular_student,
                               toggle_print_disclaimer,
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
                               BookingRegisterAddView
                               )

app_name = 'studioadmin'


urlpatterns = [
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
    path('event-registers-v1/<slug:event_slug>/<str:status_choice>/',
        register_view, name='event_register'),
    path('event-registers/<slug:event_slug>/', register_list_view, name='event_register'),
    path('event-registers/<slug:event_slug>/<str:status_choice>/print/',
        register_view, {'print_view': True}, name='event_register_print'),
    path('event-registers/print-registers-by-date/', register_print_day,
        name='register-day'),
    path('events/new/', EventAdminCreateView.as_view(),
        {'ev_type': 'event'}, name='add_event'),
    path('classes/<slug:slug>/edit/', EventAdminUpdateView.as_view(),
        {'ev_type': 'lesson'}, name='edit_lesson'),
    path('classes/', event_admin_list,
        {'ev_type': 'lessons'}, name='lessons'),
    path('class-registers/', EventRegisterListView.as_view(),
        {'ev_type': 'lessons'}, name='class_register_list'),
    path('class-registers-v1/<slug:event_slug>/<str:status_choice>/',
        register_view, name='class_register'),
    path('class-registers/<slug:event_slug>/', register_list_view, name='class_register'),
    path('class-registers/<slug:event_slug>/<str:status_choice>/print/',
        register_view, {'print_view': True}, name='class_register_print'),
    path('classes/new/', EventAdminCreateView.as_view(),
        {'ev_type': 'lesson'}, name='add_lesson'),
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
        'users/<int:user_id>/toggle_regular_student/',
        toggle_regular_student, name='toggle_regular_student'
    ),
    path(
        'users/<int:user_id>/toggle_print_disclaimer/',
        toggle_print_disclaimer, name='toggle_print_disclaimer'
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
        'activitylog/', ActivityLogListView.as_view(), name='activitylog'
    ),
    path(
        'waitinglists/<int:event_id>/',
        event_waiting_list_view, name='event_waiting_list'
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
        'bookingregisteradd/<int:event_id>/', BookingRegisterAddView.as_view(),
        name='bookingregisteradd'
    ),
    path('jsi18n/', JavaScriptCatalog.as_view(), name='jsi18n'),
    path('', RedirectView.as_view(url='/studioadmin/classes/', permanent=True)),
    ]
