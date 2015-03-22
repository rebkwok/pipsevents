from django import forms
from django.conf import settings
from datetime import date
from booking.models import Booking, Event
from django.utils.translation import ugettext_lazy as _
from django.forms import widgets


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


class DateSelectorWidget(widgets.MultiWidget):

    def __init__(self, attrs=None):


        # create choices for days, months, years
        days = [(day, day) for day in range(1, 32)]
        months = [(key, value) for key, value in MONTH_CHOICES.items()]
        years = [(year, year) for year in range(2015, 2021)]
        _widgets = (
            widgets.Select(attrs=attrs, choices=days),
            widgets.Select(attrs=attrs, choices=months),
            widgets.Select(attrs=attrs, choices=years),
        )
        super(DateSelectorWidget, self).__init__(_widgets, attrs)

    def decompress(self, value):
        if value:
            return [value.day, value.month, value.year]
        return [None, None, None]

    def format_output(self, rendered_widgets):
        return u''.join(rendered_widgets)

    def value_from_datadict(self, data, files, name):
        datelist = [
            widget.value_from_datadict(data, files, name + '_%s' % i)
            for i, widget in enumerate(self.widgets)]
        try:
            input_date = date(day=int(datelist[0]), month=int(datelist[1]),
                    year=int(datelist[2]))
        except ValueError:
            return ''
        else:
            return input_date

class CreateClassesForm(forms.Form):
    date = forms.DateField(
        label="Date", widget=DateSelectorWidget, required=False
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
    message = forms.CharField(widget=forms.Textarea, required=True)
