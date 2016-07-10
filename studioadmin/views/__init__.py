# -*- coding: utf-8 -*-

from studioadmin.views.activity_log import ActivityLogListView
from studioadmin.views.blocks import BlockListView
from studioadmin.views.disclaimers import DisclaimerUpdateView, \
    DisclaimerDeleteView, user_disclaimer
from studioadmin.views.email_users import choose_users_to_email, \
    email_users_view
from studioadmin.views.events import cancel_event_view, event_admin_list, \
    EventAdminCreateView, EventAdminUpdateView
from studioadmin.views.misc import ConfirmPaymentView, ConfirmRefundView, \
    test_paypal_view
from studioadmin.views.register import EventRegisterListView, \
    register_print_day, register_view
from studioadmin.views.ticketed_events import cancel_ticketed_event_view, \
    ConfirmTicketBookingRefundView, print_tickets_list, \
    TicketedEventAdminCreateView, TicketedEventAdminListView, \
    TicketedEventAdminUpdateView, TicketedEventBookingsListView
from studioadmin.views.timetable import timetable_admin_list, \
    TimetableSessionCreateView, TimetableSessionUpdateView, \
    upload_timetable_view
from studioadmin.views.users import MailingListView, toggle_print_disclaimer, \
    toggle_regular_student, toggle_subscribed, unsubscribe, \
    user_bookings_view, user_blocks_view, UserListView
from studioadmin.views.vouchers import BlockVoucherCreateView, \
    BlockVoucherListView, BlockVoucherUpdateView, VoucherCreateView, \
    VoucherListView, VoucherUpdateView, BlockVoucherDetailView, \
    EventVoucherDetailView
from studioadmin.views.waiting_list import event_waiting_list_view


__all__ = [
    'ActivityLogListView', 'BlockListView', 'BlockVoucherCreateView',
    'BlockVoucherDetailView',
    'BlockVoucherListView', 'BlockVoucherUpdateView',
    'cancel_ticketed_event_view',
    'cancel_event_view', 'choose_users_to_email',
    'ConfirmPaymentView', 'ConfirmRefundView', 'DisclaimerDeleteView',
    'DisclaimerUpdateView',
    'email_users_view', 'event_admin_list',
    'EventAdminCreateView', 'EventAdminUpdateView'
    'EventRegisterListView', 'EventVoucherDetailView',
    'event_waiting_list_view', 'MailingListView',
    'print_tickets_list',
    'register_print_day', 'register_view', 'TicketedEventBookingsListView',
    'TicketedEventAdminUpdateView', 'TicketedEventAdminListView',
    'TicketedEventAdminCreateView', 'ConfirmTicketBookingRefundView',
    'test_paypal_view',
    'timetable_admin_list', 'TimetableSessionCreateView',
    'TimetableSessionUpdateView', 'toggle_print_disclaimer',
    'toggle_regular_student', 'toggle_subscribed', 'unsubscribe',
    'upload_timetable_view',
    'user_bookings_view', 'user_blocks_view', 'user_disclaimer',
    'UserListView', 'VoucherCreateView', 'VoucherListView', 'VoucherUpdateView'
]

