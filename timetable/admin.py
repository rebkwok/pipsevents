from django.contrib import admin
from django import forms
from suit.widgets import EnclosedInput
from timetable.models import Session
from ckeditor.widgets import CKEditorWidget


class SessionForm(forms.ModelForm):
    description = forms.CharField(widget=CKEditorWidget())

    class Meta:
        widgets = {
            # You can also use prepended and appended together
            'cost': EnclosedInput(prepend=u'\u00A3'),
        }


class SessionAdmin(admin.ModelAdmin):
    list_display = ('day', 'time', 'name')
    ordering = ('day', 'time')
    fields = ('name', 'day', 'time', 'event_type', 'description', 'location',
              'max_participants', 'contact_person', 'contact_email',
              'email_studio_when_booked', 'cost',
              'external_instructor', 'booking_open', 'payment_open')
    model = Session
    form = SessionForm


admin.site.register(Session, SessionAdmin)
