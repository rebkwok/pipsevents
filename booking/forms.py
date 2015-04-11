from datetime import date
from django import forms
from django.conf import settings
from django.utils.translation import ugettext_lazy as _


from booking.models import Booking, Event, Block, BlockType
from booking.widgets import DateSelectorWidget


MONTH_CHOICES = {
            1: 'January',
            2: 'February',
            3: 'March',
            4: 'April',
            5: 'May',
            6: 'June',
            7: 'July',
            8: 'August',
            9: 'September',
            10: 'October',
            11: 'November',
            12: 'December',
        }


class BookingCreateForm(forms.ModelForm):

    class Meta:
        model = Booking
        fields = ['event', ]


class BlockCreateForm(forms.ModelForm):

    class Meta:
        model = Block
        fields = ('block_type', )

class CreateClassesForm(forms.Form):
    date = forms.DateField(
        label="Date", widget=DateSelectorWidget, required=False, initial=date.today()
    )

    def clean_date(self):
        if not self.cleaned_data['date']:
            day = self.data.get('date_0')
            month = MONTH_CHOICES.get(int(self.data.get('date_1')))
            year = self.data.get('date_2')
            raise forms.ValidationError(_('Invalid date {} {} {}'.format(day, month, year)))
        return self.cleaned_data['date']


class EmailUsersForm(forms.Form):
    subject = forms.CharField(max_length=255, required=True)
    from_address = forms.EmailField(max_length=255,
                                    initial=settings.DEFAULT_FROM_EMAIL,
                                    required=True)
    cc = forms.BooleanField(label="Send a copy to this address", initial=True)
    message = forms.CharField(widget=forms.Textarea, required=True)


class ConfirmPaymentForm(forms.ModelForm):

    class Meta:
        model = Booking
        fields = ('paid', 'payment_confirmed')