# -*- coding: utf-8 -*-
import pytz
from datetime import datetime, timedelta, date
import time

from django import forms
from django.conf import settings
from django.contrib.auth.models import User
from django.forms.models import modelformset_factory, BaseModelFormSet, \
    inlineformset_factory, BaseInlineFormSet
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

from ckeditor.widgets import CKEditorWidget

from booking.models import Block, Booking, Event, EventType, BlockType, \
    TicketedEvent, TicketBooking
from timetable.models import Session
from payments.models import PaypalBookingTransaction, \
    PaypalTicketBookingTransaction


class EventBaseFormSet(BaseModelFormSet):

    def add_fields(self, form, index):
        super(EventBaseFormSet, self).add_fields(form, index)

        if form.instance:
            form.fields['booking_open'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={
                    'class': "regular-checkbox studioadmin-list",
                    'id': 'booking_open_{}'.format(index)
                }),
                required=False
            )
            form.booking_open_id = 'booking_open_{}'.format(index)

            form.fields['payment_open'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={
                    'class': "regular-checkbox studioadmin-list",
                    'id': 'payment_open_{}'.format(index)
                }),
                required=False
            )
            form.payment_open_id = 'payment_open_{}'.format(index)

            form.fields['advance_payment_required'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={
                    'class': "regular-checkbox studioadmin-list",
                    'id': 'advance_payment_required_{}'.format(index)
                }),
                required=False
            )
            form.advance_payment_required_id = 'advance_payment_required_{}'.format(index)

            if form.instance.bookings.count() > 0:
                form.cannot_delete = True
            else:
                form.fields['DELETE'] = forms.BooleanField(
                    widget=forms.CheckboxInput(attrs={
                        'class': 'delete-checkbox studioadmin-list',
                        'id': 'DELETE_{}'.format(index)
                    }),
                    required=False
                )
            form.DELETE_id = 'DELETE_{}'.format(index)

EventFormSet = modelformset_factory(
    Event,
    fields=(
        'booking_open', 'payment_open', 'advance_payment_required'
    ),
    formset=EventBaseFormSet,
    extra=0,
    can_delete=True
)


day = 24
week = day * 7

cancel_choices = (
    (day * 0, '0 hours'),
    (day * 1, '24 hours'),
    (day * 2, '2 days'),
    (day * 3, '3 days'),
    (day * 4, '4 days'),
    (day * 5, '5 days'),
    (day * 6, '6 days'),
    (week, '1 week'),
    (week * 2, '2 weeks'),
    (week * 3, '3 weeks'),
    (week * 4, '4 weeks'),
    (week * 5, '5 weeks'),
    (week * 6, '6 weeks'),
)

dateoptions = {
        'format': 'dd/mm/yyyy hh:ii',
        'autoclose': True,
    }


