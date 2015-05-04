from django import forms
from django.forms.models import modelformset_factory, BaseModelFormSet

from booking.models import Event


class EventBaseFormSet(BaseModelFormSet):

    def add_fields(self, form, index):
        super(EventBaseFormSet, self).add_fields(form, index)

        if form.instance:
            form.fields['booking_open'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={
                    'class': "regular-checkbox",
                    'id': 'booking_open_{}'.format(index)
                }),
                initial=form.instance.booking_open,
                required=False
            )
            form.booking_open_id = 'booking_open_{}'.format(index)

            form.fields['payment_open'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={
                    'class': "regular-checkbox",
                    'id': 'payment_open_{}'.format(index)
                }),
                initial=form.instance.payment_open,
                required=False
            )
            form.payment_open_id = 'payment_open_{}'.format(index)

            form.fields['cost'] = forms.DecimalField(
                widget=forms.TextInput(attrs={
                    'type': 'text',
                    'class': 'form-control',
                    'aria-describedby': 'sizing-addon2',
                }),
                initial=form.instance.cost,
                required=False
            )
            form.fields['max_participants'] = forms.IntegerField(
                widget=forms.TextInput(attrs={
                    'type': 'text',
                    'class': 'form-control',
                    'aria-describedby': 'sizing-addon2',
                    'style': 'text-align: center;'
                }),
                initial=form.instance.max_participants,
                required=False
            )


EventFormSet = modelformset_factory(
    Event,
    fields=(
        'cost', 'max_participants',
        'booking_open', 'payment_open'
    ),
    formset=EventBaseFormSet,
    extra=0)