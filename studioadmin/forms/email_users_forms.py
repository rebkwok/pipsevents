# -*- coding: utf-8 -*-

from django import forms
from django.conf import settings
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth.models import User
from django.forms.models import modelformset_factory, BaseModelFormSet
from django.utils import timezone
from booking.models import Event

from ckeditor.widgets import CKEditorWidget


def get_event_names(event_type):

    def callable():
        EVENT_CHOICES = [(event.id, str(event)) for event in Event.objects.filter(
            event_type__event_type=event_type, date__gte=timezone.now()
        ).order_by('date')]
        return tuple(EVENT_CHOICES)

    return callable


def get_students():

    def callable():
        return tuple(
            [
                (user.id, '{} {} ({})'.format(
                    user.first_name, user.last_name, user.username
                )) for user in User.objects.all()
                ]
        )
    return callable

        
class UserFilterForm(forms.Form):

    events = forms.MultipleChoiceField(
        choices=get_event_names('EV'),
        widget=FilteredSelectMultiple('Events/Workshops', False),
        required=False
    )

    lessons = forms.MultipleChoiceField(
        choices=get_event_names('CL'),
        widget=FilteredSelectMultiple('Classes', False),
        required=False
    )
    students = forms.MultipleChoiceField(
        choices=get_students(),
        widget=FilteredSelectMultiple('Students', False),
        required=False
    )


class ChooseUsersBaseFormSet(BaseModelFormSet):

    def add_fields(self, form, index):
        super(ChooseUsersBaseFormSet, self).add_fields(form, index)

        form.fields['email_user'] = forms.BooleanField(
            widget=forms.CheckboxInput(attrs={
                'class': "regular-checkbox studioadmin-list select-checkbox",
                'id': 'email_user_cbox_{}'.format(index)
            }),
            initial=True,
            required=False
        )
        form.email_user_cbox_id = 'email_user_cbox_{}'.format(index)

ChooseUsersFormSet = modelformset_factory(
    User,
    fields=('id',),
    formset=ChooseUsersBaseFormSet,
    extra=0,
    max_num=2000,
    can_delete=False)


class EmailUsersForm(forms.Form):
    subject = forms.CharField(max_length=255, required=True,
                              widget=forms.TextInput(
                                  attrs={'class': 'form-control'}))
    from_address = forms.EmailField(max_length=255,
                                    initial=settings.DEFAULT_STUDIO_EMAIL,
                                    required=True,
                                    widget=forms.TextInput(
                                        attrs={'class': 'form-control'}),
                                    help_text='This will be the reply-to address')
    cc = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={
                'class': "regular-checkbox studioadmin-list",
                'id': 'cc_id'
            }),
        label="cc. from address",
        initial=True,
        required=False
    )

    message = forms.CharField(widget=CKEditorWidget(
                attrs={'class': 'form-control container-fluid'},
                config_name='studioadmin',
            ))