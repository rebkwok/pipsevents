from datetime import datetime

from django import forms

from accounts import validators as account_validators
from accounts.models import BOOL_CHOICES, OnlineDisclaimer, DISCLAIMER_TERMS


class SignupForm(forms.Form):
    first_name = forms.CharField(max_length=30, label='First name')
    last_name = forms.CharField(max_length=30, label='Last name')

    def signup(self, request, user):
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.save()


class DisclaimerForm(forms.ModelForm):

    medical_treatment_permission = forms.BooleanField(
        validators=[account_validators.validate_medical_treatment_permission],
        required=False,
        widget=forms.CheckboxInput(
            attrs={'class': 'regular-checkbox'}
        ),
        label='I give permission for myself to receive medical treatment in '
              'the event of an accident'
    )

    terms_accepted = forms.BooleanField(
        validators=[account_validators.validate_confirm],
        required=False,
        widget=forms.CheckboxInput(
            attrs={'class': 'regular-checkbox'}
        ),
        label='I accept the terms of the disclaimer'
    )

    age_over_18_confirmed = forms.BooleanField(
        validators=[account_validators.validate_age],
        required=False,
        widget=forms.CheckboxInput(
            attrs={'class': 'regular-checkbox'}
        ),
        label='I confirm that I am over the age of 18'
    )

    medical_conditions_details = forms.CharField(
        widget=forms.Textarea(
                attrs={'class': 'form-control', 'rows': 3}
            ),
        label="If yes, please give details",
        required=False
    )
    allergies_details = forms.CharField(
        widget=forms.Textarea(
                attrs={'class': 'form-control', 'rows': 3}
            ),
        label="If yes, please give details",
        required=False
    )
    joint_problems_details = forms.CharField(
        widget=forms.Textarea(
                attrs={'class': 'form-control', 'rows': 3}
            ),
        label="If yes, please give details",
        required=False
    )

    password = forms.CharField(
        widget=forms.PasswordInput(),
        label="Please re-enter your password to confirm submission of this form",
        required=True
    )

    def __init__(self, *args, **kwargs):
        self.disclaimer_terms = DISCLAIMER_TERMS
        super(DisclaimerForm, self).__init__(*args, **kwargs)
        
    class Meta:
        model = OnlineDisclaimer
        fields = (
            'name', 'dob', 'address', 'postcode', 'home_phone', 'mobile_phone',
            'emergency_contact1_name', 'emergency_contact1_relationship',
            'emergency_contact1_phone', 'emergency_contact2_name',
            'emergency_contact2_relationship', 'emergency_contact2_phone',
            'medical_conditions', 'medical_conditions_details',
            'joint_problems', 'joint_problems_details', 'allergies',
            'allergies_details', 'medical_treatment_permission',
            'terms_accepted', 'age_over_18_confirmed')

        widgets = {
            'name': forms.TextInput(
                attrs={'class': 'form-control'}
            ),
            'address': forms.TextInput(
                attrs={'class': 'form-control'}
            ),
            'dob': forms.DateInput(
                attrs={
                    'class': "form-control",
                    'id': 'dobdatepicker',
                    },
                format='%d %b %Y'
            ),
            'postcode': forms.TextInput(
                attrs={'class': 'form-control'}
            ),
            'home_phone': forms.TextInput(
                attrs={'class': 'form-control'}
            ),
            'mobile_phone': forms.TextInput(
                attrs={'class': 'form-control'}
            ),
            'emergency_contact1_name': forms.TextInput(
                attrs={'class': 'form-control'}
            ),
            'emergency_contact1_relationship': forms.TextInput(
                attrs={'class': 'form-control'}
            ),
            'emergency_contact1_phone': forms.TextInput(
                attrs={'class': 'form-control'}
            ),
            'emergency_contact2_name': forms.TextInput(
                attrs={'class': 'form-control'}
            ),
            'emergency_contact2_relationship': forms.TextInput(
                attrs={'class': 'form-control'}
            ),
            'emergency_contact2_phone': forms.TextInput(
                attrs={'class': 'form-control'}
            ),
            'medical_conditions': forms.RadioSelect(choices=BOOL_CHOICES),
            'joint_problems': forms.RadioSelect(choices=BOOL_CHOICES),
            'allergies': forms.RadioSelect(choices=BOOL_CHOICES),

        }

    def clean(self):
        if self.cleaned_data.get('medical_conditions', False) \
                and not self.cleaned_data['medical_conditions_details']:
            self.add_error(
                'medical_conditions_details', 
                'Please provide details of medical conditions'
            )

        if self.cleaned_data.get('joint_problems', False) \
                and not self.cleaned_data['joint_problems_details']:
            self.add_error(
                'joint_problems_details',
                'Please provide details of knee/back/shoulder/ankle/hip/neck '
                'problems'
            )

        if self.cleaned_data.get('allergies', False) \
                and not self.cleaned_data['allergies_details']:
            self.add_error(
                'allergies_details',
                'Please provide details of allergies'
            )

        if self.errors.get('dob'):
            del self.errors['dob']
        try:
            dob = datetime.strptime(self.data.get('dob'), '%d %b %Y').date()
            self.cleaned_data['dob'] = dob
        except ValueError:
            self.add_error(
                'dob', 'Invalid date format.  Select from '
                                    'the date picker or enter date in the '
                                    'format e.g. 08 Jun 1990')

        return super(DisclaimerForm, self).clean()
