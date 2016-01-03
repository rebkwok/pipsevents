from django import forms

from accounts import validators as account_validators
from accounts.models import Disclaimer


class SignupForm(forms.Form):
    first_name = forms.CharField(max_length=30, label='First name')
    last_name = forms.CharField(max_length=30, label='Last name')

    def signup(self, request, user):
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.save()


class DisclaimerForm(forms.ModelForm):

    terms_accepted = forms.BooleanField(
        validators=[account_validators.validate_confirm],
        required=False,
        widget=forms.CheckboxInput(
            attrs={'class': 'regular-checkbox'}
        )
    )

    class Meta:
        model = Disclaimer
        fields = ('terms_accepted',)

