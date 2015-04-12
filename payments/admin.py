from django.contrib import admin
from payments.models import PaypalBookingTransaction, PaypalBlockTransaction


class PaypalBookingTransactionAdmin(admin.ModelAdmin):

    list_display = ('id', 'get_user', 'get_event', 'invoice_id',
                    'transaction_id')
    readonly_fields = ('id', 'booking', 'get_user', 'get_event', 'invoice_id',
                    'transaction_id', 'get_booking_id', 'cost')

    def get_booking_id(self, obj):
        return obj.booking.id
    get_booking_id.short_description = "Booking id"

    def get_user(self, obj):
        return "{} {}".format(
            obj.booking.user.first_name, obj.booking.user.last_name
        )
    get_user.short_description = "User"

    def get_event(self, obj):
        return obj.booking.event
    get_event.short_description = "Event"

    def cost(self, obj):
        return u"\u00A3{:.2f}".format(obj.booking.event.cost)


class PaypalBlockTransactionAdmin(admin.ModelAdmin):

    list_display = ('id', 'get_user', 'get_blocktype', 'invoice_id',
                    'transaction_id')
    readonly_fields = ('block', 'id', 'get_user', 'get_blocktype', 'invoice_id',
                    'transaction_id', 'get_block_id', 'cost', 'block_start',
                    'block_expiry')


    def get_block_id(self, obj):
        return obj.block.id
    get_block_id.short_description = "Block id"

    def get_user(self, obj):
        return "{} {}".format(
            obj.block.user.first_name, obj.block.user.last_name
        )
    get_user.short_description = "User"

    def get_blocktype(self, obj):
        return obj.block.block_type
    get_blocktype.short_description = "BlockType"

    def block_start(self, obj):
        return obj.block.start_date.strftime('%d %b %Y, %H:%M')
    block_start.short_description = 'Start date'

    def block_expiry(self, obj):
        return obj.block.expiry_date.strftime('%d %b %Y, %H:%M')
    block_expiry.short_description = 'Expiry date'

    def cost(self, obj):
        return u"\u00A3{:.2f}".format(obj.block.block_type.cost)


admin.site.register(PaypalBookingTransaction, PaypalBookingTransactionAdmin)
admin.site.register(PaypalBlockTransaction, PaypalBlockTransactionAdmin)
