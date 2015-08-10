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

from booking.models import Block, Booking, Event, EventType, BlockType
from timetable.models import Session
from payments.models import PaypalBookingTransaction


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
        'booking_open', 'payment_open', 'advance_payment_required'
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


        return cleaned_data

    class Meta:
        model = Event
        fields = (
            'name', 'event_type', 'date', 'description', 'location',
            'max_participants', 'contact_person', 'contact_email', 'cost',
            'external_instructor',
            'booking_open', 'payment_open', 'advance_payment_required', 'payment_info',
            'payment_due_date', 'cancellation_period',
            'email_studio_when_booked',
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
                                          'automatically cancelled')
        }


class BookingRegisterInlineFormSet(BaseInlineFormSet):

    def add_fields(self, form, index):
        super(BookingRegisterInlineFormSet, self).add_fields(form, index)

        if form.instance.id:
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
            available_block_ids = [block.id for block in available_block
                                   ]
            form.fields['block'] = UserBlockModelChoiceField(
                queryset=Block.objects.filter(id__in=available_block_ids),
                widget=forms.Select(attrs={'class': 'form-control input-sm studioadmin-list'}),
                required=False
            )

            form.fields['user'] = forms.ModelChoiceField(
                queryset=User.objects.all(),
                initial=user,
                widget=forms.Select(attrs={'class': 'hide'})
            )

            form.fields['paid'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={
                    'class': "regular-checkbox",
                    'id': 'checkbox_paid_{}'.format(index)
                }),
                required=False
            )
            form.checkbox_paid_id = 'checkbox_paid_{}'.format(index)

        form.fields['attended'] = forms.BooleanField(
            widget=forms.CheckboxInput(attrs={
                'class': "regular-checkbox",
                'id': 'checkbox_attended_{}'.format(index)
            }),
            initial=False,
            required=False
        )
        form.checkbox_attended_id = 'checkbox_attended_{}'.format(index)


SimpleBookingRegisterFormSet = inlineformset_factory(
    Event,
    Booking,
    fields=('attended', 'user', 'paid', 'block'),
    can_delete=False,
    formset=BookingRegisterInlineFormSet,
    extra=0,
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
            'external_instructor',
            'booking_open', 'payment_open', 'advance_payment_required',
            'payment_info', 'cancellation_period'
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
                                          'automatically cancelled')
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
        return "Block type: {}; {} left".format(
            obj.block_type.event_type, obj.block_type.size - obj.bookings_made()
        )
    def to_python(self, value):
        if value:
            return Block.objects.get(id=value)


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
                    empty_label="---Choose from user's available active blocks---"
                ))
            else:
                form.fields['block'] = (UserBlockModelChoiceField(
                    queryset=Block.objects.filter(id=form.instance.block.id),
                    widget=forms.Select(attrs={'class': '{} form-control input-sm'.format(cancelled_class)}),
                    required=False,
                    empty_label="---Unselect block (change booking to unpaid)---"
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
                ).filter(booking_open=True).exclude(
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
        form.paid_id = 'paid_{}'.format(index)

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

            if block and event:
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
    fields=('paid', 'event', 'block', 'status', 'free_class'),
    can_delete=False,
    formset=UserBookingInlineFormSet,
    extra=1,
)


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
            form.fields['block_type'] = (forms.ModelChoiceField(
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
