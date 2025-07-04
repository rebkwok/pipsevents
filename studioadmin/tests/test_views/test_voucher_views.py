# -*- coding: utf-8 -*-
from unittest.mock import patch, Mock
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from model_bakery import baker

import pytest

from django.urls import reverse
from django.test import TestCase
from django.utils import timezone

from booking.models import BlockVoucher, EventVoucher, UsedBlockVoucher, \
    UsedEventVoucher, Membership, StripeSubscriptionVoucher
from common.tests.helpers import format_content
from stripe_payments.tests.mock_connector import MockConnector
from studioadmin.tests.test_views.helpers import TestPermissionMixin


pytestmark = pytest.mark.django_db


class VoucherListViewTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.pc_event_type = baker.make_recipe('booking.event_type_PC')
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
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

        # can't access if not staff
        self.assertTrue(
            self.client.login(username=self.user.username, password='test')
        )
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

        self.assertTrue(
            self.client.login(
                username=self.instructor_user.username, password='test'
            )
        )
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_vouchers_listed(self):
        # start date in past
        baker.make(
            EventVoucher, start_date=timezone.now() - timedelta(10), _quantity=2
        )
        # start date in future
        baker.make(
            EventVoucher, start_date=timezone.now() + timedelta(10), _quantity=2
        )
        # expired
        baker.make(
            EventVoucher, expiry_date=timezone.now() - timedelta(10), _quantity=2
        )
        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        resp = self.client.get(self.url)
        self.assertEqual(len(resp.context_data['vouchers']), 6)
        self.assertEqual(resp.context_data['sidenav_selection'], 'event_vouchers')

    def test_vouchers_expired(self):
        """
        Grey out expired/used vouchers
        """
        # active
        voucher = baker.make(EventVoucher)
        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        resp = self.client.get(self.url)
        self.assertNotIn('class="expired_block"', resp.rendered_content)

        voucher.delete()
        # expired
        voucher = baker.make(
            EventVoucher, expiry_date=timezone.now() - timedelta(10)
        )
        resp = self.client.get(self.url)
        self.assertIn('class="expired_block"', resp.rendered_content)

        voucher.delete()
        # max used
        voucher = baker.make(EventVoucher, max_vouchers=1)
        baker.make(UsedEventVoucher, voucher=voucher)
        resp = self.client.get(self.url)
        self.assertIn('class="expired_block"', resp.rendered_content)



class GiftVoucherListViewTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.pc_event_type = baker.make_recipe('booking.event_type_PC')
        cls.block_type = baker.make_recipe('booking.blocktype')
        cls.url = reverse('studioadmin:gift_vouchers')

    def test_all_gift_vouchers_listed(self):
        # gift vouchers
        ev_vouchers = baker.make(
            EventVoucher, start_date=timezone.now() + timedelta(10), is_gift_voucher=True, _quantity=2
        )
        # not gift vouchers
        baker.make(
            EventVoucher, start_date=timezone.now() + timedelta(10), _quantity=2
        )
        # block gift vouchers
        bl_vouchers = baker.make(
            BlockVoucher, start_date=timezone.now() + timedelta (10), is_gift_voucher=True, _quantity=2
        )
        # block non gift vouchers
        bl__not_gift_vouchers = baker.make(
            BlockVoucher, start_date=timezone.now() + timedelta (10), _quantity=2
        )
        for voucher in [*bl__not_gift_vouchers, *bl_vouchers]:
            voucher.block_types.add(self.block_type)
        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        resp = self.client.get(self.url)
        assert len(resp.context_data['vouchers']) == 4
        assert sorted(obj.id for obj in resp.context_data['vouchers']) == sorted(
            obj.id for obj in [*ev_vouchers, *bl_vouchers]
        )
        assert resp.context_data['sidenav_selection'] == 'gift_vouchers'


class VoucherCreateViewTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.pc_event_type = baker.make_recipe('booking.event_type_PC')
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
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

        # can't access if not staff
        self.assertTrue(
            self.client.login(username=self.user.username, password='test')
        )
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

        self.assertTrue(
            self.client.login(
                username=self.instructor_user.username, password='test'
            )
        )
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_create_voucher(self):
        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        self.assertFalse(EventVoucher.objects.exists())
        resp = self.client.post(self.url, self.data, follow=True)
        self.assertEqual(EventVoucher.objects.count(), 1)
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
        self.assertEqual(EventVoucher.objects.count(), 1)
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
        block_type = baker.make_recipe('booking.blocktype')
        url = reverse('studioadmin:add_block_voucher')
        data = self.data.copy()
        del data['event_types']
        data.update(block_types=[block_type.id])
        resp = self.client.post(url, data, follow=True)

        self.assertEqual(BlockVoucher.objects.count(), 1)
        voucher = BlockVoucher.objects.first()
        self.assertEqual(voucher.code, 'test_code')

        self.assertIn(
            'Voucher with code test_code has been created!',
            format_content(resp.rendered_content)
        )


class VoucherUpdateViewTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.pc_event_type = baker.make_recipe('booking.event_type_PC')
        cls.block_type = baker.make_recipe('booking.blocktype')

    def setUp(self):
        super(VoucherUpdateViewTests, self).setUp()
        self.voucher = baker.make(
            EventVoucher, code='test_code', discount=10,
            start_date=datetime(2016, 1, 1, tzinfo=dt_timezone.utc),
            expiry_date=datetime(2016, 2, 1, tzinfo=dt_timezone.utc)
        )
        self.voucher.event_types.add(self.pc_event_type)
        self.data = {
            'id': self.voucher.id,
            'code': self.voucher.code,
            'discount': self.voucher.discount,
            'max_per_user': self.voucher.max_per_user,
            'start_date': '01 Jan 2016',
            'expiry_date': '01 Feb 2016',
            'event_types': [self.pc_event_type.id],
            'activated': True,
            'is_gift_voucher': False,
            'name': '',
            'message': ''
        }

        self.block_voucher = baker.make(
            BlockVoucher, code='test_code', discount=10,
            start_date=datetime(2016, 1, 1, tzinfo=dt_timezone.utc),
            expiry_date=datetime(2016, 2, 1, tzinfo=dt_timezone.utc)
        )
        self.block_voucher.block_types.add(self.block_type)
        self.block_data = {
            'id': self.block_voucher.id,
            'code': self.block_voucher.code,
            'discount': self.block_voucher.discount,
            'max_per_user': self.block_voucher.max_per_user,
            'start_date': '01 Jan 2016',
            'expiry_date': '01 Feb 2016',
            'block_types': [self.block_type.id],
            'activated': True,
            'is_gift_voucher': False,
            'name': '',
            'message': ''
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
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

        # can't access if not staff
        self.assertTrue(
            self.client.login(username=self.user.username, password='test')
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

        self.assertTrue(
            self.client.login(
                username=self.instructor_user.username, password='test'
            )
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

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
        super().setUpTestData()
        cls.block_type = baker.make_recipe('booking.blocktype')
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
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

        # can't access if not staff
        self.assertTrue(
            self.client.login(username=self.user.username, password='test')
        )
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

        self.assertTrue(
            self.client.login(
                username=self.instructor_user.username, password='test'
            )
        )
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_vouchers_listed(self):
        # start date in past
        baker.make(
            BlockVoucher, start_date=timezone.now() - timedelta (10), _quantity=2
        )
        # start date in future
        baker.make(
            BlockVoucher, start_date=timezone.now() + timedelta (10), _quantity=2
        )
        # expired
        baker.make(
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
        voucher = baker.make(BlockVoucher)
        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        resp = self.client.get(self.url)
        self.assertNotIn('class="expired_block"', resp.rendered_content)

        voucher.delete()
        # expired
        voucher = baker.make(
            BlockVoucher, expiry_date=timezone.now() - timedelta(10)
        )
        resp = self.client.get(self.url)
        self.assertIn('class="expired_block"', resp.rendered_content)

        voucher.delete()
        # max used
        voucher = baker.make(BlockVoucher, max_vouchers=1)
        baker.make(UsedBlockVoucher, voucher=voucher)
        resp = self.client.get(self.url)
        self.assertIn('class="expired_block"', resp.rendered_content)


class VoucherUsesViewTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.voucher = baker.make(EventVoucher)
        cls.block_voucher = baker.make(BlockVoucher)
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
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

        # can't access if not staff
        self.assertTrue(
            self.client.login(username=self.user.username, password='test')
        )
        resp = self.client.get(self.voucher_url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

        self.assertTrue(
            self.client.login(
                username=self.instructor_user.username, password='test'
            )
        )
        resp = self.client.get(self.voucher_url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        resp = self.client.get(self.voucher_url)
        self.assertEqual(resp.status_code, 200)

    def test_voucher_counts_listed(self):
        users = baker.make_recipe('booking.user', _quantity=2)
        for user in users:
            baker.make(
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
        self.assertEqual(resp.context_data['sidenav_selection'], 'event_vouchers')

    def test_block_voucher_counts_listed(self):
        users = baker.make_recipe('booking.user', _quantity=2)
        for user in users:
            baker.make(
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


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_voucher_list(client, seller, staff_user):
    baker.make(StripeSubscriptionVoucher, code="foo")
    baker.make(StripeSubscriptionVoucher, code="bar")
    client.force_login(staff_user)
    resp = client.get(reverse("studioadmin:membership_vouchers"))
    assert resp.status_code == 200
    assert resp.context_data["sidenav_selection"] == "membership_vouchers"
    assert len(resp.context_data["vouchers"]) == 2


def test_membership_voucher_create_get(client, seller, staff_user, purchasable_membership):
    client.force_login(staff_user)
    resp = client.get(reverse("studioadmin:add_membership_voucher"))
    assert resp.status_code == 200
    assert list(resp.context_data["form"].fields["memberships"].queryset) == [purchasable_membership]


@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_membership_voucher_create(client, seller, staff_user, purchasable_membership):
    client.force_login(staff_user)
    assert not StripeSubscriptionVoucher.objects.exists()
    data = {
        "code": "Foo",
        "percent_off": 10,
        "active": True,
        "duration": "once",
        "memberships": [purchasable_membership.id]
    }
    resp = client.post(reverse("studioadmin:add_membership_voucher"), data)
    assert resp.status_code == 302
    assert StripeSubscriptionVoucher.objects.exists()
    voucher = StripeSubscriptionVoucher.objects.first()
    assert voucher.code == "foo"
    assert voucher.memberships.count() == 1


@patch("booking.models.membership_models.StripeConnector.create_promo_code")
def test_membership_voucher_create_stripe_error(mock_create_promo_code, client, seller, staff_user, purchasable_membership):
    mock_create_promo_code.side_effect=Exception("bad stripe")

    client.force_login(staff_user)
    assert not StripeSubscriptionVoucher.objects.exists()
    data = {
        "code": "Foo",
        "percent_off": 10,
        "active": True,
        "duration": "once",
        "memberships": [purchasable_membership.id]
    }
    resp = client.post(reverse("studioadmin:add_membership_voucher"), data, follow=True)
    assert not StripeSubscriptionVoucher.objects.exists()
    assert "Stripe promo code could not be created" in resp.rendered_content



@patch("booking.models.membership_models.StripeConnector.get_promo_code")
def test_membership_voucher_detail(mock_get_promo_code, client, seller, staff_user):
    mock_get_promo_code.return_value = Mock(times_redeemed=2)
    baker.make(StripeSubscriptionVoucher, code="foo")
    client.force_login(staff_user)
    resp = client.get(reverse("studioadmin:membership_voucher_detail", args=("foo",)))
    assert resp.status_code == 200
    assert resp.context_data["sidenav_selection"] == "membership_vouchers"
    assert resp.context_data["voucher"].times_used == 2


@patch("booking.models.membership_models.StripeConnector.update_promo_code")
def test_membership_voucher_toggle_active(mock_update_promo_code, client, seller, staff_user):
    voucher = baker.make(StripeSubscriptionVoucher, code="foo")
    assert voucher.active

    client.force_login(staff_user)
    client.get(reverse("studioadmin:membership_voucher_toggle_active", args=(voucher.id,)))
    voucher.refresh_from_db()
    assert not voucher.active

    client.get(reverse("studioadmin:membership_voucher_toggle_active", args=(voucher.id,)))
    voucher.refresh_from_db()
    assert voucher.active
