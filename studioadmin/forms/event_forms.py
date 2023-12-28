# -*- coding: utf-8 -*-
from typing import Any
import pytz
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.models import Group
from django import forms
from django.forms.models import modelformset_factory, BaseModelFormSet
from django.utils.translation import gettext_lazy as _

from ckeditor.widgets import CKEditorWidget

from booking.models import AllowedGroup, Event, EventType, FilterCategory

from studioadmin.forms.utils import cancel_choices


class EventBaseFormSet(BaseModelFormSet):

    def add_fields(self, form, index):
        super(EventBaseFormSet, self).add_fields(form, index)

        if form.instance:
            form.fields['visible_on_site'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={
                    'class': "form-check-input position-static studioadmin-list",
                }),
                required=False,
                label="Visible"
            )

            form.fields['booking_open'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={
                    'class': "form-check-input position-static studioadmin-list",
                }),
                required=False
            )

            form.fields['payment_open'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={
                    'class': "form-check-input position-static studioadmin-list",
                }),
                required=False
            )

            form.fields['advance_payment_required'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={
                    'class': "form-check-input position-static  studioadmin-list",
                }),
                required=False
            )

            form.fields['DELETE'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={
                    'class': 'form-check-input position-static studioadmin-list',
                    'id': 'DELETE_{}'.format(index)
                }),
                required=False
            )
            form.DELETE_id = 'DELETE_{}'.format(index)


EventFormSet = modelformset_factory(
    Event,
    fields=(
        'visible_on_site', 'booking_open', 'payment_open', 'advance_payment_required'
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

    paypal_email_check = forms.CharField(
        widget=forms.EmailInput(
            attrs={'class': "form-control"}
        ),
        help_text=_(
            'If you are changing the paypal email, please re-enter as confirmation'
        ),
        required=False
    )

    new_category = forms.CharField(widget=forms.HiddenInput, label="", required=False)

    def __init__(self, *args, **kwargs):
        ev_type = kwargs.pop('ev_type')
        super(EventAdminForm, self).__init__(*args, **kwargs)

        self.fields['payment_time_allowed'].widget.attrs = {
            'class': 'form-control'
        }
        self.fields['payment_time_allowed'].initial = 4

        cat_field = self.fields["categories"]
        cat_field.required = False
        ev_type_qset = EventType.objects.filter(event_type=ev_type)
        if ev_type in ["CL", "RH"]:
            self.fields["categories"] = forms.ModelMultipleChoiceField(
                queryset=FilterCategory.objects.all(),
                widget=forms.CheckboxSelectMultiple(),
                required=False,
                label="Filter categories",
            )
            self.fields["new_category"].widget = forms.TextInput()
            self.fields["new_category"].label = "Add new filter category"

        self.fields['event_type'] = forms.ModelChoiceField(
            widget=forms.Select(attrs={'class': "form-control"}),
            queryset=ev_type_qset,
        )

        self.fields['allowed_group'].widget.attrs = {'class': "form-control"}

        ph_type = "event" if ev_type == 'EV' else 'class' if ev_type == "CL" else 'room hire' if ev_type == "RH" else "online tutorial"
        ex_name = "Workshop" if ev_type == 'EV' else "Pole Level 1" if ev_type == "CL" else "Private Practice" if ev_type == "RH" else "Spin Combo"
        self.fields['name'] = forms.CharField(
            widget=forms.TextInput(
                attrs={
                    'class': "form-control",
                    'placeholder': 'Name of {} e.g. {}'.format(ph_type, ex_name)
                }
            )
        )

        if self.instance.id:
            ev_type_str = ph_type

            if not self.instance.cancelled:
                self.fields['cancelled'].\
                    help_text = 'To cancel, use the Cancel button on the {} ' \
                                'list page'.format(ev_type_str)
                self.fields['cancelled'].disabled = True
            else:
                self.fields['cancelled'].\
                    help_text = 'Untick to reopen {}; note that this does ' \
                                'not change any other attributes and ' \
                                'does not reopen previously cancelled ' \
                                'bookings.  {} will be reopened with both ' \
                                'booking and payment CLOSED'.format(
                    ev_type_str, ev_type_str.title()
                )
        else:
            self.fields['paypal_email'].initial = settings.DEFAULT_PAYPAL_EMAIL
            self.fields['allowed_group'].initial = AllowedGroup.default_group().id

    def clean_new_category(self):
        new_category = self.cleaned_data.get("new_category")
        if new_category:
            if FilterCategory.objects.filter(category__iexact=new_category).exists():
                self.add_error("new_category", "Category already exists")
                return
        return new_category

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

        if 'paypal_email' in self.changed_data:
            if 'paypal_email_check' not in self.changed_data:
                self.add_error(
                    'paypal_email_check',
                    'Please reenter paypal email to confirm changes'
                )
            elif self.cleaned_data['paypal_email'] != self.cleaned_data['paypal_email_check']:
                self.add_error(
                    'paypal_email',
                    'Email addresses do not match'
                )
                self.add_error(
                    'paypal_email_check',
                    'Email addresses do not match'
                )

        return cleaned_data

    class Meta:
        model = Event
        fields = (
            'name', 'event_type', 'date', 'categories', 'new_category',
            'allowed_group',
            'video_link', 'video_link_available_after_class',
            'description', 'location',
            'max_participants', 'contact_person', 'contact_email', 'cost',
            'external_instructor', 'visible_on_site',
            'booking_open', 'payment_open', 'advance_payment_required',
            'paypal_email', 'paypal_email_check',
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
            'video_link': forms.TextInput(
                attrs={'class': "form-control"}
            ),
            'video_link_available_after_class': forms.CheckboxInput(
                attrs={'class': "form-check-input"}
            ),
            'payment_info': CKEditorWidget(
                attrs={'class': 'form-control container-fluid'},
                config_name='studioadmin_min',
            ),
            'location': forms.Select(
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
                    "autocomplete": "off"
                },
                format='%d %b %Y'
            ),
            'date': forms.DateTimeInput(
                attrs={
                    'class': "form-control",
                    'id': "datetimepicker",
                    "autocomplete": "off",
                },
                format='%d %b %Y %H:%M'
            ),
            'cancellation_period': forms.Select(
                choices=cancel_choices,
                attrs={
                    'class': "form-control",
                    }
            ),
            'visible_on_site': forms.CheckboxInput(
                attrs={'class': "form-check-input"}
            ),
            'booking_open': forms.CheckboxInput(
                attrs={'class': "form-check-input"}
            ),
            'payment_open': forms.CheckboxInput(
                attrs={'class': "form-check-input"},
            ),
            'advance_payment_required': forms.CheckboxInput(
                attrs={'class': "form-check-input"},
            ),
            'external_instructor': forms.CheckboxInput(
                attrs={'class': "form-check-input"},
            ),
            'email_studio_when_booked': forms.CheckboxInput(
                attrs={'class': "form-check-input"},
            ),
            'cancelled': forms.CheckboxInput(
                attrs={'class': "form-check-input"}
            ),
            'allow_booking_cancellation': forms.CheckboxInput(
                attrs={'class': "form-check-input"}
            ),
            'paypal_email': forms.EmailInput(
                attrs={'class': "form-control"}
            ),
            }
        help_texts = {
            'visible_on_site': _('Is this event visible to users?'),
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
                'Untick to make class/event non-refundable/transferable (users '
                'will be able to cancel but will not be eligible for refunds)'
            ),
            'paypal_email': _(
                'Email for the paypal account to be used for payment. '
                'Check this carefully!  If you enter an incorrect email, '
                'payments will fail or could be paid to the wrong account!'
            ),
        }


