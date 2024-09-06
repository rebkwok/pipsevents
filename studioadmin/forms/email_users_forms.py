# -*- coding: utf-8 -*-

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from django.forms.utils import ErrorList
import pytz
from django import forms
from django.conf import settings
from django.contrib.auth.models import User
from django.forms.models import modelformset_factory, BaseModelFormSet
from django.utils import timezone

from django_select2 import forms as s2forms

from booking.models import Event

from ckeditor.widgets import CKEditorWidget


class StudentWidget(s2forms.ModelSelect2MultipleWidget):
    search_fields = [
        "username__icontains",
        "first_name__icontains",
        "last_name__icontains",
    ]

    def get_queryset(self):
        return User.objects.all().order_by("first_name", "last_name")

    def label_from_instance(self, obj):
        return f"{obj.first_name} {obj.last_name} ({obj.username})"


class UserFilterForm(forms.Form):

    events = forms.ModelMultipleChoiceField(
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label="Choose events/workshops",
        queryset=Event.objects.filter(
            event_type__event_type="EV", date__gte=timezone.now()
        ).order_by('date')
    )
    lessons = forms.ModelMultipleChoiceField(
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label="Choose classes",
        queryset=Event.objects.filter(
            event_type__event_type="CL", date__gte=timezone.now()
        ).order_by('date')
    )
    students = forms.MultipleChoiceField(
        widget=StudentWidget(attrs={"class": "form-control"}),
        required=False,
        label="Choose students (search by first name, last name or username)"
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
