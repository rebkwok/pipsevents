from django.conf.urls import url
from django.views.generic import RedirectView
from studioadmin.views import (ConfirmRefundView,
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
                               register_print_day,
                               event_admin_list,
                               timetable_admin_list,
                               toggle_regular_student,
                               toggle_print_disclaimer,
                               toggle_subscribed,
                               upload_timetable_view,
                               choose_users_to_email,
                               user_bookings_view,
                               user_blocks_view,
                               email_users_view,
                               event_waiting_list_view,
                               cancel_ticketed_event_view,
                               print_tickets_list,
                               test_paypal_view,
                               user_disclaimer,
                               VoucherCreateView,
                               VoucherListView,
                               VoucherUpdateView
                               )


urlpatterns = [
    url(r'^confirm-payment/(?P<pk>\d+)/$', ConfirmPaymentView.as_view(),
        name='confirm-payment'),
    url(r'^confirm-refunded/(?P<pk>\d+)/$', ConfirmRefundView.as_view(),
        name='confirm-refund'),
    url(r'^events/(?P<slug>[\w-]+)/edit$', EventAdminUpdateView.as_view(),
        {'ev_type': 'event'}, name='edit_event'),
    url(r'^events/$', event_admin_list,
        {'ev_type': 'events'}, name='events'),
    url(r'^events/(?P<slug>[\w-]+)/cancel', cancel_event_view,
        name='cancel_event'),
    url(r'^event-registers/$', EventRegisterListView.as_view(),
        {'ev_type': 'events'}, name='event_register_list'),
    url(r'^event-registers/(?P<event_slug>[\w-]+)/(?P<status_choice>[\w-]+)$',
        register_view, name='event_register'),
    url(r'^event-registers/(?P<event_slug>[\w-]+)/(?P<status_choice>[\w-]+)/print/$',
        register_view, {'print_view': True}, name='event_register_print'),
    url(r'^event-registers/print-registers-by-date/$', register_print_day,
        name='register-day'),
    url(r'^events/new/$', EventAdminCreateView.as_view(),
        {'ev_type': 'event'}, name='add_event'),
    url(r'^classes/(?P<slug>[\w-]+)/edit$', EventAdminUpdateView.as_view(),
        {'ev_type': 'lesson'}, name='edit_lesson'),
    url(r'^classes/$', event_admin_list,
        {'ev_type': 'lessons'}, name='lessons'),
    url(r'^class-registers/$', EventRegisterListView.as_view(),
        {'ev_type': 'lessons'}, name='class_register_list'),
    url(r'^class-registers/(?P<event_slug>[\w-]+)/(?P<status_choice>[\w-]+)$',
        register_view, name='class_register'),
    url(r'^class-registers/(?P<event_slug>[\w-]+)/(?P<status_choice>[\w-]+)/print/$',
        register_view, {'print_view': True}, name='class_register_print'),
    url(r'^classes/new/$', EventAdminCreateView.as_view(),
        {'ev_type': 'lesson'}, name='add_lesson'),
    url(r'^timetable/$', timetable_admin_list, name='timetable'),
    url(
        r'^timetable/session/(?P<pk>\d+)/edit$',
        TimetableSessionUpdateView.as_view(), name='edit_session'
    ),
    url(
        r'^timetable/session/new$',
        TimetableSessionCreateView.as_view(), name='add_session'
    ),
    url(r'^timetable/upload/$', upload_timetable_view,
        name='upload_timetable'),
    url(r'^users/$', UserListView.as_view(), name="users"),
    url(r'^blocks/$', BlockListView.as_view(), name="blocks"),
    url(r'^users/email/$', choose_users_to_email,
        name="choose_email_users"),
    url(r'^users/email/emailform/$', email_users_view,
        name="email_users_view"),
    url(r'^users/email/mailing-list-email/$', email_users_view,
        {'mailing_list': True}, name="mailing_list_email"),
    url(r'^users/mailing-list/$', MailingListView.as_view(), name='mailing_list'),
    url(
        r'^users/(?P<user_id>\d+)/bookings/(?P<booking_status>[\w-]+)$',
        user_bookings_view, name='user_bookings_list'
    ),
    url(
        r'^users/(?P<user_id>\d+)/blocks/$',
        user_blocks_view, name='user_blocks_list'
    ),
    url(
        r'^users/(?P<user_id>\d+)/toggle_regular_student/$',
        toggle_regular_student, name='toggle_regular_student'
    ),
    url(
        r'^users/(?P<user_id>\d+)/toggle_print_disclaimer/$',
        toggle_print_disclaimer, name='toggle_print_disclaimer'
    ),
    url(
        r'^users/(?P<user_id>\d+)/toggle_subscribed/$',
        toggle_subscribed, name='toggle_subscribed'
    ),
    url(r'^users/(?P<encoded_user_id>[\w-]+)/disclaimer/$',
        user_disclaimer,
        name='user_disclaimer'),
    url(r'^users/(?P<encoded_user_id>[\w-]+)/disclaimer/update/$',
        DisclaimerUpdateView.as_view(),
        name='update_user_disclaimer'),
    url(r'^users/(?P<encoded_user_id>[\w-]+)/disclaimer/delete/$',
        DisclaimerDeleteView.as_view(),
        name='delete_user_disclaimer'),
    url(
        r'activitylog/$', ActivityLogListView.as_view(), name='activitylog'
    ),
    url(
        r'^waitinglists/(?P<event_id>\d+)$',
        event_waiting_list_view, name='event_waiting_list'
    ),
    url(r'^ticketed-events/$', TicketedEventAdminListView.as_view(),
        name='ticketed_events'),
    url(r'^ticketed-events/new/$', TicketedEventAdminCreateView.as_view(),
        name='add_ticketed_event'),
    url(r'^ticketed-events/(?P<slug>[\w-]+)/edit$',
        TicketedEventAdminUpdateView.as_view(),
        name='edit_ticketed_event'),
    url(r'^ticketed-events/(?P<slug>[\w-]+)/ticket-bookings$',
        TicketedEventBookingsListView.as_view(),
        name='ticketed_event_bookings'),
    url(r'^ticketed-events/(?P<slug>[\w-]+)/cancel',
        cancel_ticketed_event_view,
        name='cancel_ticketed_event'),
    url(r'^confirm-ticket-booking-refunded/(?P<pk>\d+)/$',
        ConfirmTicketBookingRefundView.as_view(),
        name='confirm_ticket_booking_refund'),
    url(r'^ticketed-events/print-tickets-list/$', print_tickets_list,
        name='print_tickets_list'),
    url(r'^vouchers/$', VoucherListView.as_view(), name='vouchers'),
    url(r'^vouchers/new/$', VoucherCreateView.as_view(), name='add_voucher'),
    url(r'^vouchers/(?P<pk>\d+)/edit/$', VoucherUpdateView.as_view(), name='edit_voucher'),
    url(r'^test-paypal-email/$', test_paypal_view, name='test_paypal_email'),
    url(r'^$', RedirectView.as_view(url='/studioadmin/classes/', permanent=True)),
    ]
