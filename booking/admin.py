from django.conf import settings
from django.contrib import admin
from django import forms
from django.core.mail import send_mail
from django.template.loader import get_template
from django.template import Context
from django.utils import timezone
from booking.models import Event, Booking
from django.contrib.admin import DateFieldListFilter
from suit.widgets import SuitSplitDateTimeWidget


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


class EventAdminForm(forms.ModelForm):
  class Meta:
    model = Event
    fields = '__all__'
    widgets = {
      'date': SuitSplitDateTimeWidget(),
    }

class StopAdmin(admin.ModelAdmin):
  form = EventAdminForm

class EventAdmin(admin.ModelAdmin):
    list_display = ('name', 'date', 'location')
    list_filter = (EventDateListFilter, 'name')
    form = EventAdminForm

    class Meta:
        widgets = {
            'date': SuitSplitDateTimeWidget,
        }


class BookingAdmin(admin.ModelAdmin):

    list_display = ('event', 'get_date', 'user', 'get_user_first_name',
                    'get_user_last_name', 'get_cost', 'paid',
                    'space_confirmed')

    list_filter = (BookingDateListFilter, 'user', 'event')


    def get_date(self, obj):
        return obj.event.date
    get_date.short_description = 'Date'

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


admin.site.register(Event, EventAdmin)
admin.site.register(Booking, BookingAdmin)
