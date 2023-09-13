# -*- coding: utf-8 -*-

from datetime import datetime, date

from django import forms
from django.conf import settings
from django.forms.models import modelformset_factory, BaseModelFormSet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ckeditor.widgets import CKEditorWidget

from booking.models import Event, EventType, FilterCategory
from timetable.models import Session
from studioadmin.forms.utils import cancel_choices


DAY_CHOICES = dict(Session.DAY_CHOICES)


class SessionBaseFormSet(BaseModelFormSet):

    def add_fields(self, form, index):
        super(SessionBaseFormSet, self).add_fields(form, index)

        if form.instance:
            form.formatted_day = DAY_CHOICES[form.instance.day]

            form.fields['booking_open'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={'class': "form-check-input position-static"}),
                required=False
            )

            form.fields['payment_open'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={'class': "form-check-input position-static"}),
                initial=form.instance.payment_open,
                required=False
            )

            form.fields['advance_payment_required'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={'class': "form-check-input position-static"}),
                required=False
            )

            form.fields['DELETE'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={
                    'class': 'form-check-input position-static studioadmin-list',
                }),
                required=False
            )


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
        initial=9,
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

    categories = forms.ModelMultipleChoiceField(
        queryset=FilterCategory.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Filter categories"
    )
    new_category = forms.CharField(label="Add new filter category", required=False)

    def __init__(self, *args, **kwargs):
        super(SessionAdminForm, self).__init__(*args, **kwargs)
        self.fields['event_type'] = forms.ModelChoiceField(
            widget=forms.Select(attrs={'class': "form-control"}),
            queryset=EventType.objects.exclude(event_type="EV"),
        )
        self.fields['payment_time_allowed'].widget.attrs = {
            'class': 'form-control'
        }
        if self.instance.id:
            self.fields["categories"].initial = self.instance.categories.all()
        else:
            self.fields["paypal_email"].initial = settings.DEFAULT_PAYPAL_EMAIL

    def clean_new_category(self):
        new_category = self.cleaned_data.get("new_category")
        if new_category:
            if FilterCategory.objects.filter(category__iexact=new_category).exists():
                self.add_error("new_category", "Category already exists")
                return
        return new_category

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
                if 'time' in self.changed_data and self.instance.id \
                        and self.instance.time.strftime('%H:%M') \
                        == self.data['time']:
                    self.changed_data.remove('time')
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

        if not cleaned_data.get('advance_payment_required') and \
                cleaned_data.get('payment_time_allowed'):
            self.add_error(
                'payment_time_allowed',
                'To specify payment time allowed, please also '
                'tick "advance payment required"'
                )

        if not cleaned_data.get('cost'):
            cost_errors = []
            if cleaned_data.get('advance_payment_required'):
                cost_errors.append('advance payment required')
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
        model = Session
        fields = (
            'name', 'event_type', 'day', 'time', 'categories', 'new_category', 'description', 'location',
            'max_participants', 'contact_person', 'contact_email', 'cost',
            'external_instructor',
            'booking_open', 'payment_open', 'advance_payment_required',
            'payment_info', 'paypal_email', 'paypal_email_check',
            'payment_time_allowed', 'cancellation_period',
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
            'booking_open': forms.CheckboxInput(attrs={'class': "form-check-input"}),
            'payment_open': forms.CheckboxInput(attrs={'class': "form-check-input"}),
            'advance_payment_required': forms.CheckboxInput(attrs={'class': "form-check-input"}),
            'external_instructor': forms.CheckboxInput(attrs={'class': "form-check-input"}),
            'allow_booking_cancellation': forms.CheckboxInput(attrs={'class': "form-check-input"}),
            'email_studio_when_booked': forms.CheckboxInput(attrs={'class': "form-check-input"}),
            'paypal_email': forms.EmailInput(
                attrs={'class': "form-control"}
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
                'Untick to make class/event non-refundable/transferable (users '
                'will be able to cancel but will not be eligible for refunds)'
            )

        }


class UploadTimetableForm(forms.Form):
    override_options_visible_on_site = forms.CharField(
        widget=forms.RadioSelect(
            choices=(("1", "Yes"), ("0", "No")),
        ),
        initial="1",
        label="Visible on site"
    )
    override_options_booking_open = forms.CharField(
        widget=forms.RadioSelect(
            choices=(("1", "Yes"), ("0", "No"), ("default", "Use timetable defaults")),
        ),
        initial="default",
        label="Booking open"
    )
    override_options_payment_open = forms.CharField(
        widget=forms.RadioSelect(
            choices=(("1", "Yes"), ("0", "No"), ("default", "Use timetable defaults")),
        ),
        initial="default",
        label="Payment open"
    )

    def __init__(self, *args, **kwargs):
        location = kwargs.pop('location', 'all')
        super(UploadTimetableForm, self).__init__(*args, **kwargs)

        if location == 'all':
            qs = Session.objects.all().order_by('day', 'time')
            self.location_index = 0
        else:
            qs = Session.objects.filter(location=location).order_by('day', 'time')
            self.location_index = Event.LOCATION_INDEX_MAP[location]

        self.fields['start_date'] = forms.DateField(
            label="Start Date",
            widget=forms.DateInput(
                attrs={
                    'class': "form-control",
                    'id': 'datepicker_startdate_{}'.format(self.location_index),
                    'autocomplete': 'off'
                },
                format='%a %d %b %Y'
            ),
            required=True,
        )

        self.fields['end_date'] = forms.DateField(
            label="End Date",
            widget=forms.DateInput(
                attrs={
                    'class': "form-control",
                    'id': 'datepicker_enddate_{}'.format(self.location_index),
                    'autocomplete': 'off'
                },
                format='%a %d %b %Y'
            ),
            required=True,
        )

        self.fields['sessions'] = forms.ModelMultipleChoiceField(
            widget=forms.CheckboxSelectMultiple(
                attrs={'class': 'select-checkbox'}
            ),
            label="Choose sessions to upload",
            queryset=qs,
            initial=[session.pk for session in Session.objects.all()],
            required=True
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