class EventAdminForm(forms.ModelForm):

    required_css_class = 'form-error'

    cost = forms.DecimalField(
        widget=forms.TextInput(attrs={
            'type': 'text',
            'class': 'form-control',
            'aria-describedby': 'sizing-addon2',
        }),
        required=False
    )

    def __init__(self, *args, **kwargs):
        ev_type = kwargs.pop('ev_type')
        super(EventAdminForm, self).__init__(*args, **kwargs)

        if ev_type == 'EV':
            ev_type_qset = EventType.objects.filter(event_type='EV')
        else:
            ev_type_qset = EventType.objects.exclude(event_type='EV')

        self.fields['event_type'] = forms.ModelChoiceField(
            widget=forms.Select(attrs={'class': "form-control"}),
            queryset=ev_type_qset,
        )
        ph_type = "event" if ev_type == 'EV' else 'class'
        ex_name = "Workshop" if ev_type == 'EV' else "Pole Level 1"
        self.fields['name'] = forms.CharField(
            widget=forms.TextInput(
                attrs={
                    'class': "form-control",
                    'placeholder': 'Name of {} e.g. {}'.format(ph_type, ex_name)
                }
            )
        )

        if self.instance.id:
            ev_type_str = 'class' if ev_type == 'CL' else 'event'

            if not self.instance.cancelled:
                self.fields['cancelled'].label = "Cancelled: No"
                self.fields['cancelled'].\
                    help_text = 'To cancel, use the Cancel button on the {} ' \
                                'list page'.format(ev_type_str)
                self.fields['cancelled'].widget.attrs.update(
                    {'disabled': 'disabled', 'class': "hide"})
            else:
                self.fields['cancelled'].\
                    help_text = 'Untick to reopen {}; note that this does ' \
                                'not change any other attributes and ' \
                                'does not reopen previously cancelled ' \
                                'bookings.  {} will be reopened with both ' \
                                'booking and payment CLOSED'.format(
                    ev_type_str, ev_type_str.title()
                )

    def clean(self):
        super(EventAdminForm, self).clean()
        cleaned_data = self.cleaned_data
        is_new = False if self.instance else True

        date = self.data.get('date')
        if date:
            if self.errors.get('date'):
                del self.errors['date']
            try:
                date = datetime.strptime(self.data['date'], '%d %b %Y %H:%M')
                uk = pytz.timezone('Europe/London')
                cleaned_data['date'] = uk.localize(date).astimezone(pytz.utc)
            except ValueError:
                self.add_error('date', 'Invalid date format.  Select from the '
                                       'date picker or enter date and time in the '
                                       'format dd Mmm YYYY HH:MM')

        payment_due_date = self.data.get('payment_due_date')
        if payment_due_date:
            if self.errors.get('payment_due_date'):
                del self.errors['payment_due_date']
            try:
                payment_due_date = datetime.strptime(payment_due_date, '%d %b %Y')
                if payment_due_date < datetime.strptime(
                    self.data['date'],
                    '%d %b %Y %H:%M') - timedelta(
                        hours=cleaned_data.get('cancellation_period')
                    ):

                    cleaned_data['payment_due_date'] = payment_due_date
                else:
                    self.add_error('payment_due_date', 'Payment due date must '
                                                       'be before cancellation'
                                                       ' period starts')
                cleaned_data['payment_due_date'] = payment_due_date
            except ValueError:
                self.add_error(
                    'payment_due_date', 'Invalid date format.  Select from '
                                        'the date picker or enter date in the '
                                        'format dd Mmm YYYY')

        if cleaned_data.get('advance_payment_required'):
            if not (cleaned_data.get('payment_due_date') or
                        cleaned_data.get('payment_time_allowed') or
                            cleaned_data.get('cancellation_period') > 0
                    ):
                self.add_error(
                    'advance_payment_required',
                    'Please provide a payment due date, payment '
                    'time allowed or cancellation period'
                    )
            elif cleaned_data.get('payment_due_date') and \
                    cleaned_data.get('payment_time_allowed'):
                self.add_error(
                    'payment_due_date',
                    'Please provide payment due date OR payment time '
                    'allowed (but not both)'
                )
                self.add_error(
                    'payment_time_allowed',
                    'Please provide payment due date OR payment time '
                    'allowed (but not both)'
                )
        else:
            if cleaned_data.get('payment_due_date'):
                self.add_error(
                    'payment_due_date',
                    'To specify a payment due date, please also tick '
                    '"advance payment required"'
                    )
            if cleaned_data.get('payment_time_allowed'):
                self.add_error(
                    'payment_time_allowed',
                    'To specify payment time allowed, please also '
                    'tick "advance payment required"'
                    )

        if not cleaned_data.get('cost'):
            cost_errors = []
            if cleaned_data.get('advance_payment_required'):
                cost_errors.append('advance payment required')
            if cleaned_data.get('payment_due_date'):
                cost_errors.append('payment due date')
            if cleaned_data.get('payment_time_allowed'):
                cost_errors.append('payment time allowed')
            if cost_errors:
                self.add_error(
                    'cost',
                    'The following fields require a cost greater than '
                    '£0: {}'.format(', '.join(cost_errors))
                )

        if not cleaned_data.get('allow_booking_cancellation'):
            if not cleaned_data.get('cost'):
                self.add_error(
                    'allow_booking_cancellation',
                    'Booking cancellation should be allowed for events/classes '
                    'with no associated cost'
                )
            elif not cleaned_data.get('advance_payment_required'):
                self.add_error(
                    'allow_booking_cancellation',
                    'Advance payment must be required in order to make '
                    'booking cancellation disallowed (i.e. non-refundable)'
                )

        return cleaned_data

    class Meta:
        model = Event
        fields = (
            'name', 'event_type', 'date', 'description', 'location',
            'max_participants', 'contact_person', 'contact_email', 'cost',
            'external_instructor',
            'booking_open', 'payment_open', 'advance_payment_required',
            'payment_info',
            'payment_due_date', 'payment_time_allowed', 'cancellation_period',
            'allow_booking_cancellation',
            'email_studio_when_booked', 'cancelled',
        )
        widgets = {
            'description': CKEditorWidget(
                attrs={'class': 'form-control container-fluid'},
                config_name='studioadmin',
            ),
            'payment_info': CKEditorWidget(
                attrs={'class': 'form-control container-fluid'},
                config_name='studioadmin_min',
            ),
            'location': forms.TextInput(
                attrs={'class': "form-control"}
            ),
            'max_participants': forms.TextInput(
                attrs={'class': "form-control"}
            ),
            'contact_person': forms.TextInput(
                attrs={'class': "form-control"}
            ),
            'contact_email': forms.EmailInput(
                attrs={'class': "form-control"}
            ),
            'payment_due_date': forms.DateInput(
                attrs={
                    'class': "form-control",
                    'id': "datepicker",
                },
                format='%d %b %Y'
            ),
            'payment_time_allowed': forms.TextInput(
                attrs={'class': "form-control"}
            ),
            'date': forms.DateTimeInput(
                attrs={
                    'class': "form-control",
                    'id': "datetimepicker",
                },
                format='%d %b %Y %H:%M'
            ),
            'cancellation_period': forms.Select(
                choices=cancel_choices,
                attrs={
                    'class': "form-control",
                    }
            ),
            'booking_open': forms.CheckboxInput(
                attrs={
                    'class': "form-control regular-checkbox",
                    'id': 'booking_open_id',
                    }
            ),
            'payment_open': forms.CheckboxInput(
                attrs={
                    'class': "form-control regular-checkbox",
                    'id': 'payment_open_id',
                    },
            ),
            'advance_payment_required': forms.CheckboxInput(
                attrs={
                    'class': "form-control regular-checkbox",
                    'id': 'advance_payment_required_id',
                    },
            ),
            'external_instructor': forms.CheckboxInput(
                attrs={
                    'class': "form-control regular-checkbox",
                    'id': 'ext_instructor_id',
                    },
            ),
            'email_studio_when_booked': forms.CheckboxInput(
                attrs={
                    'class': "form-control regular-checkbox",
                    'id': 'email_studio_id',
                    },
            ),
            'cancelled': forms.CheckboxInput(
                attrs={
                    'class': "form-control regular-checkbox",
                    'id': 'cancelled_id',
                    }
            ),
            'allow_booking_cancellation': forms.CheckboxInput(
                attrs={
                    'class': "form-control regular-checkbox",
                    'id': 'allow_booking_cancellation_id',
                    }
            ),
            }
        help_texts = {
            'payment_open': _('Only applicable if the cost is greater than £0'),
            'payment_due_date': _('Only use this field if the cost is greater '
                                  'than £0.  If a payment due date is set, '
                                  'advance payment will always be required'),
            'external_instructor':_('Tick for classes taught by external '
                                    'instructors. These will not be bookable '
                                    'via the booking site.  Include '
                                    'booking/payment details in the payment '
                                    'information field.'),
            'email_studio_when_booked': _('Tick if you want the studio to '
                                          'receive email notifications when a '
                                          'booking is made'),
            'advance_payment_required': _('If this checkbox is not ticked, '
                                          'unpaid bookings will remain '
                                          'active after the cancellation period '
                                          'and will not be '
                                          'automatically cancelled'),
            'cancellation_period': _(
                'Set the time prior to class/event after which cancellation '
                'is NOT allowed.  If advance payment is required, unpaid '
                'bookings will be cancelled after this time'
            ),
            'allow_booking_cancellation': _(
                'Untick to make class/event non-cancellable by user (and '
                'payment non-refundable'
            )
        }


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


class StatusFilter(forms.Form):

    status_choice = forms.ChoiceField(
        widget=forms.Select,
        choices=(('OPEN', 'Open bookings only'),
                 ('CANCELLED', 'Cancelled Bookings only'),
                 ('ALL', 'All'),),
    )


class BookingStatusFilter(forms.Form):

    booking_status = forms.ChoiceField(
        widget=forms.Select,
        choices=(
            ('future', 'Upcoming bookings'),
            ('past', 'Past bookings'),
        ),
    )


class ConfirmPaymentForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ('paid', 'payment_confirmed')
        widgets = {
            'paid': forms.CheckboxInput(),
            'payment_confirmed': forms.CheckboxInput()
        }


DAY_CHOICES = dict(Session.DAY_CHOICES)


