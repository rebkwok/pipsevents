from django import forms
from django.contrib.auth.models import User
from django.forms.models import modelformset_factory, BaseModelFormSet, \
    inlineformset_factory, BaseInlineFormSet

from booking.models import Block, Booking, Event


class EventBaseFormSet(BaseModelFormSet):

    def add_fields(self, form, index):
        super(EventBaseFormSet, self).add_fields(form, index)

        if form.instance:
            form.fields['booking_open'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={
                    'class': "regular-checkbox",
                    'id': 'booking_open_{}'.format(index)
                }),
                initial=form.instance.booking_open,
                required=False
            )
            form.booking_open_id = 'booking_open_{}'.format(index)

            form.fields['payment_open'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={
                    'class': "regular-checkbox",
                    'id': 'payment_open_{}'.format(index)
                }),
                initial=form.instance.payment_open,
                required=False
            )
            form.payment_open_id = 'payment_open_{}'.format(index)

            form.fields['cost'] = forms.DecimalField(
                widget=forms.TextInput(attrs={
                    'type': 'text',
                    'class': 'form-control',
                    'aria-describedby': 'sizing-addon2',
                }),
                initial=form.instance.cost,
                required=False
            )
            form.fields['max_participants'] = forms.IntegerField(
                widget=forms.TextInput(attrs={
                    'type': 'text',
                    'class': 'form-control',
                    'aria-describedby': 'sizing-addon2',
                    'style': 'text-align: center;'
                }),
                initial=form.instance.max_participants,
                required=False
            )

EventFormSet = modelformset_factory(
    Event,
    fields=(
        'cost', 'max_participants',
        'booking_open', 'payment_open'
    ),
    formset=EventBaseFormSet,
    extra=0)


class EventAdminForm(forms.ModelForm):

    fields = (
        'name', 'event_type', 'date',
        'description', 'booking_open',
        'payment_open', 'cancellation_period'
    )


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