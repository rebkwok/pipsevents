from django import forms
from booking.models import Booking, Event
from django.utils.translation import ugettext_lazy as _


class SignupForm(forms.Form):
    first_name = forms.CharField(max_length=30, label='First name')
    last_name = forms.CharField(max_length=30, label='Last name')

    def signup(self, request, user):
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.save()


class BookingCreateForm(forms.ModelForm):

    class Meta:
        model = Booking
        fields = ['event', ]

class BookingUpdateForm(forms.ModelForm):

    class Meta:
        model = Booking
        fields = ('paid',)

        labels = {'paid': _('Confirm your payment')}
        help_texts = {'paid': _('Tick to confirm that you have made your payment.')}