class SessionBaseFormSet(BaseModelFormSet):

    def add_fields(self, form, index):
        super(SessionBaseFormSet, self).add_fields(form, index)

        if form.instance:
            form.formatted_day = DAY_CHOICES[form.instance.day]

            form.fields['booking_open'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={
                    'class': "regular-checkbox studioadmin-list",
                    'id': 'booking_open_{}'.format(index)
                }),
                required=False
            )
            form.booking_open_id = 'booking_open_{}'.format(index)

            form.fields['payment_open'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={
                    'class': "regular-checkbox studioadmin-list",
                    'id': 'payment_open_{}'.format(index)
                }),
                initial=form.instance.payment_open,
                required=False
            )
            form.payment_open_id = 'payment_open_{}'.format(index)

            form.fields['advance_payment_required'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={
                    'class': "regular-checkbox studioadmin-list",
                    'id': 'advance_payment_required_{}'.format(index)
                }),
                required=False
            )
            form.advance_payment_required_id = 'advance_payment_required_{}'.format(index)

            form.fields['DELETE'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={
                    'class': 'delete-checkbox studioadmin-list',
                    'id': 'DELETE_{}'.format(index)
                }),
                required=False
            )
            form.DELETE_id = 'DELETE_{}'.format(index)

TimetableSessionFormSet = modelformset_factory(
    Session,
    fields=(
        'booking_open',
        'payment_open', 'advance_payment_required'
    ),
    formset=SessionBaseFormSet,
    extra=0,
    can_delete=True)


class SessionAdminForm(forms.ModelForm):

    cost = forms.DecimalField(
        widget=forms.TextInput(
            attrs={
                'type': 'text',
                'class': 'form-control',
                'aria-describedby': 'sizing-addon2',
            },
        ),
        initial=7,
        required=False
    )

    def __init__(self, *args, **kwargs):
        super(SessionAdminForm, self).__init__(*args, **kwargs)
        self.fields['event_type'] = forms.ModelChoiceField(
            widget=forms.Select(attrs={'class': "form-control"}),
            queryset=EventType.objects.exclude(event_type="EV"),
        )

    def clean(self):
        super(SessionAdminForm, self).clean()
        cleaned_data = self.cleaned_data

        time = self.data.get('time')
        if time:
            if self.errors.get('time'):
                del self.errors['time']
            try:
                time = datetime.strptime(self.data['time'], '%H:%M').time()
                cleaned_data['time'] = time
            except ValueError:
                self.add_error('time', 'Invalid time format.  Select from the '
                                       'time picker or enter date and time in the '
                                       '24-hour format HH:MM')

        if not cleaned_data.get('allow_booking_cancellation'):
            if not cleaned_data.get('cost'):
                self.add_error(
                    'allow_booking_cancellation',
                    'Booking cancellation should be allowed for events/classes '
                    'with no associated cost'
                )
            elif not cleaned_data.get('advance_payment_required'):
                self.add_error(
                    'allow_booking_cancellation',
                    'Advance payment must be required in order to make '
                    'booking cancellation disallowed (i.e. non-refundable)'
                )

        return cleaned_data

    class Meta:
        model = Session
        fields = (
            'name', 'event_type', 'day', 'time', 'description', 'location',
            'max_participants', 'contact_person', 'contact_email', 'cost',
            'external_instructor',
            'booking_open', 'payment_open', 'advance_payment_required',
            'payment_info', 'payment_time_allowed', 'cancellation_period',
            'allow_booking_cancellation', 'email_studio_when_booked'
        )
        widgets = {
            'description': CKEditorWidget(
                attrs={'class': 'form-control container-fluid'},
                config_name='studioadmin',
            ),
            'payment_info': CKEditorWidget(
                attrs={'class': 'form-control container-fluid'},
                config_name='studioadmin_min',
            ),
            'name': forms.TextInput(
                attrs={'class': "form-control",
                       'placeholder': 'Name of session e.g. Pole Level 1'},
            ),
            'location': forms.TextInput(
                attrs={'class': "form-control"}
            ),
            'max_participants': forms.TextInput(
                attrs={'class': "form-control"}
            ),
            'contact_person': forms.TextInput(
                attrs={'class': "form-control"}
            ),
            'contact_email': forms.EmailInput(
                attrs={'class': "form-control"}
            ),
            'day': forms.Select(
                choices=Session.DAY_CHOICES,
                attrs={'class': "form-control"}
            ),
            'time': forms.TimeInput(
                attrs={'class': 'form-control',
                       'id': 'timepicker'},
                format="%H:%M"
            ),
            'cancellation_period': forms.Select(
                choices=cancel_choices,
                attrs={
                    'class': "form-control",
                    }
            ),
            'booking_open': forms.CheckboxInput(
                attrs={
                    'class': "form-control regular-checkbox",
                    'id': 'booking_open_id',
                    }
            ),
            'payment_open': forms.CheckboxInput(
                attrs={
                    'class': "form-control regular-checkbox",
                    'id': 'payment_open_id',
                    }
            ),
            'advance_payment_required': forms.CheckboxInput(
                attrs={
                    'class': "form-control regular-checkbox",
                    'id': 'advance_payment_required_id',
                    }
            ),
            'external_instructor': forms.CheckboxInput(
                attrs={
                    'class': "form-control regular-checkbox",
                    'id': 'ext_instructor_id',
                    },
            ),
            'allow_booking_cancellation': forms.CheckboxInput(
                attrs={
                    'class': "form-control regular-checkbox",
                    'id': 'allow_booking_cancellation_id',
                    }
            ),
            'email_studio_when_booked': forms.CheckboxInput(
                attrs={
                    'class': "form-control regular-checkbox",
                    'id': 'email_studio_when_booked_id',
                    }
            ),
            }

        help_texts = {
            'payment_open': _('Only applicable if the cost is greater than £0'),
            'external_instructor':_('Tick for classes taught by external '
                            'instructors. These will not be bookable '
                            'via the booking site.  Include '
                            'booking/payment details in the payment '
                            'information field.'),
            'advance_payment_required': _('If this checkbox is not ticked, '
                                          'unpaid bookings will remain '
                                          'active after the cancellation period '
                                          'and will not be '
                                          'automatically cancelled'),
            'cancellation_period': _(
                'Set the time prior to class/event after which cancellation '
                'is NOT allowed.  If advance payment is required, unpaid '
                'bookings will be cancelled after this time'
            ),
            'allow_booking_cancellation': _(
                'Untick to make class/event non-cancellable by user (and '
                'payment non-refundable'
            )

        }


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


