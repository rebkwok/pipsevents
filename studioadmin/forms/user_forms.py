# -*- coding: utf-8 -*-
import pytz

from datetime import datetime
from datetime import timezone as dt_timezone

from django import forms
from django.contrib.auth.models import User
from django.forms.models import inlineformset_factory, BaseInlineFormSet
from django.utils import timezone

from crispy_forms.bootstrap import PrependedText
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column

from booking.context_helpers import get_blocktypes_available_to_book
from booking.models import Block, Booking, Event, BlockType, UserMembership
from studioadmin.fields import UserBlockModelChoiceField


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
        super().add_fields(form, index)
        free_class_block = BlockType.objects.filter(identifier__icontains='free', size=1)
        available_user_block_types = get_blocktypes_available_to_book(self.user)
        form.can_buy_block = bool(available_user_block_types)
        queryset = available_user_block_types | free_class_block
        form.fields['start_date'] = forms.DateField(
            widget=forms.DateInput(
                attrs={
                    'class': "form-control form-control-sm blockdatepicker",
                    'style': 'text-align: center; font-size: small;'
                },
                format='%d %b %Y',
            ),
            required=False,
        )
        form.fields['extended_expiry_date'] = forms.DateField(
            widget=forms.DateInput(
                attrs={
                    'class': "form-control form-control-sm blockdatepicker",
                    'style': 'text-align: center; font-size: small;'
                },
                format='%d %b %Y',
            ),
            required=False,
        )

        if not form.instance.id:
            form.fields['block_type'] = (BlockTypeModelChoiceField(
                queryset=queryset.order_by('event_type__subtype'),
                widget=forms.Select(attrs={'class': 'form-control form-control-sm input-sm'}),
                required=True,
                empty_label="---Choose block type---"
            ))

        else:
            # only allow deleting blocks if not yet paid or unused free/transfer
            identifier = form.instance.block_type.identifier
            deletable = identifier and \
                        (identifier == 'free class'
                         or identifier.startswith('transferred')) \
                        and not form.instance.bookings.exists()
            if not form.instance.paid or deletable:
                form.fields['DELETE'] = forms.BooleanField(
                    widget=forms.CheckboxInput(attrs={
                        'class': 'delete-checkbox studioadmin-list',
                        'id': 'DELETE_{}'.format(index)
                    }),
                    required=False
                )
            else:
                form.fields['DELETE'] = forms.BooleanField(
                    widget=forms.CheckboxInput(attrs={
                        'class': 'delete-checkbox-disabled studioadmin-list',
                        'disabled': 'disabled',
                        'id': 'DELETE_{}'.format(index)
                    }),
                    required=False
                )
            form.DELETE_id = 'DELETE_{}'.format(index)

        form.fields['paid'] = forms.BooleanField(
            widget=forms.CheckboxInput(attrs={
                'class': "form-check-input",
                'id': 'paid_{}'.format(index)
            }),
            required=False
            )
        form.paid_id = 'paid_{}'.format(index)

    def _convert_date(self, datestring):
        date_obj = datetime.strptime(datestring, '%d %b %Y')
        date_obj = pytz.utc.localize(date_obj)
        date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
        return date_obj

    def clean(self):
        for i, form in enumerate(self.forms):
            for date_field in ["start_date", "extended_expiry_date"]:
                if date_field in form.errors:  # convert start date
                    form_date_string = form.data[f"blocks-{i}-{date_field}"]
                    try:
                        converted_date = self._convert_date(form_date_string)
                    except ValueError:
                        return  # if we can't convert the date entered
                    del form.errors[date_field]
                    form.cleaned_data[date_field] = converted_date

                if form.instance.id and date_field in form.changed_data:
                    cleaned_date = form.cleaned_data[date_field]
                    if cleaned_date and form.initial[date_field]:
                        # dates in form are in local time; on BST it will differ
                        # from the stored UTC date
                        cleaned_date_utc = cleaned_date.astimezone(dt_timezone.utc).replace(
                            hour=0, minute=0, second=0, microsecond=0
                        )
                        orig_date = form.initial[date_field].replace(
                            hour=0, minute=0, second=0, microsecond=0
                        )
                        if cleaned_date_utc == orig_date:
                            form.changed_data.remove(date_field)
                    setattr(form.instance, date_field, cleaned_date)


