from suit.apps import DjangoSuitConfig
from suit.menu import ParentItem, ChildItem


class SuitConfig(DjangoSuitConfig):
    layout = 'horizontal'

    menu = (
        ParentItem('Events and Classes', children=[
            ChildItem(model='booking.event'),
            ChildItem(model='booking.eventtype'),
        ], icon='fa fa-star'),
        ParentItem('Bookings', children=[
            ChildItem(model='booking.booking'),
            ChildItem(model='booking.block'),
            ChildItem(model='booking.blocktype'),
            ChildItem(model='booking.waitinglistuser'),
        ], icon='fa fa-heart'),
        ParentItem('Ticket Bookings', children=[
            ChildItem(model='booking.ticketedevent'),
            ChildItem(model='booking.ticketbooking'),
            ChildItem(model='booking.ticket'),
        ], icon='fa fa-star'),
        ParentItem('Accounts', children=[
            ChildItem(model='auth.user'),
            ChildItem(model='account.emailaddress'),
            ChildItem(model='accounts.cookiepolicy'),
            ChildItem(model='accounts.dataprivacypolicy'),
            ChildItem(model='accounts.signeddataprivacy'),
            ChildItem(model='accounts.onlinedisclaimer'),
            ChildItem(model='accounts.printdisclaimer'),
            ChildItem(model='accounts.nonregistereddisclaimer'),
        ], icon='fa fa-users'),
        ParentItem('Payments', children=[
            ChildItem(model='payments.paypalbookingtransaction'),
            ChildItem(model='payments.paypalblocktransaction'),
            ChildItem(model='payments.paypalticketbookingtransaction'),
            ChildItem(model='ipn.paypalipn'),
        ]),
        ParentItem('Voucher', children=[
            ChildItem(model='booking.eventvoucher'),
            ChildItem(model='booking.blockvoucher'),
            ChildItem(model='booking.usedeventvoucher'),
            ChildItem(model='booking.usedblockvoucher'),
        ]),
        ParentItem('Activity Log', children=[
            ChildItem("Activtylog", 'activitylog.activitylog'),
        ]),
        ParentItem('Links', children=[
            ChildItem('Go to main booking site', url='/'),
        ], align_right=True, icon='fa fa-cog'),
    )

    def ready(self):
        super(SuitConfig, self).ready()
