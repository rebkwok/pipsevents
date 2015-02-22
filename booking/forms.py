from django import forms
from booking.models import Booking, Event
from django.utils.translation import ugettext_lazy as _


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


