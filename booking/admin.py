from django.conf import settings
from django.conf.urls import patterns
from django.contrib import admin
from django.core.mail import send_mail
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.template.loader import get_template
from django.template import Context
from django.utils import timezone
from django import forms
from suit.widgets import EnclosedInput
from booking.models import Event, Booking, Block
from booking.forms import CreateClassesForm
from booking import utils

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
            return queryset.filter(Q(type=Event.POLE_CLASS) | Q(type=Event.OTHER_CLASS))
        if self.value() == 'event':
            return queryset.filter(Q(type=Event.WORKSHOP) | Q(type=Event.OTHER_EVENT))


class EventForm(forms.ModelForm):
    class Meta:
        widgets = {
            # You can also use prepended and appended together
            'cost': EnclosedInput(prepend='£'),
        }


# TODO validation on event fields - e.g. payment due date can't be after event
# TODO date, event date can't be in past, cost must be >= 0
class EventAdmin(admin.ModelAdmin):
    list_display = ('name', 'date', 'location')
    list_filter = (EventDateListFilter, 'name', EventTypeListFilter)
    form = EventForm

    def get_urls(self):
        urls = super(EventAdmin, self).get_urls()
        extra_urls = patterns(
            '',
            (r'^create-timetabled-classes/$',
             self.admin_site.admin_view(self.create_classes_view))
        )
        return extra_urls + urls

    def create_classes_view(self, request,
                            template_name="admin/create_classes_form.html"):
        # custom view which should return an HttpResponse

        if request.method == 'POST':
            form = CreateClassesForm(request.POST)
            if form.is_valid():
                date = form.cleaned_data['date']
                created_classes, existing_classes = \
                    utils.create_classes(week='this', input_date=date)
                context = {'input_date': date,
                           'created_classes': created_classes,
                           'existing_classes': existing_classes}
                return render(
                    request, 'admin/create_classes_confirmation.html', context
                )
        else:
            form = CreateClassesForm()
        return render(request, template_name, {'form': form})


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
    event_name.short_description = 'Event or Class'
    event_name.admin_order_field = 'event'

    def get_user_first_name(self, obj):
        return obj.user.first_name
    get_user_first_name.short_description = 'First name'

    def get_user_last_name(self, obj):
        return obj.user.last_name
    get_user_last_name.short_description = 'Last name'

    actions = ['confirm_space']

    def get_cost(self, obj):
        return "£{:.2f}".format(obj.event.cost)
    get_cost.short_description = 'Cost'

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


class BlockFilter(admin.SimpleListFilter):
    """
    Filter by active block
    """
    title = 'Block status'

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'active'

    def lookups(self, request, model_admin):
        return (
            ('active', 'Active blocks'),
            ('inactive', 'Expired/inactive blocks')
        )

    def queryset(self, request, queryset):
        if self.value() == 'active':
            return [obj for obj in queryset if obj.active_block()]
        if self.value() == 'inactive':
            return [obj for obj in queryset if not obj.active_block()]


class BlockAdmin(admin.ModelAdmin):
    fields = ('user', 'block_size', 'formatted_cost', 'paid',
              'payment_confirmed')
    readonly_fields = ('formatted_start_date', 'formatted_cost',
                       'formatted_expiry_date')
    search_fields = ('user', 'active_block')
    list_display = ('user', 'block_size', 'active_block',
                    'formatted_start_date', 'formatted_expiry_date')
    list_filter = (BlockFilter,)

    inlines = [BookingInLine, ]

    def formatted_cost(self, obj):
        return "£{:.2f}".format(obj.cost)

    def formatted_start_date(self, obj):
        return obj.start_date.strftime('%d %b %Y, %H:%M')
    formatted_start_date.short_description = 'Start date'

    def formatted_expiry_date(self, obj):
        return obj.expiry_date.strftime('%d %b %Y, %H:%M')
    formatted_expiry_date.short_description = 'Expiry date'


admin.site.register(Event, EventAdmin)
admin.site.register(Booking, BookingAdmin)
admin.site.register(Block, BlockAdmin)

