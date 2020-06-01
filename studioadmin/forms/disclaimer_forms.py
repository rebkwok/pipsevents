# -*- coding: utf-8 -*-

from django import forms

from accounts.admin import DisclaimerContentAdminForm
from accounts.forms import DisclaimerForm
from accounts.models import DisclaimerContent


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
    hide_past = forms.BooleanField(
        label="Hide disclaimers for past events",
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={'onclick': 'this.form.submit();', 'class': "regular-checkbox",})
    )


class StudioadminDisclaimerContentForm(DisclaimerContentAdminForm):

    class Meta:
        fields = ('medical_treatment_terms', 'disclaimer_terms', 'over_18_statement', 'version' )
        model = DisclaimerContent
        widgets = {
            'disclaimer_terms': forms.Textarea(
                attrs={'class': 'form-control', 'rows': 20},
            ),
            'medical_treatment_terms': forms.Textarea(
                attrs={'class': "form-control", 'rows': 2}
            ),
            'over_18_statement': forms.Textarea(
                attrs={'class': "form-control", 'rows': 1}
            ),
            'version': forms.TextInput(
                attrs={'class': "form-control"}
            ),
        }
        help_texts = {
            "disclaimer_terms": "Plain text only; use blank lines to separate paragraphs.",
            "medical_treatment_terms": "Plain text only; use blank lines to separate paragraphs.",
            "version": "Leave blank to increment to the next major version (i.e. if the current published version " \
                       "is version 1.1, the next major version will be 2.0). If you are only making minor (e.g. typo) " \
                       "changes, it's recommended to increment to a minor version (e.g. version 1.1).  " \
                       "In this case you will need to manually enter the version you require."
        }