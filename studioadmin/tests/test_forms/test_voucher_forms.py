# -*- coding: utf-8 -*-
import pytz

from model_mommy import mommy

from django.test import TestCase

from booking.models import BlockVoucher, EventVoucher, UsedBlockVoucher, \
    UsedEventVoucher
from studioadmin.forms import BlockVoucherStudioadminForm, \
    VoucherStudioadminForm


class VoucherStudioAdminFormTests(TestCase):

    def setUp(self):
        self.event_type = mommy.make_recipe('booking.event_type_PC')
        self.data = {
            'code': 'test_code',
            'discount': 10,
            'start_date': '01 Jan 2016',
            'expiry_date': '31 Jan 2016',
            'max_vouchers': 20,
            'event_types': [self.event_type.id]
        }

    def test_form_valid(self):
        form = VoucherStudioadminForm(data=self.data)
        self.assertTrue(form.is_valid())

    def test_code_cannot_contain_spaces(self):
        self.data.update({'code': 'test code'})
        form = VoucherStudioadminForm(data=self.data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'code': ['Code must not contain spaces']}
        )

    def test_max_vouchers_must_be_greater_than_0(self):
        """
        Max vouchers must be either > 0 or left blank for no max
        """
        self.data.update({'max_vouchers': 10})
        form = VoucherStudioadminForm(data=self.data)
        self.assertTrue(form.is_valid())

        self.data.update({'max_vouchers': ''})
        form = VoucherStudioadminForm(data=self.data)
        self.assertTrue(form.is_valid())

        self.data.update({'max_vouchers': 0})
        form = VoucherStudioadminForm(data=self.data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'max_vouchers': ['Must be greater than 0 (leave blank if no '
                              'maximum)']}
        )

    def test_discount_validation(self):
        """
        Discount is a % and must be between 1 and 99
        """
        self.data.update({'discount': 0})
        form = VoucherStudioadminForm(data=self.data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'discount': ['Discount must be between 1% and 99%']}
        )

        self.data.update({'discount': 100})
        form = VoucherStudioadminForm(data=self.data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'discount': ['Discount must be between 1% and 99%']}
        )

        self.data.update({'discount': 20.5})
        form = VoucherStudioadminForm(data=self.data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'discount': ['Enter a whole number.']}
        )

        self.data.update({'discount': 77})
        form = VoucherStudioadminForm(data=self.data)
        self.assertTrue(form.is_valid())

    def test_invalid_date_formats(self):
        self.data.update({'start_date': '01 01 2016'})
        form = VoucherStudioadminForm(data=self.data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'start_date': [
                'Invalid date format.  Select from the date picker or enter '
                'date in the format dd Mmm YYYY'
            ]}
        )

        self.data.update({'start_date': '01/01/2016'})
        form = VoucherStudioadminForm(data=self.data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'start_date': [
                'Invalid date format.  Select from the date picker or enter '
                'date in the format dd Mmm YYYY'
            ]}
        )

        self.data.update(
            {'expiry_date': '43 Feb 2016', 'start_date': '01 Jan 2016'}
        )
        form = VoucherStudioadminForm(data=self.data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'expiry_date': [
                'Invalid date format.  Select from the date picker or enter '
                'date in the format dd Mmm YYYY'
            ]}
        )

    def test_start_date_must_be_before_expiry_date(self):
        self.data.update(
            {'expiry_date': '01 Jan 2016', 'start_date': '15 Jan 2016'}
        )
        form = VoucherStudioadminForm(data=self.data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'expiry_date': [
                'Expiry date must be after start date'
            ]}
        )

    def test_cannot_make_max_vouchers_greater_than_number_already_used(self):
        voucher = mommy.make(EventVoucher, max_vouchers=3)
        users = mommy.make_recipe('booking.user', _quantity=3)
        for user in users:
            UsedEventVoucher.objects.create(voucher=voucher, user=user)
        self.data.update({'max_vouchers': 2, 'id': voucher.id})
        form = VoucherStudioadminForm(data=self.data, instance=voucher)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'max_vouchers': [
                'Voucher code has already been used 3 times in total; '
                'set max uses to 3 or greater'
            ]}
        )

        self.data.update({'max_vouchers': 3})
        form = VoucherStudioadminForm(data=self.data, instance=voucher)
        self.assertTrue(form.is_valid())


class BlockVoucherStudioadminFormTests(TestCase):

    def test_only_active_and_non_free_blocktypes_in_choices(self):
        # free_block
        mommy.make_recipe('booking.free_blocktype')
        # inactive_block
        mommy.make_recipe('booking.blocktype', active=False)
        active_blocktypes = mommy.make_recipe('booking.blocktype', _quantity=2)

        form = BlockVoucherStudioadminForm()
        block_types = form.fields['block_types']
        self.assertEqual(
            sorted(list([bt.id for bt in block_types.queryset])),
            sorted([bt.id for bt in active_blocktypes])
        )

    def test_cannot_make_max_vouchers_greater_than_number_already_used(self):
        block_type = mommy.make_recipe('booking.blocktype')
        voucher = mommy.make(BlockVoucher, max_vouchers=3)
        voucher.block_types.add(block_type)
        users = mommy.make_recipe('booking.user', _quantity=3)
        for user in users:
            UsedBlockVoucher.objects.create(voucher=voucher, user=user)
        data = {
            'id': voucher.id,
            'code': 'test_code',
            'discount': 10,
            'start_date': '01 Jan 2016',
            'expiry_date': '31 Jan 2016',
            'max_vouchers': 2,
            'block_types': [block_type.id]
        }

        form = BlockVoucherStudioadminForm(data=data, instance=voucher)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'max_vouchers': [
                'Voucher code has already been used 3 times in total; '
                'set max uses to 3 or greater'
            ]}
        )

        data.update({'max_vouchers': 3})
        form = BlockVoucherStudioadminForm(data=data, instance=voucher)
        self.assertTrue(form.is_valid())
