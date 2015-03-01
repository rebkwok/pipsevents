from django import forms
from booking.models import Booking, Event
from django.utils.translation import ugettext_lazy as _


class BookingCreateForm(forms.ModelForm):

    use_active_block = forms.BooleanField(
        label="Use my block", help_text="You have an active block booking; "
                                        "would you like to use your block for "
                                        "this booking?",
        required=False)

    class Meta:
        model = Booking
        fields = ['use_active_block', 'event', ]

class BookingUpdateForm(forms.ModelForm):

    use_active_block = forms.BooleanField(
        label="Use my block", help_text="Tick to use your active block booking",
        required=False)

    class Meta:
        model = Booking
        fields = ('paid', 'use_active_block')

        labels = {'paid': _('Confirm your payment'),}
        help_texts = {
            'paid': _('Tick to confirm that you have made your payment.')
        }


