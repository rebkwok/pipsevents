# -*- coding: utf-8 -*-
from django import forms
from django.contrib.auth.models import User
from django.utils import timezone
from django.forms.models import inlineformset_factory, BaseInlineFormSet

from booking.models import Booking, Event, Block, BlockType, BlockVoucher, \
    GiftVoucherType, Ticket, TicketBooking


MONTH_CHOICES = {
            1: 'January',
            2: 'February',
            3: 'March',
            4: 'April',
            5: 'May',
            6: 'June',
            7: 'July',
            8: 'August',
            9: 'September',
            10: 'October',
            11: 'November',
            12: 'December',
        }


class BookingCreateForm(forms.ModelForm):

    class Meta:
        model = Booking
        fields = ['event', ]


class BlockTypeChoiceField(forms.ModelChoiceField):

    def label_from_instance(self, obj):
        return '{}{} - quantity {}'.format(
            obj.event_type.subtype,
            ' ({})'.format(obj.identifier) if obj.identifier else '',
            obj.size
        )

    def to_python(self, value):
        if value:
            return BlockType.objects.get(id=value)


class BlockCreateForm(forms.ModelForm):

    class Meta:
        model = Block
        fields = ['block_type', ]

    def __init__(self, *args, **kwargs):
        super(BlockCreateForm, self).__init__(*args, **kwargs)
        self.fields['block_type'] = BlockTypeChoiceField(
            queryset=BlockType.objects.filter(active=True)
        )


def get_event_names(event_type):

    def callable():
        event_names = set([event.name for event in Event.objects.filter(
            event_type__event_type=event_type, date__gte=timezone.now()
        ).order_by('name')])
        NAME_CHOICES = sorted([(item, item) for i, item in enumerate(event_names)])
        NAME_CHOICES.insert(0, ("all", "All"))
        return tuple(NAME_CHOICES)
    return callable


class BaseFilter(forms.Form):

    date_selection = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "class": "form-control form-control-sm filter-form-control filter-form-control-dates",
                "placeholder": "Click to select dates",
            }
        ),
        max_length=255, label="Dates",
        required=False
    )

    spaces_only = forms.BooleanField(
        widget=forms.CheckboxInput(
            attrs={"class": "form-check-input", "onclick": "form.submit();"}
        ),
        required=False,
        initial=False
    )


class EventFilter(BaseFilter):
    name = forms.ChoiceField(
        choices=get_event_names('EV'),
        widget=forms.Select(attrs={"class": "form-control form-control-sm filter-form-control"})
    )
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["spaces_only"].label = "Hide full events"


