# -*- coding: utf-8 -*-
import pytz

from datetime import datetime, timedelta

from mock import patch

from model_mommy import mommy

from django.conf import settings
from django.core.urlresolvers import reverse
from django.core import mail
from django.test import TestCase
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone

from booking.models import Voucher
from booking.tests.helpers import _create_session, format_content
from studioadmin.views import VoucherCreateView, VoucherListView, \
    VoucherUpdateView
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
            Voucher, start_date=timezone.now() - timedelta (10), _quantity=2
        )
        # start date in future
        mommy.make(
            Voucher, start_date=timezone.now() + timedelta (10), _quantity=2
        )
        # expired
        mommy.make(
            Voucher, expiry_date=timezone.now() - timedelta (10), _quantity=2
        )
        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        resp = self.client.get(self.url)
        self.assertEqual(len(resp.context_data['vouchers']), 6)
        self.assertEqual(resp.context_data['sidenav_selection'], 'vouchers')


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
        self.assertFalse(Voucher.objects.exists())
        resp = self.client.post(self.url, self.data, follow=True)
        self.assertEquals(Voucher.objects.count(), 1)
        voucher = Voucher.objects.first()
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
        self.assertFalse(Voucher.objects.exists())
        resp = self.client.post(self.url, self.data)
        self.assertEquals(Voucher.objects.count(), 1)
        voucher = Voucher.objects.first()
        self.assertEqual(resp.status_code, 302)
        # redirects to edit page
        self.assertIn(
            reverse('studioadmin:edit_voucher', args=[voucher.id]), resp.url
        )


class VoucherUpdateViewTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.pc_event_type = mommy.make_recipe('booking.event_type_PC')

    def setUp(self):
        super(VoucherUpdateViewTests, self).setUp()
        self.voucher = mommy.make(
            Voucher, code='test_code', discount=10,
            start_date=datetime(2016, 1, 1),
            expiry_date=datetime(2016, 2, 1)
        )
        self.voucher.event_types.add(self.pc_event_type)
        self.data = {
            'id': self.voucher.id,
            'code': self.voucher.code,
            'discount': self.voucher.discount,
            'start_date': '01 Jan 2016',
            'expiry_date': '01 Feb 2016',
            'event_types': [self.pc_event_type.id]
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