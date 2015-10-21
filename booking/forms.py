from datetime import date
from django import forms
from django.conf import settings
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

from django.forms.models import modelformset_factory, BaseModelFormSet, \
    inlineformset_factory, BaseInlineFormSet

from booking.models import Booking, Event, Block, Ticket, TicketedEvent, \
    TicketBooking
from booking.widgets import DateSelectorWidget


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


def set_toggle_attrs(on_text='Yes', off_text='No', label_text=''):
    return {
        'class': 'toggle-checkbox',
        'data-size': 'mini',
        'data-on-color': 'success',
        'data-off-color': 'danger',
        'data-on-text': on_text,
        'data-off-text': off_text,
        'data-label-text': label_text,
    }


class BookingCreateForm(forms.ModelForm):

    class Meta:
        model = Booking
        fields = ['event', ]


class BlockCreateForm(forms.ModelForm):

    class Meta:
        model = Block
        fields = ['block_type', ]


class CreateClassesForm(forms.Form):
    date = forms.DateField(
        label="Date",
        widget=DateSelectorWidget,
        required=False, initial=date.today()
    )

    def clean_date(self):
        if not self.cleaned_data['date']:
            day = self.data.get('date_0')
            month = MONTH_CHOICES.get(int(self.data.get('date_1')))
            year = self.data.get('date_2')
            raise forms.ValidationError(
                _('Invalid date {} {} {}'.format(day, month, year))
            )
        return self.cleaned_data['date']


class EmailUsersForm(forms.Form):
    subject = forms.CharField(max_length=255, required=True)
    from_address = forms.EmailField(max_length=255,
                                    initial=settings.DEFAULT_FROM_EMAIL,
                                    required=True)
    cc = forms.BooleanField(label="Send a copy to this address", initial=True)
    message = forms.CharField(widget=forms.Textarea, required=True)


def get_event_names(event_type):

    def callable():
        event_names = set([event.name for event in Event.objects.filter(
            event_type__event_type=event_type, date__gte=timezone.now()
        ).order_by('name')])
        NAME_CHOICES = [(item, item) for i, item in enumerate(event_names)]
        NAME_CHOICES.insert(0, ('', 'All'))
        return tuple(sorted(NAME_CHOICES))

    return callable


class EventFilter(forms.Form):
    name = forms.ChoiceField(choices=get_event_names('EV'))


class LessonFilter(forms.Form):
    name = forms.ChoiceField(choices=get_event_names('CL'))


def get_user_blocks(user, event_type):
    blocks = [block.id for block in Block.objects.filter(
        block_type__event_type=event_type, user=user
    ) if block.active_block()]
    return Block.objects.filter(id__in=blocks).order_by('start_date')


class BlockModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return "Start date: {}".format(obj.start_date.strftime('%d %b %y'))


class UserModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return "{} {} ({})".format(obj.first_name, obj.last_name, obj.username)


def get_quantity_choices(ticketed_event, current_tickets):

    tickets_left_this_booking = ticketed_event.tickets_left() + current_tickets

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

        current_tickets = ticket_booking.tickets.count()

        self.fields['quantity'] = forms.ChoiceField(
            choices=get_quantity_choices(ticketed_event, current_tickets),
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