class LessonFilter(BaseFilter):
    name = forms.ChoiceField(
        choices=get_event_names('CL'),
        widget=forms.Select(attrs={"class": "form-control form-control-sm filter-form-control"})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["spaces_only"].label = "Hide full classes"


class RoomHireFilter(BaseFilter):
    name = forms.ChoiceField(
        choices=get_event_names('RH'),
        widget=forms.Select(attrs={"class": "form-control form-control-sm filter-form-control"})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["spaces_only"].label = "Hide full"


class OnlineTutorialFilter(forms.Form):
    name = forms.ChoiceField(
        choices=get_event_names('OT'),
        widget=forms.Select(attrs={"class": "form-control form-control-sm filter-form-control"})
    )


def get_quantity_choices(ticketed_event, ticket_booking):

    current_tickets = ticket_booking.tickets.count()
    if ticket_booking.purchase_confirmed:
        tickets_left_this_booking = ticketed_event.tickets_left() + \
                                    current_tickets
    else:
        tickets_left_this_booking = ticketed_event.tickets_left()

    if ticketed_event.max_ticket_purchase:
        if tickets_left_this_booking > ticketed_event.max_ticket_purchase:
            max_choice = ticketed_event.max_ticket_purchase
        else:
            max_choice = tickets_left_this_booking
    elif ticketed_event.max_tickets:
        max_choice = tickets_left_this_booking
    else:
        max_choice = 100

    choices = [(i, i) for i in range(1, max_choice+1)]
    choices.insert(0, (0, '------'))
    return tuple(choices)


class TicketPurchaseForm(forms.Form):

    def __init__(self, *args, **kwargs):
        ticketed_event = kwargs.pop('ticketed_event')
        ticket_booking = kwargs.pop('ticket_booking')
        super(TicketPurchaseForm, self).__init__(*args, **kwargs)

        self.fields['quantity'] = forms.ChoiceField(
            choices=get_quantity_choices(ticketed_event, ticket_booking),
            widget=forms.Select(
                attrs={
                    "onchange": "ticket_purchase_form.submit();",
                    "class": "form-control input-sm",
                },
            ),
        )

class TicketInlineFormSet(BaseInlineFormSet):

    def __init__(self, *args, **kwargs):
        self.ticketed_event = kwargs.pop('ticketed_event', None)
        super(TicketInlineFormSet, self).__init__(*args, **kwargs)

    def add_fields(self, form, index):
        super(TicketInlineFormSet, self).add_fields(form, index)

        form.fields['extra_ticket_info'].widget = forms.TextInput(
            attrs={"class": "form-control ticket-control"}
        )
        form.fields['extra_ticket_info'].label = \
            self.ticketed_event.extra_ticket_info_label
        form.fields['extra_ticket_info'].help_text = \
            self.ticketed_event.extra_ticket_info_help
        form.fields['extra_ticket_info'].required = \
            self.ticketed_event.extra_ticket_info_required
        form.fields['extra_ticket_info1'].widget = forms.TextInput(
            attrs={"class": "form-control ticket-control"}
        )
        form.fields['extra_ticket_info1'].label = \
            self.ticketed_event.extra_ticket_info1_label
        form.fields['extra_ticket_info1'].help_text = \
            self.ticketed_event.extra_ticket_info1_help
        form.fields['extra_ticket_info1'].required = \
            self.ticketed_event.extra_ticket_info1_required

        form.index = index + 1


TicketFormSet = inlineformset_factory(
    TicketBooking,
    Ticket,
    fields=('extra_ticket_info', 'extra_ticket_info1'),
    can_delete=False,
    formset=TicketInlineFormSet,
    extra=0,
)


class UserModelChoiceField(forms.ModelChoiceField):

    def label_from_instance(self, obj):
        return "{} {} ({})".format(obj.first_name, obj.last_name, obj.username)

    def to_python(self, value):
        if value:
            return User.objects.get(id=value)


class TicketBookingAdminForm(forms.ModelForm):

    class Meta:
        model = Block
        fields = ('__all__')

    def __init__(self, *args, **kwargs):
        super(TicketBookingAdminForm, self).__init__(*args, **kwargs)
        self.fields['user'] = UserModelChoiceField(
            queryset=User.objects.all().order_by('first_name')
        )


class WaitingListUserAdminForm(forms.ModelForm):

    class Meta:
        model = Block
        fields = ('__all__')

    def __init__(self, *args, **kwargs):
        super(WaitingListUserAdminForm, self).__init__(*args, **kwargs)
        self.fields['user'] = UserModelChoiceField(
            queryset=User.objects.all().order_by('first_name')
        )


class VoucherForm(forms.Form):

    code = forms.CharField(
        label='Got a voucher code?',
        widget=forms.TextInput(
            attrs={"class": "form-control input-xs voucher"}
        ),
    )


class BookingVoucherForm(forms.Form):

    booking_code = forms.CharField(
        label='Got a voucher code?',
        widget=forms.TextInput(
            attrs={"class": "form-control input-xs voucher"}
        ),
    )


class BlockVoucherForm(forms.Form):

    block_code = forms.CharField(
        label='Got a voucher code?',
        widget=forms.TextInput(
            attrs={"class": "form-control input-xs voucher"}
        ),
    )


class GiftVoucherForm(forms.Form):

    voucher_type = forms.ModelChoiceField(
        label="Voucher for:",
        queryset=GiftVoucherType.objects.filter(active=True),
        widget=forms.Select(attrs={"class": "form-control"})
    )
    user_email = forms.EmailField(
        label="Email address:",
        widget=forms.TextInput(attrs={"class": "form-control"})
    )
    user_email1 = forms.EmailField(
        label="Confirm email address:",
        widget=forms.TextInput(attrs={"class": "form-control"})
    )
    recipient_name = forms.CharField(
        label="Recipient name to display on voucher (optional):",
        widget=forms.TextInput(attrs={"class": "form-control"}),
        required=False
    )
    message = forms.CharField(
        label="Message to display on voucher (optional):",
        widget=forms.Textarea(attrs={"class": "form-control", 'rows': 4}),
        required=False,
        max_length=500,
        help_text="Max 500 characters"
    )

    def __init__(self, **kwargs):
        user = kwargs.pop("user", None)
        instance = kwargs.pop("instance", None)
        super().__init__(**kwargs)
        if instance:
            self.instance = instance
            self.fields["user_email"].initial = instance.purchaser_email
            self.fields["user_email1"].initial = instance.purchaser_email

            if instance.activated:
                self.fields["voucher_type"].disabled = True
                self.fields["user_email"].disabled = True
                self.fields["user_email1"].disabled = True

            if isinstance(instance, BlockVoucher):
                self.fields["voucher_type"].initial = GiftVoucherType.objects.get(block_type=instance.block_types.first()).id
            else:
                self.fields["voucher_type"].initial = GiftVoucherType.objects.get(event_type=instance.event_types.first()).id

            self.fields["recipient_name"].initial = instance.name
            self.fields["message"].initial = instance.message
        elif user:
            self.fields["user_email"].initial = user.email
            self.fields["user_email1"].initial = user.email

    def clean_user_email(self):
        return self.cleaned_data.get('user_email').strip()

    def clean_user_email1(self):
        return self.cleaned_data.get('user_email1').strip()

    def clean(self):
        user_email = self.cleaned_data["user_email"]
        user_email1 = self.cleaned_data["user_email1"]
        if user_email != user_email1:
            self.add_error("user_email1", "Email addresses do not match")

