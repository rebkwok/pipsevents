from django.contrib import admin
from django.contrib.auth.models import User
from django.db.models import Q

from paypal.standard.ipn.models import PayPalIPN
from paypal.standard.ipn.admin import PayPalIPNAdmin

from payments.models import PaypalBookingTransaction, PaypalBlockTransaction, \
    PaypalTicketBookingTransaction


class PaypalBookingUserFilter(admin.SimpleListFilter):

    title = 'User'
    parameter_name = 'user'

    def lookups(self, request, model_admin):
        qs = User.objects.all().order_by('first_name')
        return [
            (
                user.id,
                "{} {} ({})".format(
                    user.first_name, user.last_name, user.username
                )
             ) for user in qs
            ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(booking__user__id=self.value())
        return queryset


class PaypalCheckFilter(admin.SimpleListFilter):

    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = 'Show unpaid with transaction ID'

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'unpaid_with_txn'

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        return (
            ('all', 'all'),
            ('open', 'open only'),
            ('cancelled', 'cancelled and no-show'),
            ('autocancelled', 'autocancelled only'),
        )


class PaypalBookingCheckFilter(PaypalCheckFilter):

    def queryset(self, request, queryset):
        if self.value() == 'all':
            return queryset.filter(
                transaction_id__isnull=False, booking__paid=False
            )
        elif self.value() == 'open':
            return queryset.filter(
                transaction_id__isnull=False, booking__paid=False,
                booking__status='OPEN', booking__no_show=False
            )
        elif self.value() == 'cancelled':
            return queryset.filter(
                Q(transaction_id__isnull=False, booking__paid=False) &
                (Q(booking__status='OPEN', booking__no_show=True) | Q(booking__status='CANCELLED'))
            )
        elif self.value() == 'autocancelled':
            return queryset.filter(
                transaction_id__isnull=False, booking__paid=False,
                booking__status='CANCELLED', booking__auto_cancelled=True
            )
        else:
            return queryset


class PaypalBlockCheckFilter(PaypalCheckFilter):

    def lookups(self, request, model_admin):
        return (('yes', 'yes'),)

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(
                transaction_id__isnull=False, block__paid=False
            )
        else:
            return queryset


class PaypalBlockUserFilter(PaypalBookingUserFilter):

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(block__user__id=self.value())
        return queryset


class PaypalTicketBookingUserFilter(PaypalBookingUserFilter):

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(ticket_booking__user__id=self.value())
        return queryset


class PaypalBookingTransactionAdmin(admin.ModelAdmin):

    list_display = ('id', 'get_user', 'get_event', 'invoice_id',
                    'transaction_id', 'get_booking_id', 'paid', 'paid_by_block',
                    'booking_status'
                    )
    readonly_fields = ('id', 'booking', 'get_user', 'get_event', 'invoice_id',
                       'get_booking_id', 'cost', 'voucher_code')
    list_filter = (PaypalBookingUserFilter, PaypalBookingCheckFilter, 'booking__event')

    def get_booking_id(self, obj):
        return obj.booking.id if obj.booking else None
    get_booking_id.short_description = "Booking id"

    def get_user(self, obj):
        return "{} {}".format(
            obj.booking.user.first_name, obj.booking.user.last_name
        ) if obj.booking else None

    get_user.short_description = "User"

    def get_event(self, obj):
        return obj.booking.event if obj.booking else None
    get_event.short_description = "Event"

    def cost(self, obj):
        return u"\u00A3{:.2f}".format(obj.booking.event.cost) if obj.booking else None

    def paid(self, obj):
        return obj.booking.paid if obj.booking else None
    paid.boolean = True

    def paid_by_block(self, obj):
        return bool(obj.booking.block) if obj.booking else None
    paid_by_block.boolean = True

    def booking_status(self, obj):
        if not obj.booking:
            return None

        if obj.booking.status == 'CANCELLED' and obj.booking.auto_cancelled:
            return 'AUTOCANCELLED'
        elif obj.booking.no_show:
            return 'NO SHOW'
        else:
            return obj.booking.status

class PaypalBlockTransactionAdmin(admin.ModelAdmin):

    list_display = ('id', 'get_user', 'get_blocktype', 'invoice_id',
                    'transaction_id', 'get_block_id', 'paid')
    readonly_fields = ('block', 'id', 'get_user', 'get_blocktype', 'invoice_id',
                    'get_block_id', 'cost', 'block_start',
                    'block_expiry')
    list_filter = (PaypalBlockUserFilter, PaypalBlockCheckFilter)

    def get_block_id(self, obj):
        return obj.block.id if obj.block else None
    get_block_id.short_description = "Block id"

    def get_user(self, obj):
        return "{} {}".format(
            obj.block.user.first_name, obj.block.user.last_name
        ) if obj.block else None
    get_user.short_description = "User"

    def get_blocktype(self, obj):
        return obj.block.block_type if obj.block else None
    get_blocktype.short_description = "BlockType"

    def block_start(self, obj):
        return obj.block.start_date.strftime('%d %b %Y, %H:%M') if obj.block else None
    block_start.short_description = 'Start date'

    def block_expiry(self, obj):
        return obj.block.expiry_date.strftime('%d %b %Y, %H:%M') if obj.block else None
    block_expiry.short_description = 'Expiry date'

    def cost(self, obj):
        return u"\u00A3{:.2f}".format(obj.block.block_type.cost) if obj.block else None

    def paid(self, obj):
        return obj.block.paid if obj.block else None
    paid.boolean = True


class PaypalTicketBookingTransactionAdmin(admin.ModelAdmin):

    list_display = ('id', 'get_user', 'get_ticketed_event', 'invoice_id',
                    'get_ticket_booking_id', 'ticket_cost',
                       'number_of_tickets', 'total_cost', 'paid')
    readonly_fields = ('id', 'ticket_booking', 'get_user', 'get_ticketed_event',
                       'invoice_id', 'transaction_id', 'get_ticket_booking_id',
                       'ticket_cost', 'number_of_tickets', 'total_cost')
    list_filter = (
        PaypalTicketBookingUserFilter, 'ticket_booking__ticketed_event'
    )

    def get_ticket_booking_id(self, obj):
        return obj.ticket_booking.id if obj.ticket_booking else None
    get_ticket_booking_id.short_description = "Ticket booking id"

    def get_user(self, obj):
        return "{} {}".format(
            obj.ticket_booking.user.first_name, obj.ticket_booking.user.last_name
        ) if obj.ticket_booking else None
    get_user.short_description = "User"

    def get_ticketed_event(self, obj):
        return obj.ticket_booking.ticketed_event if obj.ticket_booking else None
    get_ticketed_event.short_description = "Event"

    def ticket_cost(self, obj):
        return u"\u00A3{:.2f}".format(
            obj.ticket_booking.ticketed_event.ticket_cost
        )

    def number_of_tickets(self, obj):
        return obj.ticket_booking.tickets.count() if obj.ticket_booking else None

    def total_cost(self, obj):
        return u"\u00A3{:.2f}".format(
            obj.ticket_booking.ticketed_event.ticket_cost *
            obj.ticket_booking.tickets.count()
        ) if obj.ticket_booking else None

    def paid(self, obj):
        return obj.ticket_booking.paid if obj.ticket_booking else None
    paid.boolean = True


class PayPalAdmin(PayPalIPNAdmin):

    search_fields = [
        "txn_id", "recurring_payment_id", 'custom', 'invoice',
        'first_name', 'last_name'
    ]
    list_display = [
        "txn_id", "flag", "flag_info", "invoice", "custom",
        "payment_status", "buyer", "created_at"
    ]

    def buyer(self, obj):
        return "{} {}".format(obj.first_name, obj.last_name)
    buyer.admin_order_field = 'first_name'


admin.site.register(PaypalBookingTransaction, PaypalBookingTransactionAdmin)
admin.site.register(PaypalBlockTransaction, PaypalBlockTransactionAdmin)
admin.site.register(
    PaypalTicketBookingTransaction, PaypalTicketBookingTransactionAdmin
)
admin.site.unregister(PayPalIPN)
admin.site.register(PayPalIPN, PayPalAdmin)
