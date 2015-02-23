from django.conf import settings
from django.contrib import admin
from django import forms
from django.core.mail import send_mail
from django.template.loader import get_template
from django.template import Context
from django.utils import timezone
from booking.models import Event, Booking, Block
from django.contrib.admin import DateFieldListFilter


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
            return queryset.filter(date__lte=timezone.now())
        if self.value() == 'upcoming':
            return queryset.filter(date__gte=timezone.now())


# TODO validation on event fields - e.g. payment due date can't be after event
# TODO date, event date can't be in past, cost must be >= 0
class EventAdmin(admin.ModelAdmin):
    list_display = ('name', 'date', 'location')
    list_filter = (EventDateListFilter, 'name')

# TODO add custom button and form/view for creating a week's classes from any
# TODO given date
# TODO or/and add this to the main page menu, visible by staff users only


class BookingAdmin(admin.ModelAdmin):

    list_display = ('event_name', 'get_date', 'user', 'get_user_first_name',
                    'get_user_last_name', 'get_cost', 'paid',
                    'space_confirmed')

    list_filter = (BookingDateListFilter, 'user', 'event')

    readonly_fields = ('date_payment_confirmed', 'date_space_confirmed')

    def get_date(self, obj):
        return obj.event.date
    get_date.short_description = 'Date'

    def event_name(self, obj):
        return obj.event.name
    event_name.short_name = 'Event'

    def get_user_first_name(self, obj):
        return obj.user.first_name
    get_user_first_name.short_description = 'First name'

    def get_user_last_name(self, obj):
        return obj.user.last_name
    get_user_last_name.short_description = 'Last name'

    actions = ['confirm_space']

    def get_cost(self, obj):
        return obj.event.cost
    get_cost.short_description = 'Cost (GBP)'

    def confirm_space(self, request, queryset):
        for obj in queryset:
            obj.confirm_space()

            send_mail('{} Space for {} confirmed'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, obj.event.name),
                get_template('booking/email/space_confirmed.txt').render(
                    Context({'event': obj.event.name,
                             'date': obj.event.date.strftime('%A %d %B'),
                             'time': obj.event.date.strftime('%I:%M %p')
                    })
                ),
                settings.DEFAULT_FROM_EMAIL,
                [obj.user.email],
                fail_silently=False)

    confirm_space.short_description = \
        "Mark selected bookings as paid and confirmed"


class BookingInLine(admin.TabularInline):
    fields = ('event', )
    readonly_fields = ('event',)
    model = Booking
    extra = 0


class BlockAdmin(admin.ModelAdmin):
    fields = ('user', 'block_size', 'formatted_cost', 'formatted_start_date',
              'formatted_expiry_date',
              'paid', 'payment_confirmed')
    readonly_fields = ('formatted_start_date', 'formatted_cost',
                       'formatted_expiry_date')
    search_fields = ('user', 'active_block')
    list_display = ('user', 'block_size', 'active_block')

    inlines = [BookingInLine, ]

    def formatted_cost(self, obj):
        return obj.cost
    formatted_cost.short_description = 'Cost (GBP)'

    def formatted_start_date(self, obj):
        return obj.start_date.strftime('%d %b %Y, %H:%M')
    formatted_start_date.short_description = 'Start date'

    def formatted_expiry_date(self, obj):
        return obj.expiry_date.strftime('%d %b %Y, %H:%M')
    formatted_expiry_date.short_description = 'Expiry date'

admin.site.register(Event, EventAdmin)
admin.site.register(Booking, BookingAdmin)
admin.site.register(Block, BlockAdmin)