class UploadTimetableForm(forms.Form):

    def __init__(self, *args, **kwargs):
        super(UploadTimetableForm, self).__init__(*args, **kwargs)
        self.fields['sessions'] = forms.ModelMultipleChoiceField(
            widget=forms.CheckboxSelectMultiple(
                attrs={'class': 'select-checkbox'}
            ),
            label="Choose sessions to upload",
            queryset=Session.objects.all().order_by('day', 'time'),
            initial=[session.pk for session in Session.objects.all()],
            required=True
        )

    start_date = forms.DateField(
        label="Start Date",
        widget=forms.DateInput(
            attrs={
                'class': "form-control",
                'id': 'datepicker_startdate'},
            format='%a %d %b %Y'
        ),
        required=True,
        initial=date.today()
    )

    end_date = forms.DateField(
        label="End Date",
        widget=forms.DateInput(
            attrs={
                'class': "form-control",
                'id': 'datepicker_enddate'},
            format='%a %d %b %Y'
        ),
        required=True,
    )

    def clean(self):
        super(UploadTimetableForm, self).clean()
        cleaned_data = self.cleaned_data

        start_date = self.data.get('start_date')
        if start_date:
            if self.errors.get('start_date'):
                del self.errors['start_date']
            try:
                start_date = datetime.strptime(start_date, '%a %d %b %Y').date()
                if start_date >= timezone.now().date():
                    cleaned_data['start_date'] = start_date
                else:
                    self.add_error('start_date',
                                   'Must be in the future')
            except ValueError:
                self.add_error(
                    'start_date', 'Invalid date format.  Select from '
                                        'the date picker or enter date in the '
                                        'format e.g. Mon 08 Jun 2015')

        end_date = self.data.get('end_date')
        if end_date:
            if self.errors.get('end_date'):
                del self.errors['end_date']
            try:
                end_date = datetime.strptime(end_date, '%a %d %b %Y').date()
            except ValueError:
                self.add_error(
                    'end_date', 'Invalid date format.  Select from '
                                        'the date picker or enter date in the '
                                        'format ddd DD Mmm YYYY (e.g. Mon 15 Jun 2015)')

        if not self.errors.get('end_date') and not self.errors.get('start_date'):
            if end_date >= start_date:
                cleaned_data['end_date'] = end_date
            else:
                self.add_error('end_date',
                                   'Cannot be before start date')
        return cleaned_data


class ChooseUsersBaseFormSet(BaseModelFormSet):

    def add_fields(self, form, index):
        super(ChooseUsersBaseFormSet, self).add_fields(form, index)

        form.fields['email_user'] = forms.BooleanField(
            widget=forms.CheckboxInput(attrs={
                'class': "regular-checkbox studioadmin-list select-checkbox",
                'id': 'email_user_cbox_{}'.format(index)
            }),
            initial=True,
            required=False
        )
        form.email_user_cbox_id = 'email_user_cbox_{}'.format(index)

ChooseUsersFormSet = modelformset_factory(
    User,
    fields=('id',),
    formset=ChooseUsersBaseFormSet,
    extra=0,
    can_delete=False)


class EmailUsersForm(forms.Form):
    subject = forms.CharField(max_length=255, required=True,
                              widget=forms.TextInput(
                                  attrs={'class': 'form-control'}))
    from_address = forms.EmailField(max_length=255,
                                    initial=settings.DEFAULT_STUDIO_EMAIL,
                                    required=True,
                                    widget=forms.TextInput(
                                        attrs={'class': 'form-control'}),
                                    help_text='This will be the reply-to address')
    cc = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={
                'class': "regular-checkbox studioadmin-list",
                'id': 'cc_id'
            }),
        label="cc. from address",
        initial=True,
        required=False
    )
    message = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control email-message',
                                     'rows': 10}),
        required=True)


def get_event_names(event_type):

    def callable():
        EVENT_CHOICES = [(event.id, str(event)) for event in Event.objects.filter(
            event_type__event_type=event_type, date__gte=timezone.now()
        ).order_by('date')]
        EVENT_CHOICES.insert(0, ('', '--None selected--'))
        return tuple(EVENT_CHOICES)

    return callable


class UserFilterForm(forms.Form):

    events = forms.MultipleChoiceField(
        choices=get_event_names('EV'),
        widget=forms.SelectMultiple(
            attrs={'class': 'form-control'}
        ),
    )

    lessons = forms.MultipleChoiceField(
        choices=get_event_names('CL'),
        widget=forms.SelectMultiple(
            attrs={'class': 'form-control'}
        ),
    )


class BlockStatusFilter(forms.Form):

    block_status = forms.ChoiceField(
        choices=(('current', 'Current (paid and unpaid)'),
                 ('active', 'Active (current and paid)'),
                 ('unpaid', 'Unpaid (current)'),
                 ('expired', 'Expired or full'),
                 ('all', 'All'),
                 ),
        widget=forms.Select(),
    )


class UserBlockModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return "{}{}; exp {}; {} left".format(
            obj.block_type.event_type.subtype,
            " ({})".format(obj.block_type.identifier)
            if obj.block_type.identifier else '',
            obj.expiry_date.strftime('%d/%m'),
            obj.block_type.size - obj.bookings_made()
        )

    def to_python(self, value):
        if value:
            return Block.objects.get(id=value)


class UserModelChoiceField(forms.ModelChoiceField):

    def label_from_instance(self, obj):
        return "{} {} ({})".format(
            obj.first_name, obj.last_name, obj.username
        )

    def to_python(self, value):
        if value:
            return User.objects.get(id=value)


