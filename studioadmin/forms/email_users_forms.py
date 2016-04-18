# -*- coding: utf-8 -*-

from django import forms
from django.conf import settings
from django.contrib.auth.models import User
from django.forms.models import modelformset_factory, BaseModelFormSet
from django.utils import timezone
from booking.models import Event


def get_event_names(event_type):

    def callable():
        EVENT_CHOICES = [(event.id, str(event)) for event in Event.objects.filter(
            event_type__event_type=event_type, date__gte=timezone.now()
        ).order_by('date')]
        EVENT_CHOICES.insert(0, ('', '--None selected--'))
        return tuple(EVENT_CHOICES)

    return callable


class UserFilterForm(forms.Form):

    events = forms.MultipleChoiceField(
        choices=get_event_names('EV'),
        widget=forms.SelectMultiple(
            attrs={'class': 'form-control', 'style': 'font-size: smaller;'}
        ),
    )

    lessons = forms.MultipleChoiceField(
        choices=get_event_names('CL'),
        widget=forms.SelectMultiple(
            attrs={'class': 'form-control', 'style': 'font-size: smaller;'}
        ),
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
    message = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control email-message',
                                     'rows': 10}),
        required=True)
