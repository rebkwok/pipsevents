from studioadmin.views.activity_log import ActivityLogListView
from studioadmin.views.blocks import BlockListView
from studioadmin.views.disclaimers import DisclaimerUpdateView, \
    DisclaimerDeleteView, user_disclaimer
from studioadmin.views.email_users import choose_users_to_email, \
    email_users_view
from studioadmin.views.events import cancel_event_view, event_admin_list, \
    EventAdminCreateView, EventAdminUpdateView
from studioadmin.views.misc import ConfirmPaymentView, ConfirmRefundView
from studioadmin.views.register import EventRegisterListView, \
    register_print_day, register_view
from studioadmin.views.ticketed_events import cancel_ticketed_event_view, \
    ConfirmTicketBookingRefundView, print_tickets_list, \
    TicketedEventAdminCreateView, TicketedEventAdminListView, \
    TicketedEventAdminUpdateView, TicketedEventBookingsListView
from studioadmin.views.timetable import timetable_admin_list, \
    TimetableSessionCreateView, TimetableSessionUpdateView, \
    upload_timetable_view
from studioadmin.views.users import user_bookings_view, user_blocks_view, \
    UserListView
from studioadmin.views.vouchers import VoucherCreateView, VoucherListView, \
    VoucherUpdateView
from studioadmin.views.waiting_list import event_waiting_list_view


__all__ = [
    'ActivityLogListView', 'BlockListView', 'cancel_ticketed_event_view',
    'cancel_event_view', 'choose_users_to_email',
    'ConfirmPaymentView', 'ConfirmRefundView', 'DisclaimerDeleteView',
    'DisclaimerUpdateView',
    'email_users_view', 'event_admin_list',
    'EventAdminCreateView', 'EventAdminUpdateView'
    'EventRegisterListView', 'event_waiting_list_view', 'print_tickets_list',
    'register_print_day', 'register_view', 'TicketedEventBookingsListView',
    'TicketedEventAdminUpdateView', 'TicketedEventAdminListView',
    'TicketedEventAdminCreateView', 'ConfirmTicketBookingRefundView',
    'timetable_admin_list', 'TimetableSessionCreateView',
    'TimetableSessionUpdateView', 'upload_timetable_view',
    'user_bookings_view', 'user_blocks_view', 'user_disclaimer',
    'UserListView', 'VoucherCreateView', 'VoucherListView', 'VoucherUpdateView'
]

