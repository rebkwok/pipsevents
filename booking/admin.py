# -*- coding: utf-8 -*-
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.template.loader import get_template
from django.utils import timezone
from django.utils.safestring import mark_safe
from django import forms
from django.urls import reverse
from ckeditor.widgets import CKEditorWidget

from booking.models import Event, Booking, Block, BlockType, \
    EventType, GiftVoucherType, WaitingListUser, TicketedEvent, TicketBooking, Ticket, \
    BlockVoucher, EventVoucher, UsedBlockVoucher, UsedEventVoucher
from booking.forms import TicketBookingAdminForm, WaitingListUserAdminForm
from booking.widgets import DurationSelectorWidget


class UserFilter(admin.SimpleListFilter):

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
            return queryset.filter(user__id=self.value())
        return queryset


class BookingDateListFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = 'date'

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'event__date'

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        return (
            ('past', ('past events only')),
            ('upcoming', ('upcoming events only')),
        )

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        # Compare the requested value
        # to decide how to filter the queryset.
        if self.value() == 'past':
            return queryset.filter(event__date__lte=timezone.now())
        if self.value() == 'upcoming':
            return queryset.filter(event__date__gte=timezone.now())
        return queryset


class EventDateListFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = 'date'

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'date'

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        return (
            ('past', 'past events only'),
            ('upcoming', 'upcoming events only'),
        )

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        # Compare the requested value
        # to decide how to filter the queryset.
        if self.value() == 'past':
            return queryset.filter(date__lte=timezone.now())
        if self.value() == 'upcoming':
            return queryset.filter(date__gte=timezone.now())
        return queryset


class EventTypeListFilter(admin.SimpleListFilter):
    """
    Filter by class or event
    """
    title = 'Type'

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'type'

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        return (
            ('class', 'Classes'),
            ('event', 'Workshops and Other Events'),
        )

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        # Compare the requested value
        # to decide how to filter the queryset.
        if self.value() == 'class':
            return queryset.filter(event_type__event_type='CL')
        if self.value() == 'event':
            return queryset.filter(event_type__event_type='EV')
        return queryset


class EventForm(forms.ModelForm):

    description = forms.CharField(
        widget=CKEditorWidget(attrs={'class': 'container-fluid'}),
        required=False
    )

    class Meta:
        widgets = {
            'cancellation_period': DurationSelectorWidget(),
            }


class EventAdmin(admin.ModelAdmin):
    list_display = ('name', 'date', 'location', 'get_spaces_left', 'visible_on_site')
    list_filter = (EventDateListFilter, 'name', EventTypeListFilter)
    actions_on_top = True
    form = EventForm

    CANCELLATION_TEXT = ' '.join(['<p>Enter cancellation period in',
                                  'weeks, days and/or hours.</br>',
                                  'Note that 1 day will be displayed to users ',
                                  'as "24 hours" for clarity.</p>',
                                  ])

    fieldsets = [
        ('Event details', {
            'fields': (
                'name', 'date', 'location', 'location_index', 'event_type',
                'max_participants', 'description', 'video_link', 'cancelled')
        }),
        ('Contacts', {
            'fields': ('contact_person', 'contact_email', 'email_studio_when_booked')
        }),
        ('Payment Information', {
            'fields': ('cost', 'advance_payment_required', 'booking_open',
            'payment_open', 'payment_info',  'payment_due_date', 'visible_on_site')
        }),
        ('Cancellation Period', {
            'fields': ('cancellation_period',),
            'description': '<div class="help">%s</div>' % CANCELLATION_TEXT,
        }),
    ]

    def get_spaces_left(self, obj):
        return obj.spaces_left
    get_spaces_left.short_description = '# Spaces left'


class BookingAdmin(admin.ModelAdmin):

    list_display = ('event_name', 'get_date', 'get_user', 'get_cost', 'paid',
                    'space_confirmed', 'status')

    list_filter = (BookingDateListFilter, UserFilter, 'event')

    readonly_fields = ('date_payment_confirmed',)

    search_fields = (
        'user__first_name', 'user__last_name', 'user__username', 'event__name'
    )

    raw_id_fields = ('user', 'event', 'block')

    actions_on_top = True
    actions_on_bottom = False

    def get_date(self, obj):
        return obj.event.date
    get_date.short_description = 'Date'
    get_date.admin_order_field = 'event__date'

    def event_name(self, obj):
        return obj.event.name
    event_name.short_description = 'Event or Class'
    event_name.admin_order_field = 'event'

    def get_user(self, obj):
        return '{} {} ({})'.format(
            obj.user.first_name, obj.user.last_name, obj.user.username
        )
    get_user.short_description = 'User'
    get_user.admin_order_field = 'user__first_name'

    actions = ['confirm_space']

    def get_cost(self, obj):
        return u"\u00A3{:.2f}".format(obj.event.cost)
    get_cost.short_description = 'Cost'

    def confirm_space(self, request, queryset):
        for obj in queryset:
            obj.confirm_space()

            send_mail('{} Space for {} confirmed'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, obj.event.name),
                get_template('booking/email/space_confirmed.txt').render(
                    {
                        'event': obj.event.name,
                        'date': obj.event.date.strftime('%A %d %B'),
                        'time': obj.event.date.strftime('%I:%M %p')
                    }
                ),
                settings.DEFAULT_FROM_EMAIL,
                [obj.user.email],
                fail_silently=False)

    confirm_space.short_description = \
        "Mark selected bookings as paid and confirmed"


