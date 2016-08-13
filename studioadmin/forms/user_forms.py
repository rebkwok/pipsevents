# -*- coding: utf-8 -*-

from django import forms
from django.contrib.auth.models import User
from django.forms.models import inlineformset_factory, BaseInlineFormSet
from django.utils import timezone

from booking.models import Block, Booking, Event, BlockType
from payments.models import PaypalBookingTransaction
from studioadmin.fields import UserBlockModelChoiceField


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

            cancelled_class = 'expired' if \
                form.instance.status == 'CANCELLED' else 'none'

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
            required=False,
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

        form.fields['no_show'] = forms.BooleanField(
            widget=forms.CheckboxInput(attrs={
                'class': "regular-checkbox",
                'id': 'no_show_{}'.format(index)
            }),
            required=False
        )
        form.no_show_id = 'no_show_{}'.format(index)

        if form.instance.id:
            paid_widget = form.fields['paid'].widget
            deposit_paid_widget = form.fields['deposit_paid'].widget
            free_class_widget = form.fields['free_class'].widget
            no_show_widget = form.fields['no_show'].widget

            if form.instance.status == 'CANCELLED':
                # disable no_show for cancelled
                no_show_widget.attrs.update({
                    'class': 'regular-checkbox regular-checkbox-disabled',
                    'OnClick': "javascript:return ReadOnlyCheckBox()"
                })
            elif form.instance.no_show:
                # make checkboxes greyed out but still usable for no-shows
                for widget in [
                    paid_widget, deposit_paid_widget, free_class_widget,
                    no_show_widget
                ]:
                    widget.attrs.update({
                        'class': 'regular-checkbox regular-checkbox-disabled'
                    })


            if form.instance.status == 'CANCELLED' or form.instance.block:
                # also disable payment and free class fields for cancelled and
                # block bookings

                paid_widget.attrs.update({
                    'class': 'regular-checkbox regular-checkbox-disabled',
                    'OnClick': "javascript:return ReadOnlyCheckBox()"
                })
                deposit_paid_widget.attrs.update({
                    'class': 'regular-checkbox regular-checkbox-disabled',
                    'OnClick': "javascript:return ReadOnlyCheckBox()"
                })
                free_class_widget.attrs.update({
                    'class': 'regular-checkbox regular-checkbox-disabled',
                    'OnClick': "javascript:return ReadOnlyCheckBox()"
                })

    def clean(self):
        """
        make sure that block selected is for the correct event type
        and that a block has not been filled
        """
        super(UserBookingInlineFormSet, self).clean()
        if {
            '__all__': ['Booking with this User and Event already exists.']
        } in self.errors:  # pragma: no cover
            pass
        elif any(self.errors):
            return

        block_tracker = {}
        for form in self.forms:
            block = form.cleaned_data.get('block')
            event = form.cleaned_data.get('event')
            free_class = form.cleaned_data.get('free_class')
            status = form.cleaned_data.get('status')
            paid = form.cleaned_data.get('paid')

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

            if block and 'paid' in form.changed_data \
                    and not 'block' in form.changed_data:
                error_msg = 'Cannot make block booking for {} ' \
                            'unpaid'.format(event)
                form.add_error('paid', error_msg)

            elif block and event and status == 'OPEN':
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

            if block and free_class and \
                            block.block_type.identifier != 'free class':
                error_msg = '"Free class" cannot be assigned to a block.'
                form.add_error('free_class', error_msg)


UserBookingFormSet = inlineformset_factory(
    User,
    Booking,
    fields=('paid', 'deposit_paid', 'event', 'block', 'status', 'free_class',
            'no_show'),
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
        free_class_block = BlockType.objects.filter(identifier='free class')
        available_block_types = BlockType.objects.filter(active=True).exclude(
            event_type__in=user_block_event_types
        )
        form.can_buy_block = True if available_block_types else False
        queryset = available_block_types | free_class_block

        if not form.instance.id:
            form.fields['block_type'] = (BlockTypeModelChoiceField(
                queryset=queryset.order_by('event_type__subtype'),
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
                'class': "regular-checkbox",
                'id': 'paid_{}'.format(index)
            }),
            required=False
            )
        form.paid_id = 'paid_{}'.format(index)

    def clean(self):
        for form in self.forms:
            if form.instance.id and 'start_date' in form.changed_data:
                # start date in form is in local time; on BST it will differ
                # from the stored UTC date
                start = form.cleaned_data['start_date']
                startutc = start.astimezone(timezone.utc).replace(microsecond=0)
                origstart = form.initial['start_date'].replace(microsecond=0)
                if startutc == origstart:
                    form.changed_data.remove('start_date')


UserBlockFormSet = inlineformset_factory(
    User,
    Block,
    fields=('paid', 'start_date', 'block_type'),
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
        )
    )
