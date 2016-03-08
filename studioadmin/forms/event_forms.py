# -*- coding: utf-8 -*-
import pytz
from datetime import datetime, timedelta

from django import forms
from django.forms.models import modelformset_factory, BaseModelFormSet
from django.utils.translation import ugettext_lazy as _

from ckeditor.widgets import CKEditorWidget

from booking.models import Event, EventType

from studioadmin.forms.utils import cancel_choices


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

        self.fields['payment_time_allowed'].widget.attrs = {
            'class': 'form-control'
        }
        
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
                self.not_cancelled_text = 'No'
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
                if self.instance.id:
                    old_event = Event.objects.get(id=self.instance.id)
                    if old_event.date == cleaned_data['date']:
                        self.changed_data.remove('date')
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
