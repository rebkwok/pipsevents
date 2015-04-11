from django.contrib import admin
from payments.models import PaypalBookingTransaction, PaypalBlockTransaction


class PaypalBookingTransactionAdmin(admin.ModelAdmin):

    list_display = ('get_booking_id', 'get_user', 'get_event', 'invoice_id', 'transaction_id')

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


class PaypalBlockTransactionAdmin(admin.ModelAdmin):

    list_display = ('get_block_id', 'get_user', 'get_blocktype', 'invoice_id', 'transaction_id')

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


admin.site.register(PaypalBookingTransaction, PaypalBookingTransactionAdmin)
admin.site.register(PaypalBlockTransaction, PaypalBlockTransactionAdmin)