class UserBookingInlineFormSet(BaseInlineFormSet):

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super(UserBookingInlineFormSet, self).__init__(*args, **kwargs)
        for form in self.forms:
            form.empty_permitted = True

    def add_fields(self, form, index):
        super(UserBookingInlineFormSet, self).add_fields(form, index)

        if form.instance.id:
            ppbs = PaypalBookingTransaction.objects.filter(
                booking_id=form.instance.id
            )
            ppbs_paypal =[True for ppb in ppbs if ppb.transaction_id]
            form.paypal = True if ppbs_paypal else False

            cancelled_class = 'expired' if form.instance.status == 'CANCELLED' else 'none'

            if form.instance.block is None:
                if form.instance.status == 'OPEN':
                    active_user_blocks = [
                        block.id for block in Block.objects.filter(
                            user=form.instance.user,
                            block_type__event_type=form.instance.event.event_type)
                        if block.active_block()
                    ]
                    form.has_available_block = True if active_user_blocks else False
                    form.fields['block'] = (UserBlockModelChoiceField(
                        queryset=Block.objects.filter(id__in=active_user_blocks),
                        widget=forms.Select(attrs={'class': '{} form-control input-sm'.format(cancelled_class)}),
                        required=False,
                        empty_label="--------None--------"
                    ))
            else:
                form.fields['block'] = (UserBlockModelChoiceField(
                    queryset=Block.objects.filter(id=form.instance.block.id),
                    widget=forms.Select(attrs={'class': '{} form-control input-sm'.format(cancelled_class)}),
                    required=False,
                    empty_label="---REMOVE BLOCK (TO CHANGE BLOCK, REMOVE AND SAVE FIRST)---",
                    initial=form.instance.block.id
                ))

        else:
            active_blocks = [
                block.id for block in Block.objects.filter(user=self.user)
                    if block.active_block()
            ]
            form.fields['block'] = (UserBlockModelChoiceField(
                queryset=Block.objects.filter(id__in=active_blocks),
                widget=forms.Select(attrs={'class': 'form-control input-sm'}),
                required=False,
                empty_label="---Choose from user's active blocks---"
            ))

        if form.instance.id is None:
            already_booked = [
                booking.event.id for booking
                in Booking.objects.filter(user=self.user)
            ]

            form.fields['event'] = forms.ModelChoiceField(
                queryset=Event.objects.filter(
                    date__gte=timezone.now()
                ).filter(booking_open=True, cancelled=False).exclude(
                    id__in=already_booked).order_by('date'),
                widget=forms.Select(attrs={'class': 'form-control input-sm'}),
            )
        else:
            form.fields['event'] = (forms.ModelChoiceField(
                queryset=Event.objects.all(),
            ))

        form.fields['paid'] = forms.BooleanField(
            widget=forms.CheckboxInput(attrs={
                'class': "regular-checkbox",
                'id': 'paid_{}'.format(index)
            }),
            required=False
        )
        form.paid_id = 'paid_{}'.format(index)

        form.fields['deposit_paid'] = forms.BooleanField(
            widget=forms.CheckboxInput(attrs={
                'class': "regular-checkbox",
                'id': 'deposit_paid_{}'.format(index)
            }),
            required=False
        )
        form.deposit_paid_id = 'deposit_paid_{}'.format(index)

        form.fields['free_class'] = forms.BooleanField(
            widget=forms.CheckboxInput(attrs={
                'class': "regular-checkbox",
                'id': 'free_class_{}'.format(index)
            }),
            required=False
        )
        form.free_class_id = 'free_class_{}'.format(index)
        form.fields['send_confirmation'] = forms.BooleanField(
            widget=forms.CheckboxInput(attrs={
                'class': "regular-checkbox",
                'id': 'send_confirmation_{}'.format(index)
            }),
            initial=False,
            required=False
        )
        form.send_confirmation_id = 'send_confirmation_{}'.format(index)
        form.fields['status'] = forms.ChoiceField(
            choices=(('OPEN', 'OPEN'), ('CANCELLED', 'CANCELLED')),
            widget=forms.Select(attrs={'class': 'form-control input-sm'}),
            initial='OPEN'
        )

    def clean(self):
        """
        make sure that block selected is for the correct event type
        and that a block has not been filled
        :return:
        """
        super(UserBookingInlineFormSet, self).clean()
        if {
            '__all__': ['Booking with this User and Event already exists.']
        } in self.errors:
            pass
        elif any(self.errors):
            return

        block_tracker = {}
        for form in self.forms:
            block = form.cleaned_data.get('block')
            event = form.cleaned_data.get('event')
            free_class = form.cleaned_data.get('free_class')
            status = form.cleaned_data.get('status')


            if form.instance.status == 'CANCELLED' and form.instance.block and \
                'block' in form.changed_data:
                error_msg = 'A cancelled booking cannot be assigned to a ' \
                    'block.  Please change status of booking for {} to "OPEN" ' \
                    'before assigning block'.format(event)
                form.add_error('block', error_msg)
                raise forms.ValidationError(error_msg)

            if event:
                if event.event_type.event_type == 'CL':
                    ev_type = "class"
                elif event.event_type.event_type == 'EV':
                    ev_type = "event"

                if event.cancelled:
                    if form.instance.block:
                        error_msg = 'Cannot assign booking for cancelled ' \
                                    'event {} to a block'.format(event)
                        form.add_error('block', error_msg)
                    if form.instance.status == 'OPEN':
                        error_msg = 'Cannot reopen booking for cancelled ' \
                                    'event {}'.format(event)
                        form.add_error('status', error_msg)
                    if form.instance.free_class:
                        error_msg = 'Cannot assign booking for cancelled ' \
                                    'event {} as free class'.format(event)
                        form.add_error('free_class', error_msg)
                    if form.instance.paid:
                        error_msg = 'Cannot assign booking for cancelled ' \
                                    'event {} as paid'.format(event)
                        form.add_error('paid', error_msg)
                    if form.instance.deposit_paid:
                        error_msg = 'Cannot assign booking for cancelled ' \
                                    'event {} as deposit paid'.format(event)
                        form.add_error('deposit_paid', error_msg)

            if block and event and status == 'OPEN':
                if not block_tracker.get(block.id):
                    block_tracker[block.id] = 0
                block_tracker[block.id] += 1

                if event.event_type != block.block_type.event_type:
                    available_block_type = BlockType.objects.filter(
                        event_type=event.event_type
                    )
                    if not available_block_type:
                        error_msg = '{} ({} type "{}") cannot be ' \
                                    'block-booked'.format(
                            event, ev_type, event.event_type
                        )
                    else:
                        error_msg = '{} (type "{}") can only be block-booked with a "{}" ' \
                                    'block type.'.format(
                            event, event.event_type, available_block_type[0].event_type
                        )
                    form.add_error('block', error_msg)
                else:
                    if block.bookings_made() + block_tracker[block.id] > block.block_type.size:
                        error_msg = 'Block selected for {} is now full. ' \
                                    'Add another block for this user or confirm ' \
                                    'payment was made directly.'.format(event)
                        form.add_error('block', error_msg)
            if block and free_class:
                error_msg = '"Free class" cannot be assigned to a block.'
                form.add_error('free_class', error_msg)


UserBookingFormSet = inlineformset_factory(
    User,
    Booking,
    fields=('paid', 'deposit_paid', 'event', 'block', 'status', 'free_class'),
    can_delete=False,
    formset=UserBookingInlineFormSet,
    extra=1,
)


class BlockTypeModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return "{}{} - quantity {}".format(
            obj.event_type.subtype,
            " ({})".format(obj.identifier) if obj.identifier else '',
            obj.size
        )
    def to_python(self, value):
        if value:
            return BlockType.objects.get(id=value)


