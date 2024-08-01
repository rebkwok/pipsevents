# -*- coding: utf-8 -*-
import pytz
from datetime import datetime, date
from datetime import timezone as datetime_tz

from crispy_forms.bootstrap import PrependedText, AppendedText
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, LayoutObject, Submit, Fieldset, HTML, Hidden

from django.db.models import Q
from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse
from booking.models import BlockType, BlockVoucher, EventVoucher, Membership, \
    UsedBlockVoucher, UsedEventVoucher, EventType, StripeSubscriptionVoucher


def validate_discount(value):
    if value < 1 or value > 100:
        raise ValidationError('Discount must be between 1% and 100%')


def validate_greater_than_0(value):
    if value == 0:
        raise ValidationError('Must be greater than 0 (leave blank if no '
                              'maximum)')


def validate_amount(value):
    if value <= 0:
        raise ValidationError('Must be greater than 0, leave blank if None')


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
            'members_only',
            'event_types',
            "activated",
            "is_gift_voucher",
            'name',
            'message',
            'purchaser_email'
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
            'discount': 'Discount (%)',
            'name': 'Name (optional, for gift vouchers)',
            'message': 'Message (optional, for gift vouchers)',
        }

        help_texts = {
            'max_per_user': 'Optional: set a limit on the number of times '
                            'this voucher can be used by a single user',
            'max_vouchers': 'Optional: set a limit on the number of times this '
                            'voucher can be used (across ALL users)',
            'start_date': 'Pick from calendar or enter in format '
                          'e.g. 10 Jan 2016',
            'expiry_date': 'Optional: set an expiry date after which the '
                           'voucher will no longer be accepted',
            'event_types': 'Choose event/class types that this voucher can '
                           'be used for',
            'is_gift_voucher': 'For a standard, single use gift voucher, set max uses per user=1, max available vouchers=1, and discount=100%',
            'purchaser_email': 'Read only; purchaser email for gift voucher'
        }

    def __init__(self, *args, **kwargs):
        super(VoucherStudioadminForm, self).__init__(*args, **kwargs)
        self.fields['code'].validators = [validate_code]
        self.fields['discount'].validators = [validate_discount]
        self.fields['max_vouchers'].validators = [validate_greater_than_0]
        self.fields['purchaser_email'].disabled = True

        if "event_types" in self.fields:
            visible_event_types = EventType.objects.visible()
            if self.instance.id and any((set(self.instance.event_types.all()) - set(visible_event_types))):
                self.fields['event_types'].queryset = EventType.objects.all()
            else:
                self.fields['event_types'].queryset = visible_event_types

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
            'members_only',
            'block_types',
            "activated",
            "is_gift_voucher",
            'name',
            'message',
            'purchaser_email'
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
            'discount': 'Discount (%)',
            'name': 'Name (optional, for gift vouchers)',
            'message': 'Message (optional, for gift vouchers)',
        }

        help_texts = {
            'max_per_user': 'Optional: set a limit on the number of times '
                            'this voucher can be used by a single user',
            'max_vouchers': 'Optional: set a limit on the number of times this '
                            'voucher can be used (across ALL users)',
            'start_date': 'Pick from calendar or enter in format '
                          'e.g. 10 Jan 2016',
            'expiry_date': 'Optional: set an expiry date after which the '
                           'voucher will no longer be accepted',
            'block_types': 'Choose block types that this voucher can '
                           'be used for',
            'is_gift_voucher': 'For a standard, single use gift voucher, set max uses per user=1, max available vouchers=1, and discount=100%',
            'purchaser_email': 'Read only; purchaser email for gift voucher'
        }

    def __init__(self, *args, **kwargs):
        super(BlockVoucherStudioadminForm, self).__init__(*args, **kwargs)
        self.fields['code'].validators = [validate_code]
        self.fields['discount'].validators = [validate_discount]
        self.fields['max_vouchers'].validators = [validate_greater_than_0]
        block_types = self.fields['block_types']
        block_types.queryset = BlockType.objects.exclude(identifier="free class").filter(
            Q(active=True) | Q(identifier__iexact="standard")
        )
            
        self.fields['purchaser_email'].disabled = True


    def get_uses(self):
        return UsedBlockVoucher.objects.filter(voucher=self.instance).count()

    def get_old_instance(self, id):
        return BlockVoucher.objects.get(id=id)



class MembershipVoucherForm(forms.ModelForm):

    class Meta:
        model = StripeSubscriptionVoucher
        exclude = ("promo_code_id",)
        labels = {
            "percent_off":  "Discount (%)",
            "amount_off": "Discount amount (£)",
            "duration": "How often will this voucher be applied?",
            "duration_in_months": "How many months will the voucher apply? (Repeating vouchers only)",
            "redeem_by": "End date",
            "active": "Code is active and redeemable",
            "max_redemptions": "Max uses (across all users)",
        }
        widgets = {
            "memberships": forms.CheckboxSelectMultiple(),
            "percent_off": forms.NumberInput(attrs={"onWheel": "event.preventDefault();"}),
            "amount_off": forms.NumberInput(attrs={"onWheel": "event.preventDefault();"})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['memberships'].queryset = Membership.objects.purchasable()
        self.fields['code'].validators = [validate_code]
        self.fields['percent_off'].validators = [validate_discount]
        self.fields['amount_off'].validators = [validate_amount]
        self.fields["new_memberships_only"].initial = False
        self.fields["duration"].choices = [
            ("once", "Once only, applied to the first/next month's membership"),
            ("repeating", "Repeating, applied to the next X months (specify below)"),
            ("forever", "Forever, applied to every month of the membership"),
        ]
        self.fields["redeem_by"] = forms.DateField(
            widget=forms.DateInput(
                attrs={
                    'class': "form-control",
                    'id': 'datepicker',
                    'onchange': "this.form.submit()"},
                format='%d %b %Y'
            ),
            required=False,
            input_formats=['%d %b %Y']
        )
        back_url = reverse('studioadmin:membership_vouchers')

        self.helper = FormHelper()
        self.helper.layout = Layout(
            "code",
            "memberships",
            PrependedText("amount_off", "£"),
            AppendedText("percent_off", "%"),
            "duration",
            "duration_in_months",
            "max_redemptions",
            "redeem_by",
            "active",
            "new_memberships_only",
            Submit('submit', f'Save', css_class="btn btn-success"),
            HTML(f'<a class="btn btn-secondary" href="{back_url}">Back</a>')
        )

    def clean_code(self):
        code = self.cleaned_data["code"].lower().strip()
        if StripeSubscriptionVoucher.objects.filter(code=code).exists():
            self.add_error("code", "Voucher with this code already exists")
        else:
            return code

    def clean(self):
        redeem_by = self.data.get('redeem_by')
        if redeem_by:
            if "redeem_by" in self.errors:   # pragma: no cover
                del self.errors["redeem_by"]

            try:
                redeem_by = datetime.strptime(redeem_by, '%d %b %Y').replace(hour=23, minute=59, tzinfo=datetime_tz.utc)
                self.cleaned_data["redeem_by"] = redeem_by
            except ValueError:
                self.add_error(
                    'redeem_by',
                    'Invalid date format.  Select from the date picker or '
                    'enter date in the format dd Mmm YYYY'
                )
        
        amount_off = self.cleaned_data.get("amount_off")
        percent_off = self.cleaned_data.get("percent_off")

        if len([it for it in [amount_off, percent_off] if it]) != 1:
            for field in ["amount_off", "percent_off"]:
                self.add_error(field, "You must specify a discount as one of % or amount (£)")

