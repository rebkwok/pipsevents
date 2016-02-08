# -*- coding: utf-8 -*-

from django import forms

from booking.models import Booking


class ConfirmPaymentForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ('paid', 'payment_confirmed')
        widgets = {
            'paid': forms.CheckboxInput(),
            'payment_confirmed': forms.CheckboxInput()
        }
