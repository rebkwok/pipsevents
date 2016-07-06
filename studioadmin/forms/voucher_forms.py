# -*- coding: utf-8 -*-
import pytz
from datetime import datetime

from django import forms
from django.core.exceptions import ValidationError
from booking.models import BlockType, BlockVoucher, EventVoucher, \
    UsedBlockVoucher, UsedEventVoucher


def validate_discount(value):
    if value < 1 or value > 99:
        raise ValidationError('Discount must be between 1% and 99%')


def validate_greater_than_0(value):
    if value == 0:
        raise ValidationError('Must be greater than 0 (leave blank if no '
                              'maximum)')


def validate_code(code):
    if len(code.split()) > 1:
        raise ValidationError('Code must not contain spaces')


class VoucherStudioadminForm(forms.ModelForm):
    class Meta:
        model = EventVoucher
        fields = (
            'code', 'discount', 'start_date', 'expiry_date',
            'max_per_user',
            'max_vouchers',
            'event_types'
        )
        widgets = {
            'code': forms.TextInput(
                attrs={'class': "form-control"}
            ),
            'discount': forms.TextInput(
                attrs={'class': "form-control"}
            ),
            'max_vouchers': forms.TextInput(
                attrs={'class': "form-control"}
            ),
            'max_per_user': forms.TextInput(
                attrs={'class': "form-control"}
            ),
            'start_date': forms.DateInput(
                attrs={
                    'class': "form-control",
                    'id': "datepicker",
                },
                format='%d %b %Y'
            ),
            'expiry_date': forms.DateInput(
                attrs={
                    'class': "form-control",
                    'id': "datepicker1",
                },
                format='%d %b %Y'
            ),
            'event_types': forms.CheckboxSelectMultiple(),
        }
        labels = {
            'discount': 'Discount (%)'
        }

        help_texts = {
            'max_per_user': 'Optional: set a limit on the number of times '
                            'this voucher can be used by a single user',
            'max_vouchers': 'Optional: set a limit on the number of times this '
                            'voucher can be used (across all users)',
            'start_date': 'Pick from calendar or enter in format '
                          'e.g. 10 Jan 2016',
            'expiry_date': 'Optional: set an expiry date after which the '
                           'voucher will no longer be accepted',
            'event_types': 'Choose event/class types that this voucher can '
                           'be used for'
        }

    def __init__(self, *args, **kwargs):
        super(VoucherStudioadminForm, self).__init__(*args, **kwargs)
        self.fields['code'].validators = [validate_code]
        self.fields['discount'].validators = [validate_discount]
        self.fields['max_vouchers'].validators = [validate_greater_than_0]

    def get_uses(self):
        return UsedEventVoucher.objects.filter(voucher=self.instance).count()

    def get_old_instance(self, id):
        return EventVoucher.objects.get(id=id)

    def clean(self):
        super(VoucherStudioadminForm, self).clean()
        cleaned_data = self.cleaned_data
        start_date = self.data.get('start_date')
        expiry_date = self.data.get('expiry_date')

        old = None
        if self.instance.id:
            old = self.get_old_instance(self.instance.id)

        uk = pytz.timezone('Europe/London')

        if start_date:
            if self.errors.get('start_date'):
                del self.errors['start_date']
            try:
                start_date = datetime.strptime(start_date, '%d %b %Y')
                start_date = uk.localize(start_date).astimezone(pytz.utc)
                cleaned_data['start_date'] = start_date
                if old and old.start_date == start_date:
                    self.changed_data.remove('start_date')
            except ValueError:
                self.add_error(
                    'start_date',
                    'Invalid date format.  Select from the date picker or '
                    'enter date in the format dd Mmm YYYY'
                )
                start_date = None

        if expiry_date:
            if self.errors.get('expiry_date'):
                del self.errors['expiry_date']
            try:
                expiry_date = datetime.strptime(expiry_date, '%d %b %Y')
                expiry_date = uk.localize(expiry_date).astimezone(pytz.utc)
                expiry_date = expiry_date.replace(hour=23, minute=59, second=59)
                cleaned_data['expiry_date'] = expiry_date
                if old and old.expiry_date == cleaned_data['expiry_date']:
                    self.changed_data.remove('expiry_date')
            except ValueError:
                self.add_error(
                    'expiry_date',
                    'Invalid date format.  Select from the date picker or '
                    'enter date in the format dd Mmm YYYY')
                expiry_date = None

        if start_date and expiry_date:
            if start_date > expiry_date:
                self.add_error(
                    'expiry_date', 'Expiry date must be after start date')

        max_uses = cleaned_data.get('max_vouchers')
        if self.instance.id and max_uses:
            uses = self.get_uses()
            if uses > max_uses:
                self.add_error(
                    'max_vouchers',
                    'Voucher code has already been used {times_used} times in '
                    'total; set max uses to {times_used} or greater'.format(
                        times_used=uses,
                    )
                )


class BlockVoucherStudioadminForm(VoucherStudioadminForm):

    class Meta:
        model = BlockVoucher
        fields = (
            'code', 'discount', 'start_date', 'expiry_date',
            'max_per_user',
            'max_vouchers',
            'block_types'
        )
        widgets = {
            'code': forms.TextInput(
                attrs={'class': "form-control"}
            ),
            'discount': forms.TextInput(
                attrs={'class': "form-control"}
            ),
            'max_vouchers': forms.TextInput(
                attrs={'class': "form-control"}
            ),
            'max_per_user': forms.TextInput(
                attrs={'class': "form-control"}
            ),
            'start_date': forms.DateInput(
                attrs={
                    'class': "form-control",
                    'id': "datepicker",
                },
                format='%d %b %Y'
            ),
            'expiry_date': forms.DateInput(
                attrs={
                    'class': "form-control",
                    'id': "datepicker1",
                },
                format='%d %b %Y'
            ),
            'block_types': forms.CheckboxSelectMultiple(),
        }
        labels = {
            'discount': 'Discount (%)'
        }

        help_texts = {
            'max_per_user': 'Optional: set a limit on the number of times '
                            'this voucher can be used by a single user',
            'max_vouchers': 'Optional: set a limit on the number of times this '
                            'voucher can be used (across all users)',
            'start_date': 'Pick from calendar or enter in format '
                          'e.g. 10 Jan 2016',
            'expiry_date': 'Optional: set an expiry date after which the '
                           'voucher will no longer be accepted',
            'block_types': 'Choose block types that this voucher can '
                           'be used for'
        }

    def __init__(self, *args, **kwargs):
        super(BlockVoucherStudioadminForm, self).__init__(*args, **kwargs)
        block_types = self.fields['block_types']
        block_types.queryset = BlockType.objects.filter(active=True)\
            .exclude(identifier="free class")

    def get_uses(self):
        return UsedBlockVoucher.objects.filter(voucher=self.instance).count()

    def get_old_instance(self, id):
        return BlockVoucher.objects.get(id=id)
