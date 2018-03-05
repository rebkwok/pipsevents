# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from model_mommy import mommy

from django.urls import reverse
from django.test import TestCase
from django.utils import timezone

from booking.models import BlockVoucher, EventVoucher, UsedBlockVoucher, \
    UsedEventVoucher
from common.tests.helpers import format_content
from studioadmin.tests.test_views.helpers import TestPermissionMixin


class VoucherListViewTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.pc_event_type = mommy.make_recipe('booking.event_type_PC')
        cls.url = reverse('studioadmin:vouchers')

    def test_access(self):
        """
        requires login
        requires staff user
        instructor can't access
        """
        # can't access if not logged in
        resp = self.client.get(self.url)
        redirected_url = reverse('account_login') + "?next={}".format(self.url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

        # can't access if not staff
        self.assertTrue(
            self.client.login(username=self.user.username, password='test')
        )
        resp = self.client.get(self.url)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

        self.assertTrue(
            self.client.login(
                username=self.instructor_user.username, password='test'
            )
        )
        resp = self.client.get(self.url)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        resp = self.client.get(self.url)
        self.assertEquals(resp.status_code, 200)

    def test_vouchers_listed(self):
        # start date in past
        mommy.make(
            EventVoucher, start_date=timezone.now() - timedelta(10), _quantity=2
        )
        # start date in future
        mommy.make(
            EventVoucher, start_date=timezone.now() + timedelta(10), _quantity=2
        )
        # expired
        mommy.make(
            EventVoucher, expiry_date=timezone.now() - timedelta(10), _quantity=2
        )
        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        resp = self.client.get(self.url)
        self.assertEqual(len(resp.context_data['vouchers']), 6)
        self.assertEqual(resp.context_data['sidenav_selection'], 'vouchers')

    def test_vouchers_expired(self):
        """
        Grey out expired/used vouchers
        """
        # active
        voucher = mommy.make(EventVoucher)
        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        resp = self.client.get(self.url)
        self.assertNotIn('class="expired_block"', resp.rendered_content)

        voucher.delete()
        # expired
        voucher = mommy.make(
            EventVoucher, expiry_date=timezone.now() - timedelta(10)
        )
        resp = self.client.get(self.url)
        self.assertIn('class="expired_block"', resp.rendered_content)

        voucher.delete()
        # max used
        voucher = mommy.make(EventVoucher, max_vouchers=1)
        mommy.make(UsedEventVoucher, voucher=voucher)
        resp = self.client.get(self.url)
        self.assertIn('class="expired_block"', resp.rendered_content)


class VoucherCreateViewTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.pc_event_type = mommy.make_recipe('booking.event_type_PC')
        cls.url = reverse('studioadmin:add_voucher')

    def setUp(self):
        super(VoucherCreateViewTests, self).setUp()
        self.data = {
            'code': 'test_code',
            'discount': 10,
            'start_date': '01 Jan 2016',
            'expiry_date': '31 Jan 2016',
            'max_vouchers': 20,
            'event_types': [self.pc_event_type.id]
        }

    def test_access(self):
        """
        requires login
        requires staff user
        instructor can't access
        """
        # can't access if not logged in
        resp = self.client.get(self.url)
        redirected_url = reverse('account_login') + "?next={}".format(self.url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

        # can't access if not staff
        self.assertTrue(
            self.client.login(username=self.user.username, password='test')
        )
        resp = self.client.get(self.url)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

        self.assertTrue(
            self.client.login(
                username=self.instructor_user.username, password='test'
            )
        )
        resp = self.client.get(self.url)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        resp = self.client.get(self.url)
        self.assertEquals(resp.status_code, 200)

    def test_create_voucher(self):
        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        self.assertFalse(EventVoucher.objects.exists())
        resp = self.client.post(self.url, self.data, follow=True)
        self.assertEquals(EventVoucher.objects.count(), 1)
        voucher = EventVoucher.objects.first()
        self.assertEqual(voucher.code, 'test_code')

        self.assertIn(
            'Voucher with code test_code has been created!',
            format_content(resp.rendered_content)
        )

    def test_create_voucher_redirects_to_edit_page(self):
        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        self.assertFalse(EventVoucher.objects.exists())
        resp = self.client.post(self.url, self.data)
        self.assertEquals(EventVoucher.objects.count(), 1)
        voucher = EventVoucher.objects.first()
        self.assertEqual(resp.status_code, 302)
        # redirects to edit page
        self.assertIn(
            reverse('studioadmin:edit_voucher', args=[voucher.id]), resp.url
        )

    def test_create_block_voucher_context(self):
        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        url = reverse('studioadmin:add_block_voucher')
        resp = self.client.get(url, follow=True)

        self.assertTrue(resp.context_data['is_block_voucher'])
        self.assertEqual(
            resp.context_data['sidenav_selection'], 'add_block_voucher'
        )

    def test_create_block_voucher(self):
        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        self.assertFalse(BlockVoucher.objects.exists())
        block_type = mommy.make_recipe('booking.blocktype')
        url = reverse('studioadmin:add_block_voucher')
        data = self.data.copy()
        del data['event_types']
        data.update(block_types=[block_type.id])
        resp = self.client.post(url, data, follow=True)

        self.assertEquals(BlockVoucher.objects.count(), 1)
        voucher = BlockVoucher.objects.first()
        self.assertEqual(voucher.code, 'test_code')

        self.assertIn(
            'Voucher with code test_code has been created!',
            format_content(resp.rendered_content)
        )


class VoucherUpdateViewTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.pc_event_type = mommy.make_recipe('booking.event_type_PC')
        cls.block_type = mommy.make_recipe('booking.blocktype')

    def setUp(self):
        super(VoucherUpdateViewTests, self).setUp()
        self.voucher = mommy.make(
            EventVoucher, code='test_code', discount=10,
            start_date=datetime(2016, 1, 1),
            expiry_date=datetime(2016, 2, 1)
        )
        self.voucher.event_types.add(self.pc_event_type)
        self.data = {
            'id': self.voucher.id,
            'code': self.voucher.code,
            'discount': self.voucher.discount,
            'max_per_user': self.voucher.max_per_user,
            'start_date': '01 Jan 2016',
            'expiry_date': '01 Feb 2016',
            'event_types': [self.pc_event_type.id]
        }

        self.block_voucher = mommy.make(
            BlockVoucher, code='test_code', discount=10,
            start_date=datetime(2016, 1, 1),
            expiry_date=datetime(2016, 2, 1)
        )
        self.block_voucher.block_types.add(self.block_type)
        self.block_data = {
            'id': self.block_voucher.id,
            'code': self.block_voucher.code,
            'discount': self.block_voucher.discount,
            'max_per_user': self.block_voucher.max_per_user,
            'start_date': '01 Jan 2016',
            'expiry_date': '01 Feb 2016',
            'block_types': [self.block_type.id]
        }

    def test_access(self):
        """
        requires login
        requires staff user
        instructor can't access
        """
        url = reverse('studioadmin:edit_voucher', args=[self.voucher.id])

        # can't access if not logged in
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

        # can't access if not staff
        self.assertTrue(
            self.client.login(username=self.user.username, password='test')
        )
        resp = self.client.get(url)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

        self.assertTrue(
            self.client.login(
                username=self.instructor_user.username, password='test'
            )
        )
        resp = self.client.get(url)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        resp = self.client.get(url)
        self.assertEquals(resp.status_code, 200)

    def test_update_voucher(self):
        url = reverse('studioadmin:edit_voucher', args=[self.voucher.id])
        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        self.data.update(code='new_test_code')
        resp = self.client.post(url, self.data, follow=True)
        self.voucher.refresh_from_db()
        self.assertEqual(self.voucher.code, 'new_test_code')

        self.assertIn(
            'Voucher with code new_test_code has been updated!',
            format_content(resp.rendered_content)
        )

    def test_with_no_changes(self):
        url = reverse('studioadmin:edit_voucher', args=[self.voucher.id])
        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        resp = self.client.post(url, self.data, follow=True)
        self.voucher.refresh_from_db()

        self.assertIn(
            'No changes made',
            format_content(resp.rendered_content)
        )

    def test_update_block_voucher(self):
        url = reverse(
            'studioadmin:edit_block_voucher', args=[self.block_voucher.id]
        )
        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        self.block_data.update(code='new_test_code')
        resp = self.client.post(url, self.block_data, follow=True)
        self.block_voucher.refresh_from_db()
        self.assertEqual(self.block_voucher.code, 'new_test_code')

        self.assertIn(
            'Voucher with code new_test_code has been updated!',
            format_content(resp.rendered_content)
        )

    def test_update_block_voucher_with_no_changes(self):
        url = reverse(
            'studioadmin:edit_block_voucher', args=[self.block_voucher.id]
        )
        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        resp = self.client.post(url, self.block_data, follow=True)
        self.voucher.refresh_from_db()

        self.assertIn(
            'No changes made',
            format_content(resp.rendered_content)
        )


class BlockVoucherListViewTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.block_type = mommy.make_recipe('booking.blocktype')
        cls.url = reverse('studioadmin:block_vouchers')

    def test_access(self):
        """
        requires login
        requires staff user
        instructor can't access
        """
        # can't access if not logged in
        resp = self.client.get(self.url)
        redirected_url = reverse('account_login') + "?next={}".format(self.url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

        # can't access if not staff
        self.assertTrue(
            self.client.login(username=self.user.username, password='test')
        )
        resp = self.client.get(self.url)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

        self.assertTrue(
            self.client.login(
                username=self.instructor_user.username, password='test'
            )
        )
        resp = self.client.get(self.url)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        resp = self.client.get(self.url)
        self.assertEquals(resp.status_code, 200)

    def test_vouchers_listed(self):
        # start date in past
        mommy.make(
            BlockVoucher, start_date=timezone.now() - timedelta (10), _quantity=2
        )
        # start date in future
        mommy.make(
            BlockVoucher, start_date=timezone.now() + timedelta (10), _quantity=2
        )
        # expired
        mommy.make(
            BlockVoucher, expiry_date=timezone.now() - timedelta (10), _quantity=2
        )
        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        resp = self.client.get(self.url)
        self.assertEqual(len(resp.context_data['vouchers']), 6)
        self.assertEqual(
            resp.context_data['sidenav_selection'], 'block_vouchers'
        )

    def test_vouchers_expired(self):
        """
        Grey out expired/used vouchers
        """
        # active
        voucher = mommy.make(BlockVoucher)
        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        resp = self.client.get(self.url)
        self.assertNotIn('class="expired_block"', resp.rendered_content)

        voucher.delete()
        # expired
        voucher = mommy.make(
            BlockVoucher, expiry_date=timezone.now() - timedelta(10)
        )
        resp = self.client.get(self.url)
        self.assertIn('class="expired_block"', resp.rendered_content)

        voucher.delete()
        # max used
        voucher = mommy.make(BlockVoucher, max_vouchers=1)
        mommy.make(UsedBlockVoucher, voucher=voucher)
        resp = self.client.get(self.url)
        self.assertIn('class="expired_block"', resp.rendered_content)


class VoucherUsesViewTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(VoucherUsesViewTests, cls).setUpTestData()
        cls.voucher = mommy.make(EventVoucher)
        cls.block_voucher = mommy.make(BlockVoucher)
        cls.voucher_url = reverse(
            'studioadmin:voucher_uses', args=[cls.voucher.pk]
        )
        cls.block_voucher_url = reverse(
            'studioadmin:block_voucher_uses', args=[cls.block_voucher.pk]
        )

    def test_access(self):
        """
        requires login
        requires staff user
        instructor can't access
        """
        # can't access if not logged in
        resp = self.client.get(self.voucher_url)
        redirected_url = reverse('account_login') + \
            "?next={}".format(self.voucher_url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

        # can't access if not staff
        self.assertTrue(
            self.client.login(username=self.user.username, password='test')
        )
        resp = self.client.get(self.voucher_url)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

        self.assertTrue(
            self.client.login(
                username=self.instructor_user.username, password='test'
            )
        )
        resp = self.client.get(self.voucher_url)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        resp = self.client.get(self.voucher_url)
        self.assertEquals(resp.status_code, 200)

    def test_voucher_counts_listed(self):
        users = mommy.make_recipe('booking.user', _quantity=2)
        for user in users:
            mommy.make(
                UsedEventVoucher, voucher=self.voucher, user=user, _quantity=2
            )

        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        resp = self.client.get(self.voucher_url)
        self.assertEqual(len(resp.context_data['user_list']), 2)
        for user_item in resp.context_data['user_list']:
            self.assertEqual(user_item['count'], 2)
        self.assertEqual(resp.context_data['sidenav_selection'], 'vouchers')

    def test_block_voucher_counts_listed(self):
        users = mommy.make_recipe('booking.user', _quantity=2)
        for user in users:
            mommy.make(
                UsedBlockVoucher, voucher=self.block_voucher, user=user,
                _quantity=2
            )

        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        resp = self.client.get(self.block_voucher_url)
        self.assertEqual(len(resp.context_data['user_list']), 2)
        for user_item in resp.context_data['user_list']:
            self.assertEqual(user_item['count'], 2)
        self.assertEqual(
            resp.context_data['sidenav_selection'], 'block_vouchers'
        )