class UserBlockInlineFormSet(BaseInlineFormSet):

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super(UserBlockInlineFormSet, self).__init__(*args, **kwargs)

        for form in self.forms:
            form.empty_permitted = True

    def add_fields(self, form, index):
        super(UserBlockInlineFormSet, self).add_fields(form, index)

        user_blocks = Block.objects.filter(user=self.user)
        # get the event types for the user's blocks that are currently active
        # or awaiting payment
        user_block_event_types = [
            block.block_type.event_type for block in user_blocks
            if block.active_block() or
            (not block.expired and not block.paid and not block.full)
        ]
        available_block_types = BlockType.objects.exclude(
            event_type__in=user_block_event_types
        )
        form.can_buy_block = True if available_block_types else False

        if not form.instance.id:
            form.fields['block_type'] = (BlockTypeModelChoiceField(
                queryset=available_block_types,
                widget=forms.Select(attrs={'class': 'form-control input-sm'}),
                required=False,
                empty_label="---Choose block type---"
            ))

            form.fields['start_date'] = forms.DateTimeField(
                widget=forms.DateTimeInput(
                    attrs={
                        'class': "form-control",
                        'id': "datepicker",
                        'placeholder': "dd/mm/yy",
                        'style': 'text-align: center'
                    },
                    format='%d %m %y',
                ),
                required=False,
            )

        if form.instance:
            # only allow deleting blocks if not yet paid
            if form.instance.paid:
                form.fields['DELETE'] = forms.BooleanField(
                    widget=forms.CheckboxInput(attrs={
                        'class': 'delete-checkbox-disabled studioadmin-list',
                        'disabled': 'disabled',
                        'id': 'DELETE_{}'.format(index)
                    }),
                    required=False
                )
            else:
                form.fields['DELETE'] = forms.BooleanField(
                    widget=forms.CheckboxInput(attrs={
                        'class': 'delete-checkbox studioadmin-list',
                        'id': 'DELETE_{}'.format(index)
                    }),
                    required=False
                )
            form.DELETE_id = 'DELETE_{}'.format(index)

        form.fields['paid'] = forms.BooleanField(
            widget=forms.CheckboxInput(attrs={
                'class': "regular-checkbox",
                'id': 'paid_{}'.format(index)
            }),
            required=False
            )
        form.paid_id = 'paid_{}'.format(index)




UserBlockFormSet = inlineformset_factory(
    User,
    Block,
    fields=('paid', 'start_date', 'block_type'),
    can_delete=True,
    formset=UserBlockInlineFormSet,
    extra=1,
)


class ActivityLogSearchForm(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(
            attrs={
                'placeholder': 'Search log text'
            }
        )
    )
    search_date = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={
                'id': "logdatepicker",
                'placeholder': "Search by log date",
                'style': 'text-align: center'
            },
            format='%d-%m-%y',
        ),
    )
    hide_empty_cronjobs = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={
            'class': "regular-checkbox",
            'id': 'hide_empty_cronjobs_id'
        }),
        initial='on'
    )


class TicketedEventBaseFormSet(BaseModelFormSet):

    def add_fields(self, form, index):
        super(TicketedEventBaseFormSet, self).add_fields(form, index)

        if form.instance:
            form.fields['show_on_site'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={
                    'class': "regular-checkbox studioadmin-list",
                    'id': 'show_on_site_{}'.format(index)
                }),
                required=False
            )
            form.show_on_site_id = 'show_on_site_{}'.format(index)

            form.fields['payment_open'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={
                    'class': "regular-checkbox studioadmin-list",
                    'id': 'payment_open_{}'.format(index)
                }),
                required=False
            )
            form.payment_open_id = 'payment_open_{}'.format(index)

            form.fields['advance_payment_required'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={
                    'class': "regular-checkbox studioadmin-list",
                    'id': 'advance_payment_required_{}'.format(index)
                }),
                required=False
            )
            form.advance_payment_required_id = 'advance_payment_required_{}'.format(index)

            confirmed_ticket_bookings = form.instance.ticket_bookings.filter(
                purchase_confirmed=True
            )
            if confirmed_ticket_bookings:
                form.cannot_delete = True

            form.fields['DELETE'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={
                    'class': 'delete-checkbox studioadmin-list',
                    'id': 'DELETE_{}'.format(index)
                }),
                required=False
            )
            form.DELETE_id = 'DELETE_{}'.format(index)

TicketedEventFormSet = modelformset_factory(
    TicketedEvent,
    fields=(
        'payment_open', 'advance_payment_required', 'show_on_site'
    ),
    formset=TicketedEventBaseFormSet,
    extra=0,
    can_delete=True
)