class OnlineTutorialAdminForm(EventAdminForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hidden_fields = [
            'external_instructor', 'video_link_available_after_class', 'allow_booking_cancellation',
            'cancellation_period', 'advance_payment_required', 'email_studio_when_booked', 'payment_due_date',
            'max_participants', "location"
        ]
        if not self.instance.id:
            self.hidden_fields.append("cancelled")
        self.fields["date"].label = "Last purchasable date"
        self.fields["video_link_available_after_class"].initial = True
        self.fields["advance_payment_required"].initial = True
        self.fields["allow_booking_cancellation"].initial = False
        self.fields["email_studio_when_booked"].initial = False
        self.fields["location"].initial = "Online"
        self.fields["max_participants"].initial = None
        self.fields["payment_due_date"].initial = None
        self.fields["video_link"].required = True
        self.fields["payment_time_allowed"].initial = 4

        for field in self.hidden_fields:
            self.fields[field].widget.attrs.update({'class': "hide"})
            self.fields[field].hidden = True

    def clean(self):
        super().clean()
        cost = self.cleaned_data.get('cost', 0)
        if cost is None or cost <= 0:
            self.cleaned_data["advance_payment_required"] = False
            self.cleaned_data["payment_due_date"] = None
            self.cleaned_data["payment_time_allowed"] = None
            self.cleaned_data["allow_booking_cancellation"] = True
            self.cleaned_data["cost"] = 0

            for field in ["advance_payment_required", "allow_booking_cancellation", "payment_due_date", "payment_time_allowed", "cost"]:
                if field in self.errors:
                    del self.errors[field]
        
