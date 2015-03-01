from django.contrib import admin
from timetable.models import Session


class SessionAdmin(admin.ModelAdmin):
    list_display = ('day', 'time', 'name')
    ordering = ('day', 'time')
    fields = ('name', 'day', 'time', 'type', 'description', 'location',
              'max_participants', 'contact_person', 'contact_email',
              'cost', 'payment_open')
    model = Session

admin.site.register(Session, SessionAdmin)