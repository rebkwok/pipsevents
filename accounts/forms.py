from datetime import datetime

from dateutil.relativedelta import relativedelta

from django import forms
from django.contrib.auth.models import Group
from django.utils import timezone

from accounts import validators as account_validators
from accounts.models import BOOL_CHOICES, OnlineDisclaimer, DISCLAIMER_TERMS, \
    OVER_18_TERMS, MEDICAL_TREATMENT_TERMS, DataPrivacyPolicy, \
    SignedDataPrivacy
from accounts.utils import has_expired_disclaimer
from activitylog.models import ActivityLog
from common.mailchimp_utils import update_mailchimp


class SignupForm(forms.Form):
    first_name = forms.CharField(max_length=30, label='First name')
    last_name = forms.CharField(max_length=30, label='Last name')

    def __init__(self, *args, **kwargs):
        super(SignupForm, self).__init__(*args, **kwargs)
        # get the current version here to make sure we always display and save
        # with the same version, even if it changed while the form was being
        # completed
        if DataPrivacyPolicy.current():
            self.data_privacy_policy = DataPrivacyPolicy.current()
            self.fields['data_privacy_content'] = forms.CharField(
                initial=self.data_privacy_policy.data_privacy_content,
                required=False
            )
            self.fields['cookie_content'] = forms.CharField(
                initial=self.data_privacy_policy.cookie_content,
                required=False
            )
            self.fields['data_privacy_confirmation'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={'class': "regular-checkbox"}),
                required=False,
                label='I confirm I have read and agree to the terms of the data ' \
                      'privacy policy'
            )
        self.fields['mailing_list'] = forms.CharField(
            widget=forms.RadioSelect(
                choices=(
                    ('yes', 'Yes, subscribe me'),
                    ('no', "No, I don't want to subscribe")
                )
            )
        )

    def clean_data_privacy_confirmation(self):
        dp = self.cleaned_data.get('data_privacy_confirmation')
        if not dp:
            self.add_error(
                'data_privacy_confirmation',
                'You must check this box to continue'
            )
        return

    def signup(self, request, user):
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.save()
        if hasattr(self, 'data_privacy_version'):
            SignedDataPrivacy.objects.create(
                user=user, version=self.data_privacy_policy.version,
                date_signed=timezone.now()
            )
        if self.cleaned_data.get('mailing_list') == 'yes':
            group, _ = Group.objects.get_or_create(name='subscribed')
            group.user_set.add(user)
            ActivityLog.objects.create(
                log='User {} {} ({}) has subscribed to the mailing list'.format(
                    user.first_name, user.last_name,
                    user.username
                )
            )
            update_mailchimp(user, 'subscribe')
            ActivityLog.objects.create(
                log='User {} {} ({}) has been subscribed to MailChimp'.format(
                    user.first_name, user.last_name,
                    user.username
                )
            )


class DisclaimerForm(forms.ModelForm):

    medical_treatment_permission = forms.BooleanField(
        validators=[account_validators.validate_medical_treatment_permission],
        required=False,
        widget=forms.CheckboxInput(
            attrs={'class': 'regular-checkbox'}
        ),
        label='Please tick to confirm'
    )

    terms_accepted = forms.BooleanField(
        validators=[account_validators.validate_confirm],
        required=False,
        widget=forms.CheckboxInput(
            attrs={'class': 'regular-checkbox'}
        ),
        label='Please tick to accept terms'
    )

    age_over_18_confirmed = forms.BooleanField(
        validators=[account_validators.validate_age],
        required=False,
        widget=forms.CheckboxInput(
            attrs={'class': 'regular-checkbox'}
        ),
        label='Please tick to confirm'
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
        label="Please enter your password to submit your data.<br/>"
              "By submitting this form, you confirm that "
              "the information you have provided is complete and accurate.",
        required=True,
    )

    def __init__(self, *args, **kwargs):

        user = kwargs.pop('user')
        super(DisclaimerForm, self).__init__(*args, **kwargs)
        # the agreed-to terms are read-only fields.  For a new disclaimer, we
        # show the default terms from the model.  If we're updating an existing
        # disclaimer, we show the terms that are already on the instance (i.e.
        # the terms the user agreed to before.  THESE WILL NEVER CHANGE!  If the
        # default terms are updated, existing disclaimers will continue to show
        # the old terms that the user agreed to when they first completed the
        # disclaimer

        if self.instance.id:
            # in the DisclaimerForm, these fields are autopoulated based
            self.medical_treatment_terms = self.instance.medical_treatment_terms
            self.disclaimer_terms = self.instance.disclaimer_terms
            self.age_over_18_confirmed = self.instance.age_over_18_confirmed
        else:
            self.disclaimer_terms = DISCLAIMER_TERMS
            self.over_18_terms = OVER_18_TERMS
            self.medical_treatment_terms = MEDICAL_TREATMENT_TERMS

            if has_expired_disclaimer(user):
                last_disclaimer = OnlineDisclaimer.objects.filter(user=user)\
                    .last()
                # set initial on all fields except ^^^ and terms_accepted
                # to data from last disclaimer
                for field_name in self.fields:
                    if field_name not in [
                        'medical_treatment_terms', 'over_18_terms',
                        'disclaimer_terms', 'terms_accepted',
                        'password'
                    ]:
                        last_value = getattr(last_disclaimer, field_name)
                        if field_name == 'dob':
                            last_value = last_value.strftime('%d %b %Y')
                        self.fields[field_name].initial = last_value

        self.fields['home_phone'].required = False

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
        dob = self.data.get('dob', None)
        if dob and self.errors.get('dob'):
            del self.errors['dob']
        if dob:
            try:
                dob = datetime.strptime(dob, '%d %b %Y').date()
                self.cleaned_data['dob'] = dob
            except ValueError:
                self.add_error(
                    'dob', 'Invalid date format.  Select from '
                                        'the date picker or enter date in the '
                                        'format e.g. 08 Jun 1990')
        if not self.errors.get('dob'):
            yearsago = datetime.today().date() - relativedelta(years=18)
            if dob > yearsago:
                self.add_error(
                    'dob', 'You must be over 18 years in order to register')
        return super(DisclaimerForm, self).clean()


class DataPrivacyAgreementForm(forms.Form):

    confirm = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={'class': "regular-checkbox"}),
        required=False,
        label='I confirm I have read and agree to the terms of the data ' \
              'privacy and cookie policy'
    )

    mailing_list = forms.CharField(
        widget=forms.RadioSelect(
            choices=(
                ('yes', 'Yes, subscribe me'),
                ('no', "No, I don't want to subscribe")
            )
        )
    )

    def __init__(self, *args, **kwargs):
        self.next_url = kwargs.pop('next_url')
        user = kwargs.pop('user')
        super(DataPrivacyAgreementForm, self).__init__(*args, **kwargs)
        self.data_privacy_policy = DataPrivacyPolicy.current()
        if user.subscribed:
            self.fields['mailing_list'].initial = True

    def clean_confirm(self):
        confirm = self.cleaned_data.get('confirm')
        if not confirm:
            self.add_error('confirm', 'You must check this box to continue')
        return
