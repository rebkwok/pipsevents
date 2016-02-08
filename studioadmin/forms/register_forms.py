# -*- coding: utf-8 -*-
from datetime import datetime, date

from django import forms
from django.contrib.auth.models import User
from django.forms.models import inlineformset_factory, BaseInlineFormSet

from booking.models import Block, Booking, Event
from payments.models import PaypalBookingTransaction

from studioadmin.forms.user_forms import UserBlockModelChoiceField, \
    UserModelChoiceField


class BookingRegisterInlineFormSet(BaseInlineFormSet):

    def __init__(self, *args, **kwargs):

        super(BookingRegisterInlineFormSet, self).__init__(*args, **kwargs)
        if self.instance.max_participants:
            self.extra = self.instance.spaces_left()
        elif self.instance.bookings.count() < 15:
            open_bookings = [
                bk for bk in self.instance.bookings.all() if bk.status == 'OPEN'
                ]
            self.extra = 15 - len(open_bookings)
        else:
            self.extra = 2


    def add_fields(self, form, index):
        super(BookingRegisterInlineFormSet, self).add_fields(form, index)

        form.index = index + 1

        if form.instance.id:
            user = form.instance.user
            event_type = form.instance.event.event_type
            available_block = [
                block for block in Block.objects.filter(user=user) if
                block.active_block()
                and block.block_type.event_type == event_type
            ]
            if form.instance.block:
                form.available_block = form.instance.block
            else:
                form.available_block = form.instance.block or (
                    available_block[0] if available_block else None
                )
                available_block_ids = [block.id for block in available_block
                                       ]
                form.fields['block'] = UserBlockModelChoiceField(
                    queryset=Block.objects.filter(id__in=available_block_ids),
                    widget=forms.Select(
                        attrs={'class': 'form-control input-xs studioadmin-list'}),
                    required=False,
                    empty_label="Active block not used"
                )

            form.fields['user'] = forms.ModelChoiceField(
                queryset=User.objects.all(),
                initial=user,
                widget=forms.Select(attrs={'class': 'hide'})
            )

            # add field for if booking has been paid by paypal (don't allow
            # changing paid in register for paypal payments
            pbts = PaypalBookingTransaction.objects.filter(
                booking=form.instance
            )
            if pbts and pbts[0].transaction_id:
                form.paid_by_paypal = True

        else:
            booked_user_ids = [
                bk.user.id for bk in self.instance.bookings.all()
                if bk.status == 'OPEN'
                ]

            form.fields['user'] = UserModelChoiceField(
                queryset=User.objects.exclude(id__in=booked_user_ids).order_by('first_name'),
                widget=forms.Select(attrs={'class': 'form-control input-xs studioadmin-list'})
            )

        form.fields['paid'] = forms.BooleanField(
            widget=forms.CheckboxInput(attrs={
                'class': "regular-checkbox",
                'id': 'checkbox_paid_{}'.format(index)
            }),
            required=False
        )
        form.checkbox_paid_id = 'checkbox_paid_{}'.format(index)

        form.fields['deposit_paid'] = forms.BooleanField(
            widget=forms.CheckboxInput(attrs={
                'class': "regular-checkbox",
                'id': 'checkbox_deposit_paid_{}'.format(index)
            }),
            required=False
        )
        form.checkbox_deposit_paid_id = 'checkbox_deposit_paid_{}'.format(index)

        form.fields['attended'] = forms.BooleanField(
            widget=forms.CheckboxInput(attrs={
                'class': "regular-checkbox",
                'id': 'checkbox_attended_{}'.format(index)
            }),
            initial=False,
            required=False
        )
        form.checkbox_attended_id = 'checkbox_attended_{}'.format(index)

    def clean(self):
        if not self.is_valid():
            for form in self.forms:
                if form.errors:
                    if form.errors == {
                        '__all__': [
                            'Booking with this User and Event already exists.'
                        ]
                    }:
                        del form.errors['__all__']


SimpleBookingRegisterFormSet = inlineformset_factory(
    Event,
    Booking,
    fields=('attended', 'user', 'deposit_paid', 'paid', 'block'),
    can_delete=False,
    formset=BookingRegisterInlineFormSet,
)


class RegisterDayForm(forms.Form):

    def __init__(self, *args, **kwargs):
        if 'events' in kwargs:
            self.events = kwargs.pop('events')
        else:
            self.events = None
        super(RegisterDayForm, self).__init__(*args, **kwargs)

        self.fields['register_date'] = forms.DateField(
            label="Date",
            widget=forms.DateInput(
                attrs={
                    'class': "form-control",
                    'id': 'datepicker_registerdate',
                    'onchange': "this.form.submit()"},
                format='%a %d %b %Y'
            ),
            required=True,
            initial=date.today()
        )

        self.fields['exclude_ext_instructor'] = forms.BooleanField(
            label="Exclude classes by external instructors:",
            widget=forms.CheckboxInput(
                attrs={
                    'class': 'regular-checkbox select-checkbox',
                    'id': 'ext_instructor_cbox',
                    'style': 'align-text: top;',
                    'onchange': "this.form.submit()"
                }
            ),
            initial=True,
            required=False
        )

        self.fields['register_format'] = forms.ChoiceField(
            label="Register format",
            choices=[('full', 'Full register'), ('namesonly', 'Names only')],
            widget=forms.RadioSelect,
            initial='full',
            required=False
        )

        if self.events:
            if self.initial.get('exclude_ext_instructor'):
                initial = [event.id for event in self.events
                           if not event.external_instructor]
            else:
                initial = [event.id for event in self.events]
            event_choices = tuple([(event.id, event) for event in self.events])
            self.fields['select_events'] = forms.MultipleChoiceField(
                label="Select registers to print:",
                widget=forms.CheckboxSelectMultiple,
                choices=event_choices,
                initial=initial
            )
        else:
            self.fields['no_events'] = forms.CharField(
                label="",
                widget=forms.TextInput(
                    attrs={
                           'placeholder': "No classes/workshops on this date",
                           'style': 'width: 200px; border: none;',
                           'class': 'disabled studioadmin-help'
                    }
                ),
                required=False
            )

    def clean(self):
        super(RegisterDayForm, self).clean()
        cleaned_data = self.cleaned_data

        if self.data.get('select_events'):
            selected_events = self.data.getlist('select_events')
            if selected_events:
                cleaned_data['select_events'] = [int(ev) for ev in selected_events]

        register_date = self.data.get('register_date')
        if register_date:
            if self.errors.get('register_date'):
                del self.errors['register_date']
            try:
                register_date = datetime.strptime(register_date, '%a %d %b %Y').date()
                cleaned_data['register_date'] = register_date
            except ValueError:
                self.add_error(
                    'register_date', 'Invalid date format.  Select from '
                                        'the date picker or enter date in the '
                                        'format e.g. Mon 08 Jun 2015')

        return cleaned_data
