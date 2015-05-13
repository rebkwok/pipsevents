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

from booking.models import Block, Booking, Event, EventType
from timetable.models import Session


class EventBaseFormSet(BaseModelFormSet):

    def add_fields(self, form, index):
        super(EventBaseFormSet, self).add_fields(form, index)

        if form.instance:
            form.fields['booking_open'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={
                    'class': "regular-checkbox studioadmin-list",
                    'id': 'booking_open_{}'.format(index)
                }),
                initial=form.instance.booking_open,
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

            form.fields['cost'] = forms.DecimalField(
                widget=forms.TextInput(attrs={
                    'type': 'text',
                    'class': 'form-control studioadmin-list',
                    'aria-describedby': 'sizing-addon3',
                }),
                initial=form.instance.cost,
                required=False
            )
            form.fields['max_participants'] = forms.IntegerField(
                widget=forms.TextInput(attrs={
                    'type': 'text',
                    'class': 'form-control studioadmin-list',
                    'style': 'text-align: center; margin-left: 10;'
                }),
                initial=form.instance.max_participants,
                required=False
            )
            if form.instance.bookings.count() > 0:
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

EventFormSet = modelformset_factory(
    Event,
    fields=(
        'cost', 'max_participants',
        'booking_open', 'payment_open'
    ),
    formset=EventBaseFormSet,
    extra=0,
    can_delete=True
)


day = 24
week = day * 7