class TicketedEventAdminForm(forms.ModelForm):

    required_css_class = 'form-error'

    ticket_cost = forms.DecimalField(
        widget=forms.TextInput(attrs={
            'type': 'text',
            'class': 'form-control',
            'aria-describedby': 'sizing-addon2',
        }),
        initial=0,
    )

    extra_ticket_info_label = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': "form-control"}
            ),
        label="Label",
        help_text="Label for extra information to be entered for each ticket; "
                  "leave blank if no extra info needed.",
        required=False
    )
    extra_ticket_info_required = forms.BooleanField(
        widget=forms.CheckboxInput(
            attrs={
                'class': "form-control regular-checkbox",
                'id': 'extra_ticket_info_required_id'
            }
            ),
        label="Required?",
        help_text="Tick if this information is mandatory",
        required=False
    )
    extra_ticket_info_help = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': "form-control"}
            ),
        label="Help text",
        help_text="Description/details/help text to display under the extra "
                  "information field",
        required=False
    )

    extra_ticket_info1_label = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': "form-control"}
            ),
        label="Label",
        help_text="Label for extra information to be entered for each ticket; "
                  "leave blank if no extra info needed.",
        required=False
    )
    extra_ticket_info1_required = forms.BooleanField(
        widget=forms.CheckboxInput(
            attrs={
                'class': "form-control regular-checkbox",
                'id': 'extra_ticket_info1_required_id'
            }
            ),
        label="Required?",
        help_text="Tick if this information is mandatory",
        required=False
    )
    extra_ticket_info1_help = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': "form-control"}
            ),
        label="Help text",
        help_text="Description/details/help text to display under the extra "
                  "information field",
        required=False
    )

    def __init__(self, *args, **kwargs):
        super(TicketedEventAdminForm, self).__init__(*args, **kwargs)
        if self.instance.id:
            if not self.instance.cancelled:
                self.fields['cancelled'].label = "Cancelled: No"
                self.fields['cancelled'].help_text = 'To cancel, use the Cancel ' \
                                                     'button on the event ' \
                                                     'list page'
                self.fields['cancelled'].widget.attrs.update(
                    {'disabled': 'disabled', 'class': "hide"})
            else:
                self.fields['cancelled'].\
                    help_text = 'Untick to reopen event; note that this does ' \
                                'not change any other event attributes and ' \
                                'does not reopen previously cancelled ticket ' \
                                'bookings.'

    def clean(self):
        super(TicketedEventAdminForm, self).clean()
        cleaned_data = self.cleaned_data
        is_new = False if self.instance else True

        date = self.data.get('date')
        if date:
            if self.errors.get('date'):
                del self.errors['date']
            try:
                date = datetime.strptime(self.data['date'], '%d %b %Y %H:%M')
                uk = pytz.timezone('Europe/London')
                cleaned_data['date'] = uk.localize(date).astimezone(pytz.utc)
            except ValueError:
                self.add_error('date', 'Invalid date format.  Select from the '
                                       'date picker or enter date and time in the '
                                       'format dd Mmm YYYY HH:MM')

        payment_due_date = self.data.get('payment_due_date')
        if payment_due_date:
            if self.errors.get('payment_due_date'):
                del self.errors['payment_due_date']
            try:
                payment_due_date = datetime.strptime(payment_due_date, '%d %b %Y')
                if payment_due_date < date:
                    cleaned_data['payment_due_date'] = payment_due_date
                else:
                    self.add_error(
                        'payment_due_date',
                        'Payment due date must be before event date'
                    )
                cleaned_data['payment_due_date'] = payment_due_date
            except ValueError:
                self.add_error(
                    'payment_due_date',
                    'Invalid date format.  Select from the date picker or '
                    'enter date in the format dd Mmm YYYY')

        if not cleaned_data.get('extra_ticket_info_label'):
            if cleaned_data.get('extra_ticket_info_required'):
                self.add_error(
                    'extra_ticket_info_required',
                    'Provide a label for this extra ticket info field'
                )
            if cleaned_data.get('extra_ticket_info_help'):
                self.add_error(
                    'extra_ticket_info_help',
                    'Provide a label for this extra ticket info field'
                )
        if not cleaned_data.get('extra_ticket_info1_label'):
            if cleaned_data.get('extra_ticket_info1_required'):
                self.add_error(
                    'extra_ticket_info1_required',
                    'Provide a label for this extra ticket info field'
                )
            if cleaned_data.get('extra_ticket_info1_help'):
                self.add_error(
                    'extra_ticket_info1_help',
                    'Provide a label for this extra ticket info field'
                )

        if cleaned_data.get('advance_payment_required'):
            if not (cleaned_data.get('payment_due_date') or
                        cleaned_data.get('payment_time_allowed')):
                self.add_error(
                    'advance_payment_required',
                    'Please provide either a payment due date or payment '
                    'time allowed'
                    )
            elif cleaned_data.get('payment_due_date') and \
                    cleaned_data.get('payment_time_allowed'):
                self.add_error(
                    'payment_due_date',
                    'Please provide either a payment due date or payment time '
                    'allowed (but not both)'
                )
                self.add_error(
                    'payment_time_allowed',
                    'Please provide either a payment due date or payment time '
                    'allowed (but not both)'
                )
        else:
            if cleaned_data.get('payment_due_date'):
                self.add_error(
                    'payment_due_date',
                    'To specify a payment due date, please also tick '
                    '"advance payment required"'
                    )
            if cleaned_data.get('payment_time_allowed'):
                self.add_error(
                    'payment_time_allowed',
                    'To specify payment time allowed, please also '
                    'tick "advance payment required"'
                    )

        if not cleaned_data.get('ticket_cost'):
            ticket_cost_errors = []
            if cleaned_data.get('advance_payment_required'):
                ticket_cost_errors.append('advance payment required')
            if cleaned_data.get('payment_due_date'):
                ticket_cost_errors.append('payment due date')
            if cleaned_data.get('payment_time_allowed'):
                ticket_cost_errors.append('payment time allowed')
            if ticket_cost_errors:
                self.add_error(
                    'ticket_cost',
                    'The following fields require a ticket cost greater than '
                    '£0: {}'.format(', '.join(ticket_cost_errors))
                )

        return cleaned_data

    class Meta:
        model = TicketedEvent
        fields = (
            'name', 'date', 'description', 'location',
            'max_tickets', 'contact_person', 'contact_email', 'ticket_cost',
            'payment_open', 'advance_payment_required', 'payment_info',
            'payment_due_date', 'payment_time_allowed',
            'email_studio_when_purchased', 'max_ticket_purchase',
            'extra_ticket_info_label', 'extra_ticket_info_required',
            'extra_ticket_info_help', 'extra_ticket_info1_label',
            'extra_ticket_info1_required',
            'extra_ticket_info1_help', 'show_on_site', 'cancelled',
        )
        labels = {
            'max_tickets': 'Maximum available tickets',
            'max_ticket_purchase': 'Maximum tickets per booking'
        }
        widgets = {
            'name': forms.TextInput(
                attrs={
                    'class': "form-control",
                    'placeholder': 'Name of event'
                }
            ),
            'description': CKEditorWidget(
                attrs={'class': 'form-control container-fluid'},
                config_name='studioadmin',
            ),
            'payment_info': CKEditorWidget(
                attrs={'class': 'form-control container-fluid'},
                config_name='studioadmin_min',
            ),
            'location': forms.TextInput(
                attrs={'class': "form-control"}
            ),
            'max_tickets': forms.TextInput(
                attrs={'class': "form-control"}
            ),
            'contact_person': forms.TextInput(
                attrs={'class': "form-control"}
            ),
            'contact_email': forms.EmailInput(
                attrs={'class': "form-control"}
            ),
            'payment_time_allowed': forms.TextInput(
                attrs={'class': "form-control"}
            ),
            'payment_due_date': forms.DateInput(
                attrs={
                    'class': "form-control",
                    'id': "datepicker",
                },
                format='%d %b %Y'
            ),
            'date': forms.DateTimeInput(
                attrs={
                    'class': "form-control",
                    'id': "datetimepicker",
                },
                format='%d %b %Y %H:%M'
            ),
            'payment_open': forms.CheckboxInput(
                attrs={
                    'class': "form-control regular-checkbox",
                    'id': 'payment_open_id',
                    },
            ),
            'advance_payment_required': forms.CheckboxInput(
                attrs={
                    'class': "form-control regular-checkbox",
                    'id': 'advance_payment_required_id',
                    },
            ),
            'email_studio_when_purchased': forms.CheckboxInput(
                attrs={
                    'class': "form-control regular-checkbox",
                    'id': 'email_studio_id',
                    },
            ),
            'max_ticket_purchase': forms.TextInput(
                attrs={'class': "form-control"}
            ),
            'show_on_site': forms.CheckboxInput(
                attrs={
                    'class': "form-control regular-checkbox",
                    'id': 'show_on_site_id',
                    }
            ),
            'cancelled': forms.CheckboxInput(
                attrs={
                    'class': "form-control regular-checkbox",
                    'id': 'cancelled_id',
                    }
            ),
            }
        help_texts = {
            'payment_open': _('Only applicable if the ticket cost is greater than £0'),
            'payment_due_date': _('Only use this field if the ticket cost is greater '
                                  'than £0.  If a payment due date is set, '
                                  'advance payment will always be required'),
            'email_studio_when_purchased': _('Tick if you want the studio to '
                                          'receive email notifications when a '
                                          'ticket booking is made'),
            'advance_payment_required': _('If this checkbox is not ticked, '
                                          'unpaid ticket bookings will remain '
                                          'active after the payment due date or '
                                          'time allowed for payment, and will not be '
                                          'automatically cancelled')
        }


