# -*- coding: utf-8 -*-

from django import forms


class ActivityLogSearchForm(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(
            attrs={
                'placeholder': 'Search log text'
            }
        )
    )
    search_date = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={
                'id': "logdatepicker",
                'placeholder': "Search by log date",
                'style': 'text-align: center'
            },
            format='%d-%m-%y',
        ),
    )
    hide_empty_cronjobs = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={
            'class': "regular-checkbox",
            'id': 'hide_empty_cronjobs_id'
        }),
        initial='on'
    )