cancel_choices = (
    (day, '24 hours'),
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


def convert_date(date_string, dateformat, is_new=True):
    if is_new:
        localtz = pytz.timezone('Europe/London')
    else:
        localtz = pytz.utc
    naive_date = datetime.strptime(date_string, dateformat)
    local_dt = localtz.localize(
                naive_date, is_dst=time.localtime().tm_isdst
                )
    return local_dt.astimezone(pytz.utc)


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
        self.fields['event_type'] = forms.ModelChoiceField(
            widget=forms.Select(attrs={'class': "form-control"}),
            queryset=EventType.objects.filter(event_type=ev_type),
        )
        ph_type = "class" if ev_type == 'CL' else 'event'
        ex_name = "Pole Level 1" if ev_type == 'CL' else "Workshop"
        self.fields['name'] = forms.CharField(
            widget=forms.TextInput(
                attrs={
                    'class': "form-control",
                    'placeholder': 'Name of {} e.g. {}'.format(ph_type, ex_name)
                }
            )
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
                date = convert_date(self.data['date'], '%d %b %Y %H:%M', is_new=is_new)
                cleaned_data['date'] = date
            except ValueError:
                self.add_error('date', 'Invalid date format.  Select from the '
                                       'date picker or enter date and time in the '
                                       'format dd Mmm YYYY HH:MM')

        payment_due_date = self.data.get('payment_due_date')
        if payment_due_date:
            if self.errors.get('payment_due_date'):
                del self.errors['payment_due_date']
            try:
                payment_due_date = convert_date(payment_due_date, '%d %b %Y', is_new=is_new)
                if payment_due_date < convert_date(
                        self.data['date'], '%d %b %Y %H:%M', is_new=is_new
                ) - timedelta(hours=cleaned_data.get('cancellation_period')):

                    cleaned_data['payment_due_date'] = payment_due_date
                else:
                    self.add_error('payment_due_date', 'Payment due date must '
                                                       'be before cancellation'
                                                       'period starts')
                cleaned_data['payment_due_date'] = payment_due_date
            except ValueError:
                self.add_error(
                    'payment_due_date', 'Invalid date format.  Select from '
                                        'the date picker or enter date in the '
                                        'format dd Mmm YYYY')


        return cleaned_data

    class Meta:
        model = Event
        fields = (
            'name', 'event_type', 'date', 'description', 'location',
            'max_participants', 'contact_person', 'contact_email', 'cost',
            'booking_open', 'payment_open', 'payment_info',
            'payment_due_date', 'cancellation_period'
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
            }
        help_texts = {
            'payment_open': _('Only use this checkbox if the cost is greater than £0'),
            'payment_due_date': _('Only use this field if the cost is greater than £0'),
        }


class SimpleBookingInlineFormSet(BaseInlineFormSet):

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event', None)
        super(SimpleBookingInlineFormSet, self).__init__(*args, **kwargs)
        # this calls _construct_forms()

    def add_fields(self, form, index):
        super(SimpleBookingInlineFormSet, self).add_fields(form, index)
        if form.initial.get('user'):
            form.index = index + 1
            user = form.instance.user
            event_type = form.instance.event.event_type
            available_block = [
                block for block in Block.objects.filter(user=user) if
                block.active_block()
                and block.block_type.event_type == event_type
            ]
            form.available_block = form.instance.block or (
                available_block[0] if available_block else None
            )

            form.fields['user'] = forms.ModelChoiceField(
                queryset=User.objects.all(),
                initial=user,
                widget=forms.Select(attrs={'class': 'hide'})
            )

        form.fields['attended'] = forms.BooleanField(
            widget=forms.CheckboxInput(attrs={
                'class': "regular-checkbox",
                'id': 'checkbox_attended_{}'.format(index)
            }),
            initial=form.instance.attended if form.instance else False,
            required=False
        )
        form.checkbox_attended_id = 'checkbox_attended_{}'.format(index)


SimpleBookingRegisterFormSet = inlineformset_factory(
    Event,
    Booking,
    fields=('attended', 'user'),
    can_delete=False,
    formset=SimpleBookingInlineFormSet,
    extra=0,
)


class StatusFilter(forms.Form):

    status_choice = forms.ChoiceField(
        widget=forms.Select,
        choices=(('OPEN', 'Open bookings only'),
                 ('CANCELLED', 'Cancelled Bookings only'),
                 ('ALL', 'All'),),
    )


class ConfirmPaymentForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = '__all__'
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
                initial=form.instance.booking_open,
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

            form.fields['cost'] = forms.DecimalField(
                widget=forms.TextInput(attrs={
                    'type': 'text',
                    'class': 'form-control studioadmin-list',
                    'aria-describedby': 'sizing-addon3',
                }),
                initial=form.instance.cost,
                required=False
            )

            form.fields['max_participants'] = forms.IntegerField(
                widget=forms.TextInput(attrs={
                    'type': 'text',
                    'class': 'form-control studioadmin-list',
                    'style': 'text-align: center; margin-left: 10;'
                }),
                initial=form.instance.max_participants,
                required=False
            )
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
    fields=('cost', 'max_participants', 'booking_open', 'payment_open'),
    formset=SessionBaseFormSet,
    extra=0,
    can_delete=True)


class SessionAdminForm(forms.ModelForm):

    error_css_class = 'has-error'

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
            queryset=EventType.objects.filter(event_type="CL"),
        )

    def clean(self):
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
        super(SessionAdminForm, self).clean()
        return cleaned_data

    class Meta:
        model = Session
        fields = (
            'name', 'event_type', 'day', 'time', 'description', 'location',
            'max_participants', 'contact_person', 'contact_email', 'cost',
            'booking_open', 'payment_open', 'payment_info',
            'cancellation_period'
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
            }
        help_texts = {
            'payment_open': _('Only use this checkbox if the cost is greater than £0'),
        }


class UploadTimetableForm(forms.Form):
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
                                        'format e.g. Fri 01 May 2015')

        end_date = self.data.get('end_date')
        if end_date:
            if self.errors.get('end_date'):
                del self.errors['end_date']
            try:
                end_date = datetime.strptime(end_date, '%a %d %b %Y').date()
                if end_date >= start_date:
                    cleaned_data['end_date'] = end_date
                else:
                    self.add_error('end_date',
                                   'Cannot be before start date')
            except ValueError:
                self.add_error(
                    'end_date', 'Invalid date format.  Select from '
                                        'the date picker or enter date in the '
                                        'format dd Mmm YYYY')

        return cleaned_data


class ChooseUsersBaseFormSet(BaseModelFormSet):

    def add_fields(self, form, index):
        super(ChooseUsersBaseFormSet, self).add_fields(form, index)

        form.fields['email_user'] = forms.BooleanField(
            widget=forms.CheckboxInput(attrs={
                'class': "regular-checkbox studioadmin-list",
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
                                    initial=settings.DEFAULT_FROM_EMAIL,
                                    required=True,
                                    widget=forms.TextInput(
                                        attrs={'class': 'form-control'}))
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