class BookingInLine(admin.TabularInline):
    fields = ('event', 'user', 'paid', 'payment_confirmed', 'status')
    readonly_fields = ('user', 'paid', 'payment_confirmed')
    model = Booking
    extra = 0

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "event":
            parent_obj_id = request.resolver_match.kwargs.get('object_id')
            if parent_obj_id:
                block = Block.objects.get(id=str(parent_obj_id))
                kwargs["queryset"] = Event.objects.filter(
                    event_type=block.block_type.event_type
                )
        return super(
            BookingInLine, self
        ).formfield_for_foreignkey(db_field, request, **kwargs)


class BlockFilter(admin.SimpleListFilter):
    """
    Filter by active block
    """
    title = 'Block status'

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return (
            ('active', 'Active blocks'),
            ('inactive', 'Expired/Full blocks'),
            ('unpaid', 'Unpaid blocks (not expired)')
        )

    def queryset(self, request, queryset):
        active_ids = [obj.id for obj in queryset if obj.active_block()]
        if self.value() == 'active':
            return queryset.filter(id__in=active_ids)
        if self.value() == 'inactive':
            return queryset.exclude(id__in=active_ids)
        if self.value() == 'unpaid':
            unpaid_ids = [obj.id for obj in queryset if not obj.full
            and not obj.expired and not obj.paid]
            return queryset.filter(id__in=unpaid_ids)
        return queryset


class BlockAdmin(admin.ModelAdmin):
    fields = ('user', 'user_name', 'block_type', 'parent',
              'transferred_booking_id',
              'formatted_cost', 'start_date', 'paypal_pending',
              'paid', 'extended_expiry_date', 'formatted_expiry_date')
    readonly_fields = ('formatted_cost', 'formatted_expiry_date', 'user_name',)
    list_display = ('get_user', 'block_type', 'block_size', 'active_block',
                    'get_full', 'paid', 'formatted_start_date', 'formatted_expiry_date')
    list_editable = ('paid', )
    list_filter = (UserFilter, 'block_type__identifier', 'block_type__event_type', BlockFilter,)

    raw_id_fields = ('user', 'parent')

    inlines = [BookingInLine, ]
    actions_on_top = True

    def get_user(self, obj):
        return '{} {} ({})'.format(
            obj.user.first_name, obj.user.last_name, obj.user.username
        )
    get_user.short_description = 'User'
    get_user.admin_order_field = 'user__first_name'

    def user_name(self, obj):
        return self.get_user(obj)
    user_name.short_description = 'User name'

    def get_full(self, obj):
        return obj.full
    get_full.short_description = 'Full'
    get_full.boolean = True

    def block_size(self, obj):
        return obj.block_type.size

    def formatted_cost(self, obj):
        return u"\u00A3{:.2f}".format(obj.block_type.cost)

    def formatted_start_date(self, obj):
        return obj.start_date.strftime('%d %b %Y, %H:%M')
    formatted_start_date.short_description = 'Start date'
    formatted_start_date.admin_order_field = 'start_date'

    def formatted_expiry_date(self, obj):
        return obj.expiry_date.strftime('%d %b %Y, %H:%M')
    formatted_expiry_date.short_description = 'Expiry date'

    def save_formset(self, request, form, formset, change):
        if formset.model != Booking:  # pragma: no cover
            # not used atm as Booking is the only inline
            return super(BlockAdmin, self)\
                .save_formset(request, form, formset, change)

        bookingformset = formset.save(commit=False)
        block = form.save()

        for booking in bookingformset:
            if not booking.pk:
                booking.user = block.user
                try:
                    booking.validate_unique()
                except ValidationError:
                    booking = Booking.objects.get(
                        user=block.user, event=booking.event
                    )
                    reopened = False
                    if booking.status == 'CANCELLED':
                        booking.status = 'OPEN'
                        reopened = True
                    messages.info(
                        request,
                        mark_safe('<a href={}>Booking {}</a> '
                                  'with user {} and event {} {} and '
                                  'has been associated with block {}. '.format(
                            reverse('admin:booking_booking_change', args=[booking.id]),
                            booking.id,
                            booking.user.username, booking.event,
                            'already existed' if not reopened else 'has been reopened',
                            block.id
                            )
                        ),
                    )
                booking.paid = True
                booking.payment_confirmed = True
                booking.block = block
                booking.save()
            elif booking.status == 'CANCELLED':
                booking.block = None
                booking.paid = False
                booking.payment_confirmed = False
                booking.save()
                messages.info(
                    request,
                    mark_safe('<a href={}>Booking {}</a> '
                              'with user {} and event {} has been cancelled, '
                              'set to unpaid and disassociated from block {}. '.format(
                        reverse('admin:booking_booking_change', args=[booking.id]),
                        booking.id,
                        booking.user.username, booking.event, block.id
                    )),
                )

            
class BlockTypeAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'identifier', 'size', 'formatted_cost',
                    'formatted_duration', 'active')
    actions_on_top = True

    def formatted_duration(self, obj):
        return "{} months".format(obj.duration)
    formatted_duration.short_description = "Duration"

    def formatted_cost(self, obj):
        return u"\u00A3{:.2f}".format(obj.cost)
    formatted_cost.short_description = "Cost"

    def save_form(self, request, form, change):
        blocktype = super(BlockTypeAdmin, self).save_form(request, form, change)
        identifier = form.cleaned_data.get('identifier')
        active = form.cleaned_data.get('active')
        if active and identifier not in ['standard', 'sale']:
            messages.warning(
                request,
                '{} is active and will appear on site for purchase; identifier '
                'is not standard or sale type; please check this is '
                'correct.'.format(blocktype)
            )
        return blocktype


class WaitingListUserAdmin(admin.ModelAdmin):
    fields = ('user', 'event')
    list_display = ('user', 'event')
    list_filter = (UserFilter, 'event')
    search_fields = (
        'user__first_name', 'user__last_name', 'user__username', 'event__name'
    )
    form = WaitingListUserAdminForm

class TicketAdminInline(admin.TabularInline):
    model = Ticket
    extra = 0


class TicketBookingAdmin(admin.ModelAdmin):
    list_display = (
        'ticketed_event', 'user', 'booking_reference', 'number_of_tickets',
        'paid', 'cancelled', 'purchase_confirmed'
    )
    form = TicketBookingAdminForm
    search_fields = (
        'user__first_name', 'user__last_name', 'user__username',
        'ticketed_event__name'
    )
    list_filter = (UserFilter, 'ticketed_event')
    actions_on_top = True

    inlines = (TicketAdminInline,)

    def number_of_tickets(self, obj):
        return obj.tickets.count()


class TicketedEventAdmin(admin.ModelAdmin):
    list_display = ('name', 'date', 'tickets_left')


class TicketAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'ticket_booking_ref', 'ticketed_event', 'user'
    )

    def ticketed_event(self, obj):
        return obj.ticket_booking.ticketed_event
    ticketed_event.short_description = 'Event'
    ticketed_event.admin_order_field = 'ticket_booking__ticketed_event'

    def ticket_booking_ref(self, obj):
        return obj.ticket_booking.booking_reference
    ticket_booking_ref.short_description = 'Ticket Booking Reference'
    ticket_booking_ref.admin_order_field = 'ticket_booking__booking_reference'

    def user(self, obj):
        return '{} {} ({})'.format(
            obj.ticket_booking.user.first_name,
            obj.ticket_booking.user.last_name,
            obj.ticket_booking.user.username
        )
    user.admin_order_field = 'ticket_booking__user__first_name'


class EventVoucherAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'discount', 'start_date', 'expiry_date', 'max_vouchers',
        'ev_types', 'times_used'
    )

    def ev_types(self, obj):
        return ', '.join(et.subtype for et in obj.event_types.all())
    ev_types.short_description = 'Event types'

    def times_used(self, obj):
        return UsedEventVoucher.objects.filter(voucher=obj).count()


class BlockVoucherAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'discount', 'start_date', 'expiry_date', 'max_vouchers',
        'get_block_types', 'times_used'
    )

    def get_block_types(self, obj):
        return ', '.join([str(bt) for bt in obj.block_types.all()])
    get_block_types.short_description = 'Block types'

    def times_used(self, obj):
        return UsedBlockVoucher.objects.filter(voucher=obj).count()


class UsedEventVoucherAdmin(admin.ModelAdmin):
    list_display = (
        'voucher', 'user', 'booking_id'
    )
    list_filter = ('voucher', UserFilter)


class UsedBlockVoucherAdmin(admin.ModelAdmin):
    list_display = (
        'voucher', 'user', 'block_id'
    )
    list_filter = ('voucher', UserFilter)


class GiftVoucherTypeAdmin(admin.ModelAdmin):
    list_display = (
        'voucher_type', 'cost'
    )

    def voucher_type(self, obj):
        if obj.block_type:
            return obj.block_type
        return obj.event_type

admin.site.site_header = "Watermelon Admin"
admin.site.register(Event, EventAdmin)
admin.site.register(Booking, BookingAdmin)
admin.site.register(Block, BlockAdmin)
admin.site.register(BlockType, BlockTypeAdmin)
admin.site.register(EventType)
admin.site.register(WaitingListUser, WaitingListUserAdmin)
admin.site.register(TicketBooking, TicketBookingAdmin)
admin.site.register(Ticket, TicketAdmin)
admin.site.register(TicketedEvent, TicketedEventAdmin)
admin.site.register(EventVoucher, EventVoucherAdmin)
admin.site.register(BlockVoucher, BlockVoucherAdmin)
admin.site.register(UsedEventVoucher, UsedEventVoucherAdmin)
admin.site.register(UsedBlockVoucher, UsedBlockVoucherAdmin)
admin.site.register(GiftVoucherType, GiftVoucherTypeAdmin)
