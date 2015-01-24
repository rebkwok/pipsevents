from django.contrib import admin
from booking.models import Event, Booking, Location


class EventAdmin(admin.ModelAdmin):
    list_display = ('name', 'date')
    # prepopulated_fields = {"slug": ("name",)}


class BookingAdmin(admin.ModelAdmin):
    list_display = ('event', 'user', 'paid')



admin.site.register(Location)
admin.site.register(Event, EventAdmin)
admin.site.register(Booking, BookingAdmin)
