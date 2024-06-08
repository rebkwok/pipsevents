from django.contrib import admin
from django.urls import reverse
from django.utils.safestring import mark_safe 

from booking.models import Booking, Block
from stripe_payments.models import Invoice, StripePaymentIntent, Seller, StripeSubscriptionInvoice


from django.contrib import admin
from django.urls import reverse
from django.utils.safestring import mark_safe 

from booking.models import Booking, Block, TicketBooking, BlockVoucher, EventVoucher, TicketBooking, UserMembership
from stripe_payments.models import Invoice, StripePaymentIntent


class BookingInline(admin.TabularInline):
    fields = ("id", "user", "event", "status", "voucher_code")
    readonly_fields = ("user", "event", "status", "voucher_code")
    model = Booking
    extra = 0


class TicketBookingInline(admin.TabularInline):
    fields = ("id", "user", "ticketed_event")
    readonly_fields = ("user", "ticketed_event")
    model = TicketBooking
    extra = 0


class BlockInline(admin.TabularInline):
    fields = ("user", "block_type", "voucher_code")
    readonly_fields = ("user", "block_type", "voucher_code")
    model = Block
    extra = 0


class BlockVoucherInline(admin.TabularInline):
    fields = ("purchaser_email", "code", "block_types")
    readonly_fields = ("purchaser_email", "code", "block_types")
    model = BlockVoucher
    extra = 0


class EventVoucherInline(admin.TabularInline):
    fields = ("purchaser_email", "code", "event_types")
    readonly_fields = ("purchaser_email", "code", "event_types")
    model = EventVoucher
    extra = 0
    

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_id", "pi", "get_username", "display_amount", "paid", "items")

    fields = (
        "invoice_id", "username", "stripe_payment_intent_id", "payment_intent_ids",
        "amount", "date_created", "paid", "date_paid",
    )
    readonly_fields = fields
    search_fields = (
        'invoice_id', 'username'
    )
    list_filter = ("paid", "username")

    inlines = (BookingInline, BlockInline, BlockVoucherInline, EventVoucherInline, TicketBookingInline)

    def get_username(self, obj):
        return obj.username
    get_username.short_description = "Email"
    get_username.admin_order_field = "username"

    def display_amount(self, obj):
        return f"£{obj.amount}"
    display_amount.short_description = "amount"
    display_amount.admin_order_field = "amount"

    def pi(self, obj):
        if obj.payment_intents.exists():
            pi = obj.payment_intents.first()
            return mark_safe(
                '<a href="{}">{}</a>'.format(
                reverse("admin:stripe_payments_stripepaymentintent_change", args=(pi.pk,)),
                pi.payment_intent_id
            ))
        return ""
    pi.short_description = "Payment Intent"

    def items(self, obj):
        return _inv_items(obj)


@admin.register(StripePaymentIntent)
class StripePaymentIntentAdmin(admin.ModelAdmin):
    list_display = ("payment_intent_id", "inv", "username", "status", "items")
    exclude = ("client_secret","seller")
    fields = (
        "payment_intent_id", "amount", "description", "status", "invoice",
        "metadata", "currency" 
    )
    search_fields = (
        'payment_intent_id', 'invoice__invoice_id', 'invoice__username'
    )
    list_filter = ("status", "invoice__username")
    readonly_fields = fields

    def username(self, obj):
        return obj.invoice.username

    def inv(self, obj):
        return mark_safe(
            '<a href="{}">{}</a>'.format(
            reverse("admin:stripe_payments_invoice_change", args=(obj.invoice.pk,)),
            obj.invoice.invoice_id
        ))
    inv.short_description = "Invoice"

    def items(self, obj):
        return _inv_items(obj.invoice)


def _inv_items(invoice):
    items = sum(list(invoice.items_summary().values()), [])
    if items:
        items = [f"<li>{item}</li>" for item in items]
        return mark_safe(f"<ul>{''.join(items)}</ul>")
    return ""


@admin.register(StripeSubscriptionInvoice)
class StripeSubscriptionInvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "subscription_id", "user_membership", "invoice_id", "status", "total", "invoice_date"
    )
    readonly_fields = ("subscription_id", "invoice_id", "status", "total", "invoice_date")

    def user_membership(self, obj):
        try:
            return str(UserMembership.objects.get(subscription_id=obj.subscription_id))
        except UserMembership.DoesNotExist:
            return None


admin.site.register(Seller)
