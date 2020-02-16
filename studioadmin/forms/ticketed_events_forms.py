# -*- coding: utf-8 -*-

import pytz
from datetime import datetime

from django import forms
from django.forms.models import modelformset_factory, BaseModelFormSet, \
    inlineformset_factory, BaseInlineFormSet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ckeditor.widgets import CKEditorWidget

from booking.models import TicketedEvent, TicketBooking
from payments.models import PaypalTicketBookingTransaction


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

    paypal_email_check = forms.CharField(
        widget=forms.EmailInput(
            attrs={'class': "form-control"}
        ),
        help_text=_(
            'If you are changing the paypal email, please re-enter as confirmation'
        ),
        required=False
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

        self.fields['payment_time_allowed'].widget.attrs = {
            'class': 'form-control'
        }

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
                if self.instance.id and cleaned_data['date'] == \
                        self.instance.date and 'date' in self.changed_data:
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
                if cleaned_data.get('date') and payment_due_date < date:
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
        model = TicketedEvent
        fields = (
            'name', 'date', 'description', 'location',
            'max_tickets', 'contact_person', 'contact_email', 'ticket_cost',
            'payment_open', 'advance_payment_required', 'payment_info',
            'paypal_email', 'paypal_email_check',
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
            'paypal_email': forms.EmailInput(
                attrs={'class': "form-control"}
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