class TicketBookingInlineBaseFormSet(BaseInlineFormSet):

    def add_fields(self, form, index):
        super(TicketBookingInlineBaseFormSet, self).add_fields(form, index)

        pptbs = PaypalTicketBookingTransaction.objects.filter(
            ticket_booking__id=form.instance.id
        )
        pptbs_paypal =[True for pptb in pptbs if pptb.transaction_id]
        form.paypal = True if pptbs_paypal else False

        form.fields['cancel'] = forms.BooleanField(
            widget=forms.CheckboxInput(attrs={
                'class': 'delete-checkbox studioadmin-list',
                'id': 'cancel_{}'.format(index)
            }),
            required=False
        )
        form.cancel_id = 'cancel_{}'.format(index)

        form.fields['reopen'] = forms.BooleanField(
            widget=forms.CheckboxInput(attrs={
                'class': 'regular-checkbox reopen studioadmin-list',
                'id': 'reopen_{}'.format(index)
            }),
            required=False
        )
        form.reopen_id = 'reopen_{}'.format(index)

        form.fields['paid'] = forms.BooleanField(
            widget=forms.CheckboxInput(attrs={
                'class': 'regular-checkbox studioadmin-list',
                'id': 'paid_{}'.format(index)
            }),
            required=False
        )
        form.paid_id = 'paid_{}'.format(index)

        form.fields['send_confirmation'] = forms.BooleanField(
            widget=forms.CheckboxInput(attrs={
                'class': 'regular-checkbox studioadmin-list',
                'id': 'send_confirmation_{}'.format(index)
            }),
            required=False
        )
        form.send_confirmation_id = 'send_confirmation_{}'.format(index)


TicketBookingInlineFormSet = inlineformset_factory(
    TicketedEvent,
    TicketBooking,
    fields=('paid', ),
    formset=TicketBookingInlineBaseFormSet,
    extra=0,
)


class PrintTicketsForm(forms.Form):

    def __init__(self, *args, **kwargs):
        self.ticketed_event = kwargs.pop('ticketed_event_instance', None)
        super(PrintTicketsForm, self).__init__(*args, **kwargs)

        self.fields['ticketed_event'] = forms.ModelChoiceField(
            label="Event",
            widget=forms.Select(
              attrs={'class': 'form-control', 'onchange': 'form.submit()'}
            ),
            queryset=TicketedEvent.objects.filter(
                date__gte=timezone.now(),
                cancelled=False
            ),
            required=True,
            initial=self.ticketed_event
        )

        order_field_choices = [
            ('ticket_booking__date_booked', 'Date booked (earliest first)'),
            ('-ticket_booking__date_booked', 'Date booked (latest first)'),
            ('ticket_booking__booking_reference', 'Booking reference'),
            ('ticket_booking__user__first_name', 'User who made the booking'),
        ]
        show_fields_choices = [
            ('show_booking_user', 'User who made the booking'),
            ('show_date_booked', 'Date booked'),
            ('show_booking_reference', 'Booking reference'),
            ('show_paid', 'Paid status'),
        ]

        if self.ticketed_event:
            if self.ticketed_event.extra_ticket_info_label:
                order_field_choices.insert(
                    len(order_field_choices) + 1, (
                        'extra_ticket_info',
                        self.ticketed_event.extra_ticket_info_label +
                        " (extra requested ticket info)"
                    )
                )
                show_fields_choices.insert(
                    len(show_fields_choices) + 1, (
                        'show_extra_ticket_info',
                        self.ticketed_event.extra_ticket_info_label +
                        " (extra requested ticket info)"
                    )
                )

            if self.ticketed_event.extra_ticket_info1_label:
                order_field_choices.insert(
                    len(order_field_choices) + 1, (
                        'extra_ticket_info1',
                        self.ticketed_event.extra_ticket_info1_label +
                        " (extra requested ticket info)"
                    )
                )
                show_fields_choices.insert(
                    len(show_fields_choices) + 1, (
                        'show_extra_ticket_info1',
                        self.ticketed_event.extra_ticket_info1_label +
                        " (extra requested ticket info)"
                    )
                )

        self.fields['show_fields'] = forms.MultipleChoiceField(
            label="Choose fields to show:",
            widget=forms.CheckboxSelectMultiple,
            choices=show_fields_choices,
            initial=[
                'show_booking_user', 'show_date_booked',
                'show_booking_reference'
            ],
            required=True
        )

        self.fields['order_field'] = forms.ChoiceField(
            label="Sort tickets by:",
            choices=order_field_choices,
            widget=forms.RadioSelect,
            initial='ticket_booking__user__first_name',
            required=True
        )
    
    def clean(self):
        cleaned_data = super(PrintTicketsForm, self).clean()

        if 'show_fields' in self.errors:
            if self.data.get('show_fields') == 'show_extra_ticket_info' \
                    or self.data.get('show_fields') == 'show_extra_ticket_info1':
                del self.errors['show_fields']
                cleaned_data['show_fields'] = self.data.getlist('show_fields')
        if 'order_field' in self.errors:
            if self.data.get('order_field') == 'extra_ticket_info' \
                    or self.data.get('order_field') == 'extra_ticket_info1':
                del self.errors['order_field']
                cleaned_data['order_field'] = self.data.get('order_field')

        return cleaned_data
