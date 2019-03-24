# -*- coding: utf-8 -*-

from django import forms

from accounts.forms import DisclaimerForm


class StudioadminDisclaimerForm(DisclaimerForm):

    def __init__(self, *args, **kwargs):
        super(StudioadminDisclaimerForm, self).__init__(*args, **kwargs)
        self.fields['password'].label = "Please have the user re-enter their " \
                                       "password to confirm acceptance of the " \
                                       "changes to their data."


class DisclaimerUserListSearchForm(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(
            attrs={
                'placeholder': 'Search first and last name',
                'style': 'width: 250px;'
            }
        ),
        required=False
    )
    search_date = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={
                'id': "logdatepicker",
                'placeholder': "Search by event date",
                'style': 'text-align: center'
            },
            format='%d-%m-%y',
        ),
        required=False
    )
