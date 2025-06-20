# -*- coding: utf-8 -*-

from studioadmin.views.activity_log import ActivityLogListView
from studioadmin.views.blocks import BlockListView
from studioadmin.views.disclaimers import DisclaimerUpdateView, \
    DisclaimerDeleteView, user_disclaimer, NonRegisteredDisclaimersListView, \
    nonregistered_disclaimer, DisclaimerContentCreateView, DisclaimerContentListView, \
    disclaimer_content_view, DisclaimerContentUpdateView, expire_user_disclaimer
from studioadmin.views.email_users import choose_users_to_email, \
    email_users_view, export_mailing_list
from studioadmin.views.events import cancel_event_view, event_admin_list, \
    EventAdminCreateView, EventAdminUpdateView, open_all_events, clone_event, eventedit, delete_event
from studioadmin.views.misc import ConfirmPaymentView, ConfirmRefundView, \
    test_paypal_view, reactivated_block_status, InvoiceListView, stripe_test, SubscriptionInvoiceListView, landing
from studioadmin.views.register import EventRegisterListView, \
    register_print_day, register_view, booking_register_add_view, \
    ajax_toggle_attended
from studioadmin.views.ticketed_events import cancel_ticketed_event_view, \
    ConfirmTicketBookingRefundView, print_tickets_list, \
    TicketedEventAdminCreateView, TicketedEventAdminListView, \
    TicketedEventAdminUpdateView, TicketedEventBookingsListView
from studioadmin.views.timetable import timetable_admin_list, \
    TimetableSessionCreateView, TimetableSessionUpdateView, \
    upload_timetable_view, clone_timetable_session
from studioadmin.views.users import MailingListView, \
    toggle_subscribed, unsubscribe, \
    user_modal_bookings_view, user_blocks_view, UserListView, \
    BookingEditPastView, BookingEditView, BookingAddView, users_status, toggle_permission, user_memberships_list
from studioadmin.views.vouchers import BlockVoucherCreateView, \
    BlockVoucherListView, BlockVoucherUpdateView, VoucherCreateView, \
    VoucherListView, VoucherUpdateView, BlockVoucherDetailView, \
    EventVoucherDetailView, GiftVoucherListView, MembershipVoucherListView, \
    MembershipVoucherCreateView, membership_voucher_toggle_active, membership_voucher_detail
from studioadmin.views.waiting_list import event_waiting_list_view, email_waiting_list, \
    ticketed_event_waiting_list_view, email_ticketed_event_waiting_list
from studioadmin.views.notifications import all_users_banner_view, new_users_banner_view, popup_notification_view
from studioadmin.views.setup_views import AllowedGroupListView, EventTypeListView
from studioadmin.views.memberships import memberships_list, membership_edit, membership_add, membership_delete, \
    membership_deactivate, membership_users, email_members, email_all_members


__all__ = [
    'ActivityLogListView', 'BlockListView', 'BlockVoucherCreateView',
    'BlockVoucherDetailView',
    'BlockVoucherListView', 'BlockVoucherUpdateView', 'GiftVoucherListView',
    'cancel_ticketed_event_view',
    'cancel_event_view', 'choose_users_to_email',
    'ConfirmPaymentView', 'ConfirmRefundView', 'DisclaimerDeleteView',
    'DisclaimerUpdateView', 'NonRegisteredDisclaimersListView', 'nonregistered_disclaimer',
    'DisclaimerContentCreateView', 'DisclaimerContentListView', 'disclaimer_content_view',
    'DisclaimerContentUpdateView', 'expire_user_disclaimer',
    'email_users_view', 'event_admin_list', 'event_admin_list', 'eventedit',
    'EventAdminCreateView', 'EventAdminUpdateView',
    'EventRegisterListView', 'EventVoucherDetailView',
    'event_waiting_list_view', 'MailingListView',
    'print_tickets_list',
    'register_print_day', 'register_view', 'TicketedEventBookingsListView',
    'TicketedEventAdminUpdateView', 'TicketedEventAdminListView',
    'TicketedEventAdminCreateView', 'ConfirmTicketBookingRefundView',
    'test_paypal_view',
    'timetable_admin_list', 'TimetableSessionCreateView',
    'TimetableSessionUpdateView', 'toggle_subscribed', 'unsubscribe', 'toggle_permission',
    'upload_timetable_view', "clone_timetable_session",
    'user_blocks_view', 'user_disclaimer',
    'UserListView', 'user_modal_bookings_view', 'VoucherCreateView',
    'VoucherListView', 'VoucherUpdateView',
    'BookingEditPastView', 'BookingAddView', 'BookingEditView',
    'export_mailing_list', 'booking_register_add_view',
    'ajax_toggle_attended', 'open_all_events',
    'clone_event', 'users_status', 'email_waiting_list', 'delete_event',
    'all_users_banner_view', 'new_users_banner_view', 'popup_notification_view',
    "InvoiceListView", "stripe_test",
    "ticketed_event_waiting_list_view", "email_ticketed_event_waiting_list",
    "AllowedGroupListView", "EventTypeListView",
    "memberships_list", "membership_edit", "membership_add", "membership_delete",
    "SubscriptionInvoiceListView", "membership_deactivate",
    "reactivated_block_status", "MembershipVoucherListView",
    "MembershipVoucherCreateView", "membership_voucher_toggle_active", "membership_voucher_detail",
    "membership_users", "email_members", "email_all_members", "user_memberships_list",
]