UserBlockFormSet = inlineformset_factory(
    User,
    Block,
    fields=('paid', 'start_date', 'extended_expiry_date', 'block_type'),
    can_delete=True,
    formset=UserBlockInlineFormSet,
    extra=1,
)


class UserListSearchForm(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(
            attrs={
                'placeholder': 'Search first, last and username',
                'style': 'width: 250px;'
            }
        ),
        required=False
    )


class AddBookingForm(forms.ModelForm):

    send_confirmation = forms.BooleanField(
            widget=forms.CheckboxInput(attrs={'class': "form-check-input"}),
            initial=False,
            required=False
        )

    class Meta:
        model = Booking
        fields = (
            'user', 'event',
            'paid', 'status', 'no_show', 'instructor_confirmed_no_show', 'attended', 'block', 'membership',
            'free_class'
        )

        widgets = {
            'user': forms.HiddenInput(),
            'paid': forms.CheckboxInput(attrs={'class': "form-check-input"}),
            'status': forms.Select(
                attrs={'class': "form-control input-sm"}
            ),
            'no_show': forms.CheckboxInput(attrs={'class': "form-check-input"}),
            'instructor_confirmed_no_show': forms.CheckboxInput(attrs={'class': "form-check-input"}),
            'attended': forms.CheckboxInput(attrs={'class': "form-check-input"}),
            'free_class': forms.CheckboxInput(attrs={'class': "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super(AddBookingForm, self).__init__(*args, **kwargs)

        self.fields['user'].initial = self.user.id
        self.fields['no_show'].helptext = "No show OR late cancellation (after allowed period)"
        self.fields['instructor_confirmed_no_show'].label = "No-show confirmed"
        self.fields['instructor_confirmed_no_show'].helptext = "True no-show, marked by instructor in class"

        already_booked = self.user.bookings.values_list("event_id", flat=True)
        self.fields['event'] = forms.ModelChoiceField(
            queryset=Event.objects.filter(date__gte=timezone.now())
            .filter(cancelled=False)
            .exclude(id__in=already_booked).order_by('date'),
            widget=forms.Select(attrs={'class': 'form-control input-sm'}),
            required=True
        )

        active_user_blocks = [
            block.id for block in Block.objects.filter(user=self.user)
            if block.active_block()
        ]
        self.has_available_block = True if active_user_blocks else False

        self.fields['block'] = (UserBlockModelChoiceField(
            queryset=Block.objects.filter(id__in=active_user_blocks),
            widget=forms.Select(attrs={'class': 'form-control input-sm'}),
            required=False,
            empty_label="--------None--------"
        ))

        if self.user.has_membership():
            self.fields['membership'] = forms.ModelChoiceField(
                queryset=self.user.memberships.filter(subscription_status="active"),
                widget=forms.Select(attrs={'class': 'form-control input-sm'}),
                required=False,
                empty_label="--------None--------"
            )

        for field in self.fields:
            self.fields[field].widget.attrs.update(
                {'id': 'id_new_{}'.format(field)}
            )

    def clean(self):
        """
        make sure that block selected is for the correct event type
        Add form validation for cancelled bookings
        """
        block = self.cleaned_data.get('block')
        membership = self.cleaned_data.get("membership")
        event = self.cleaned_data.get('event')
        free_class = self.cleaned_data.get('free_class')
        status = self.cleaned_data.get('status')

        if (block or membership) and status == 'CANCELLED':
            error_msg = 'A cancelled booking cannot be assigned to a block/membership.'
            raise forms.ValidationError(error_msg)

        if membership and block:
            raise forms.ValidationError("Select a membership OR block to use (not both)")

        if event.event_type.event_type == 'CL':
            ev_type = "class"
        elif event.event_type.event_type == 'EV':
            ev_type = "event"

        if membership and not membership.valid_for_event(event):
            self.add_error('membership', f"User's membership is not valid for this {ev_type}")

        if block and event.event_type != block.block_type.event_type:
            available_block_type = BlockType.objects.filter(
                event_type=event.event_type
            )
            if not available_block_type:
                error_msg = 'This {} type cannot be block-booked'.format(
                    ev_type
                )
            else:
                error_msg = 'This {} can only be block-booked with a "{}" ' \
                            'block type.'.format(
                    ev_type, available_block_type[0].event_type
                )
            self.add_error('block', error_msg)

        if block and free_class and \
                        block.block_type.identifier != 'free class':
            error_msg = '"Free class" cannot be assigned to a block.'
            self.add_error('free_class', error_msg)


        if membership and free_class:
            self.add_error('free_class', '"Free class" cannot be assigned to a membership.')


class EditPastBookingForm(forms.ModelForm):

    class Meta:
        model = Booking
        fields = (
            'deposit_paid', 'paid', 'status', 'no_show', 'instructor_confirmed_no_show',
            'attended', 'block', 'membership', 'free_class'
        )

        widgets = {
            'deposit_paid': forms.CheckboxInput(attrs={'class': "form-check-input"}),
            'paid': forms.CheckboxInput(attrs={'class': "form-check-input"}),
            'status': forms.Select(
                attrs={'class': "form-control input-sm"}
            ),
            'no_show': forms.CheckboxInput(attrs={'class': "form-check-input"}),
            'instructor_confirmed_no_show': forms.CheckboxInput(attrs={'class': "form-check-input"}),
            'attended': forms.CheckboxInput(attrs={'class': "form-check-input"}),
            'free_class': forms.CheckboxInput(attrs={'class': "form-check-input"})
        }

    def __init__(self, *args, **kwargs):
        super(EditPastBookingForm, self).__init__(*args, **kwargs)
        self.fields['no_show'].helptext = "No show OR late cancellation (after allowed period)"
        self.fields['instructor_confirmed_no_show'].label = "No-show confirmed"
        self.fields['instructor_confirmed_no_show'].helptext = "True no-show, marked by instructor in class"

        # find all blocks for this user that are not full (i.e. that we could
        # use for this booking.  We allow admin users to change a past booking
        # to a block that is expired
        if self.instance.block:
            blocks = [
                block.id for block in Block.objects.filter(
                    user=self.instance.user,
                    block_type__event_type=self.instance.event.event_type)
                if not block.full or block == self.instance.block
            ]
        else:
            blocks = [
                block.id for block in Block.objects.filter(
                    user=self.instance.user,
                    block_type__event_type=self.instance.event.event_type)
                if not block.full
            ]

        self.fields['block'] = (UserBlockModelChoiceField(
            queryset=Block.objects.filter(id__in=blocks),
            widget=forms.Select(attrs={'class': 'form-control input-sm'}),
            required=False,
            empty_label="--------None--------"
        ))

        
        # show options for currently available membership and the instance membership, if different
        next_membership = self.instance.get_next_active_user_membership()
        membership_ids = {next_membership.id} if next_membership else set()
        if self.instance.membership:
            membership_ids.add(self.instance.membership.id)
            
        self.fields['membership'] = forms.ModelChoiceField(
            queryset=UserMembership.objects.filter(id__in=membership_ids),
            widget=forms.Select(attrs={'class': 'form-control input-sm'}),
            required=False,
            empty_label="--------None--------"
        )

        widgets_to_disable_for_cancelled = {
            'attended', 'paid', 'deposit_paid', 'free_class', 'no_show'
        }
        widgets_to_disable_for_blocks_and_memberships = {
            'paid', 'deposit_paid', 'free_class'
        }
        self.disabled_attrs = set()

        if self.instance.status == 'CANCELLED':
            self.disabled_attrs |= widgets_to_disable_for_cancelled
        if self.instance.block or self.instance.membership:
            self.disabled_attrs |= widgets_to_disable_for_blocks_and_memberships

        for field in self.disabled_attrs:
            self.fields[field].disabled = True

    def clean(self):
        for field in self.disabled_attrs:
            self.cleaned_data[field] = getattr(self.instance, field)
        status = self.cleaned_data.get('status')
        free_class = self.cleaned_data.get('free_class')
        attended = self.cleaned_data.get('attended')
        no_show = self.cleaned_data.get('no_show')

        if status == 'CANCELLED' and 'status' in self.changed_data:
            self.cleaned_data['paid'] = False
            self.cleaned_data['block'] = None
            self.cleaned_data['membership'] = None

        block = self.cleaned_data.get('block')
        membership = self.cleaned_data.get('membership')

        ev_type = 'class' \
            if self.instance.event.event_type.event_type == 'CL' else 'event'

        if block and membership:
            if membership and block:
                raise forms.ValidationError("Select a membership OR block to use (not both)")

        if self.instance.event.cancelled:
            base_error_msg = '{} is cancelled. '.format(self.instance.event)
            if block:
                error_msg = 'Cannot assign booking to a block.'
                self.add_error('block', base_error_msg + error_msg)
            if membership:
                error_msg = 'Cannot assign booking to a membership.'
                self.add_error('membership', base_error_msg + error_msg)
            if status == 'OPEN':
                error_msg = 'Cannot reopen booking for cancelled ' \
                            '{}.'.format(ev_type)
                self.add_error('status', base_error_msg + error_msg)

        else:
            if free_class and (
                membership or (block and block.block_type.identifier != 'free class')
            ):
                self.add_error(
                    'free_class', 'Free class cannot be assigned to a block/membership.'
                )

            if (block or membership) and status == 'CANCELLED':
                self.add_error(
                    'block', 'Cannot assign cancelled booking to a block/membership.'
                )

            # this should be prevented by the disabled attribute on the field
            if block and 'paid' in self.changed_data \
                    and 'block' not in self.changed_data:  # pragma: no cover
                self.add_error('paid', 'Cannot make block booking unpaid.')

            if attended and no_show:
                if 'attended' in self.changed_data:
                    self.add_error(
                        'attended',
                        'Booking cannot be both attended and no-show.'
                    )
                if 'no_show' in self.changed_data:
                    self.add_error(
                        'no_show',
                        'Booking cannot be both attended and no-show'
                    )


class EditBookingForm(EditPastBookingForm):

    def __init__(self, *args, **kwargs):
        super(EditBookingForm, self).__init__(*args, **kwargs)

        self.fields['send_confirmation'] = forms.BooleanField(
            widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            initial=False,
            required=False
        )

        active_user_blocks = [
            block.id for block in Block.objects.filter(
                user=self.instance.user,
                block_type__event_type=self.instance.event.event_type)
            if block.active_block()
        ]
        self.has_available_block = True if active_user_blocks else False

        if self.instance.block is not None:
            active_user_blocks.append(self.instance.block.id)

        self.fields['block'] = (UserBlockModelChoiceField(
            queryset=Block.objects.filter(id__in=active_user_blocks),
            widget=forms.Select(attrs={'class': 'form-control input-sm'}),
            required=False,
            empty_label="--------None--------"
        ))


class AttendanceSearchForm(forms.Form):
    start_date = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={
                'id': "datepicker",
                'placeholder': "Start date",
                'style': 'text-align: center',
            },
            format='%d %m %Y',
        ),
        input_formats=['%d %b %Y'],
        required=True,
        label=""
    )
    end_date = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={
                'id': "datepicker1",
                'placeholder': "End date",
                'style': 'text-align: center'
            },
            format='%d %m %Y',
        ),
        input_formats=['%d %b %Y'],
        required=True,
        label=""
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column(
                    PrependedText("start_date", "From", input_size="input-group-sm"),
                    css_class="col-6"
                ),
                Column(
                    PrependedText("end_date", "To", input_size="input-group-sm"),
                    css_class="col-6"
                ),
            ),
            Row(
                Column(Submit('submit', 'Search', css_class="btn btn-sm btn-wm pt-1 pb-1"), css_class="ml-2 mt-1 col-12")
            )

        )
