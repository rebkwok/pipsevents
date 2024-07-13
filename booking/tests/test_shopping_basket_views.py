# -*- coding: utf-8 -*-
import json

from datetime import datetime, timedelta
from decimal import Decimal
from model_bakery import baker
from urllib.parse import urlsplit

from django.core import mail
from django.urls import reverse
from django.test import override_settings, TestCase, RequestFactory
from django.utils import timezone

from accounts.models import DataPrivacyPolicy
from booking.models import Event, Booking, \
    Block, BlockVoucher, EventVoucher, UsedBlockVoucher, UsedEventVoucher
from common.tests.helpers import make_data_privacy_agreement, TestSetupMixin


class ShoppingBasketViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.url = reverse('booking:shopping_basket')

    def setUp(self):
        super().setUp()
        self.client.login(username=self.user.username, password='test')
        baker.make_recipe(
            'booking.booking', event__event_type__event_type='CL',
            event__date=timezone.now() + timedelta(3),
            event__cost=8,
            user=self.user, _quantity=3
        )
        baker.make_recipe(
            'booking.booking', event__event_type__event_type='EV',
            event__date=timezone.now() + timedelta(3),
            event__cost=8,
            user=self.user, _quantity=3
        )
        self.voucher = baker.make(
            EventVoucher, code='foo', discount=10, max_per_user=10
        )
        self.block_voucher = baker.make(
            BlockVoucher, code='foo', discount=10, max_per_user=2
        )
        self.gift_voucher = baker.make(
            EventVoucher, code='gift_booking', discount=100, max_per_user=1
        )
        self.block_gift_voucher = baker.make(
            BlockVoucher, code='gift_block', discount=100, max_per_user=1
        )

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)

        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_data_privacy_required(self):
        # if one exists, user must have signed it
        baker.make(DataPrivacyPolicy, version=None)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            resp.url.startswith(reverse('profile:data_privacy_review'))
        )

        make_data_privacy_agreement(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_only_users_bookings_displayed(self):
        other_user = baker.make_recipe('booking.user')
        baker.make_recipe(
            'booking.booking', user=other_user,
            event__date=timezone.now() + timedelta(3),
            event__cost=8, paid=False
        )

        # 7 unpaid bookings, only 6 for self.user
        self.assertEqual(
            Booking.objects.filter(
                event__date__gte=timezone.now(), paid=False,
                event__payment_open=True, status='OPEN',
                no_show=False, paypal_pending=False
            ).count(), 7
        )

        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['unpaid_bookings']), 6)

    def test_past_unpaid_bookings_not_displayed(self):
        baker.make_recipe('booking.past_booking', user=self.user)

        # 7 unpaid bookings, only 6 future, 1 past
        self.assertEqual(
            Booking.objects.filter(
                paid=False,
                event__payment_open=True, status='OPEN',
                no_show=False, paypal_pending=False
            ).count(), 7
        )

        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['unpaid_bookings']), 6)

    def test_cancelled_bookings_not_displayed(self):
        baker.make_recipe(
            'booking.booking', user=self.user,
            event__date=timezone.now() + timedelta(3),
            event__cost=8, paid=False, status='CANCELLED'
        )
        # 7 unpaid, future bookings (1 cancelled)
        self.assertEqual(
            Booking.objects.filter(
                paid=False, event__date__gte=timezone.now(),
                event__payment_open=True,
                paypal_pending=False
            ).count(), 7
        )

        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['unpaid_bookings']), 6)

    def test_no_show_bookings_not_displayed(self):
        baker.make_recipe(
            'booking.booking', user=self.user,
            event__date=timezone.now() + timedelta(3),
            event__cost=8, paid=False, status='OPEN', no_show=True
        )
        # 7 unpaid open, future bookings (1 no_show)
        self.assertEqual(
            Booking.objects.filter(
                paid=False, event__date__gte=timezone.now(),
                event__payment_open=True, status='OPEN',
                paypal_pending=False
            ).count(), 7
        )

        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['unpaid_bookings']), 6)

    def test_paypal_pending_bookings_not_displayed(self):
        baker.make_recipe(
            'booking.booking', user=self.user,
            event__date=timezone.now() + timedelta(3),
            event__cost=8, paid=False, status='OPEN', paypal_pending=True
        )
        # 7 unpaid open, future bookings (1 paypal_pending_
        self.assertEqual(
            Booking.objects.filter(
                paid=False, event__date__gte=timezone.now(),
                event__payment_open=True, status='OPEN',
                no_show=False
            ).count(), 7
        )

        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['unpaid_bookings']), 6)

    def test_unpaid_bookings_payment_not_open(self):
        ev = Event.objects.first()
        ev.payment_open = False
        ev.save()

        # 6 unpaid open, future bookings
        self.assertEqual(
            Booking.objects.filter(
                paid=False, event__date__gte=timezone.now(),
                status='OPEN', no_show=False, paypal_pending=False
            ).count(), 6
        )

        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['unpaid_bookings']), 5)
        self.assertEqual(
            len(resp.context['unpaid_bookings_payment_not_open']), 1
        )

    def test_unpaid_bookings_non_default_paypal(self):
        ev = Event.objects.first()
        ev.paypal_email = 'new@paypal.test'
        ev.save()

        # 6 unpaid open, future bookings
        self.assertEqual(
            Booking.objects.filter(
                paid=False, event__date__gte=timezone.now(),
                status='OPEN', no_show=False, paypal_pending=False
            ).count(), 6
        )

        with override_settings(PAYMENT_METHOD="paypal"):
            resp = self.client.get(self.url)
            assert resp.status_code == 200
            assert len(resp.context['unpaid_bookings']) == 5
            assert len(resp.context['unpaid_bookings_non_default_paypal']) == 1
        
        # stripe doesn't care about non-default paypal, everything has to go through
        # the one account
        with override_settings(PAYMENT_METHOD="stripe"):
            resp = self.client.get(self.url)
            assert resp.status_code == 200
            assert len(resp.context['unpaid_bookings']) == 6
            assert "unpaid_bookings_non_default_paypal" not in resp.context

    def test_cancellation_warning_shown(self):
        resp = self.client.get(self.url)
        self.assertFalse(resp.context['include_warning'])

        ev = Event.objects.first()
        ev.payment_time_allowed = 6
        ev.date = timezone.now() + timedelta(hours=3)
        ev.save()

        resp = self.client.get(self.url)
        self.assertTrue(resp.context['include_warning'])

    def test_unpaid_blocks_displayed(self):
        baker.make_recipe(
            'booking.block', block_type__cost=20, user=self.user, paid=False
        )
        baker.make_recipe(
            'booking.block', block_type__cost=10, user=self.user, paid=False
        )
        baker.make_recipe(
            'booking.block', block_type__cost=5, user=self.user, paid=True
        )

        with override_settings(PAYMENT_METHOD="paypal"):
            resp = self.client.get(self.url)
            assert resp.context["payment_method"] == "paypal"
            assert len(resp.context_data['unpaid_blocks']) == 2
            assert resp.context_data['total_unpaid_block_cost'] == 30
            assert 'block_voucher_form' in resp.context_data

            paypalform = resp.context_data['blocks_paypalform']

            block_ids_str = ','.join(
                [
                    str(id) for id in Block.objects.order_by('id').filter(paid=False).values_list('id', flat=True)
                    ]
            )
            assert paypalform.initial['custom'] == f'obj=block ids={block_ids_str} usr={self.user.email}'

            for i, block in enumerate(Block.objects.filter(paid=False)):
                assert f'item_name_{i + 1}' in paypalform.initial
                assert paypalform.initial[f'amount_{i + 1}']== block.block_type.cost

        with override_settings(PAYMENT_METHOD="stripe"):
            resp = self.client.get(self.url)
            assert resp.context["payment_method"] == "stripe"
            assert len(resp.context_data['unpaid_blocks']) == 2
            assert resp.context_data['total_unpaid_block_cost'] == 30
            assert 'block_voucher_form' in resp.context_data
            assert 'blocks_paypalform' not in resp.context_data

    def test_block_booking_available(self):
        resp = self.client.get(self.url)
        self.assertFalse(resp.context['block_booking_available'])

        ev_type = Booking.objects.first().event.event_type
        baker.make_recipe(
            'booking.block_5', block_type__event_type=ev_type,
            user=self.user, paid=True, start_date=timezone.now() - timedelta(1)
        )

        resp = self.client.get(self.url)
        self.assertTrue(resp.context['block_booking_available'])

    def test_total_displayed(self):
        resp = self.client.get(self.url)
        # 6 bookings, events each £8
        self.assertEqual(resp.context['total_unpaid_booking_cost'], 48)

    def test_booking_voucher_code(self):
        # valid voucher
        booking = Booking.objects.first()
        ev_type = booking.event.event_type
        self.voucher.event_types.add(ev_type)
        resp = self.client.get(self.url + '?booking_code=foo')
        self.assertIsNone(resp.context.get('booking_voucher_error'))
        self.assertTrue(resp.context['valid_booking_voucher'])
        self.assertEqual(resp.context['times_booking_voucher_used'], 0)

        # 6 bookings, events each £8, one with 10% discount
        self.assertEqual(resp.context['total_unpaid_booking_cost'], Decimal('47.20'))
        self.assertEqual(
            resp.context['voucher_applied_bookings'], [booking.id]
        )
        self.assertIn(
            'Voucher cannot be used for some bookings',
            resp.context['booking_voucher_msg'][0]
        )

        # invalid voucher code
        resp = self.client.get(self.url + '?booking_code=bar')
        self.assertEqual(resp.context['booking_voucher_error'], 'Invalid code')

    def test_remove_booking_voucher_code(self):
        # valid voucher
        booking = Booking.objects.first()
        ev_type = booking.event.event_type
        self.voucher.event_types.add(ev_type)
        resp = self.client.get(self.url + '?booking_code=foo')

        # 6 bookings, events each £8, one with 10% discount
        assert resp.context['total_unpaid_booking_cost'] == Decimal('47.20')
        booking.refresh_from_db()
        assert booking.voucher_code == "foo"

        # remove code
        resp = self.client.get(self.url + '?booking_code=foo&remove_booking_voucher=')
        booking.refresh_from_db()
        assert booking.voucher_code is None
        assert resp.context['total_unpaid_booking_cost'] == Decimal('48.00')

    def test_block_voucher_code(self):
        # valid voucher
        block = baker.make_recipe(
            'booking.block', block_type__cost=20, user=self.user, paid=False
        )
        baker.make_recipe(
            'booking.block', block_type__cost=20, user=self.user, paid=False
        )
        self.block_voucher.block_types.add(block.block_type)
        resp = self.client.get(self.url + '?block_code=foo')
        self.assertIsNone(resp.context.get('block_voucher_error'))
        self.assertTrue(resp.context['valid_block_voucher'])
        self.assertEqual(resp.context['times_block_voucher_used'], 0)

        # 2 bookings, one with 10% discount
        self.assertEqual(resp.context['total_unpaid_block_cost'], Decimal('38.00'))
        self.assertEqual(
            resp.context['voucher_applied_blocks'], [block.id]
        )
        self.assertIn(
            'Voucher cannot be used for some block types',
            resp.context['block_voucher_msg'][0]
        )

        # invalid voucher code
        resp = self.client.get(self.url + '?block_code=bar')
        self.assertEqual(resp.context['block_voucher_error'], 'Invalid code')

    def test_remove_block_voucher_code(self):
        # valid voucher
        block = baker.make_recipe(
            'booking.block', block_type__cost=20, user=self.user, paid=False
        )
        baker.make_recipe(
            'booking.block', block_type__cost=20, user=self.user, paid=False
        )
        self.block_voucher.block_types.add(block.block_type)
        resp = self.client.get(self.url + '?block_code=foo')
        
        # 2 bookings, one with 10% discount
        block.refresh_from_db()
        assert resp.context['total_unpaid_block_cost'] == Decimal('38.00')
        assert block.voucher_code == "foo"

        resp = self.client.get(self.url + '?block_code=foo&remove_block_voucher=')
        block.refresh_from_db()
        assert resp.context['total_unpaid_block_cost'] == Decimal('40.00')
        assert block.voucher_code is None

    def test_booking_voucher_code_expired(self):
        # expired voucher
        booking = Booking.objects.first()
        ev_type = booking.event.event_type
        self.voucher.event_types.add(ev_type)
        self.voucher.start_date = timezone.now() - timedelta(4)
        self.voucher.expiry_date = timezone.now() - timedelta(2)
        self.voucher.save()
        resp = self.client.get(self.url + '?booking_code=foo')
        self.assertEqual(
            resp.context['booking_voucher_error'], 'Voucher code has expired'
        )

    def test_block_voucher_code_expired(self):
        # expired voucher
        block = baker.make_recipe(
            'booking.block', block_type__cost=20, user=self.user, paid=False
        )
        self.block_voucher.block_types.add(block.block_type)
        self.block_voucher.start_date = timezone.now() - timedelta(4)
        self.block_voucher.expiry_date = timezone.now() - timedelta(2)
        self.block_voucher.save()
        resp = self.client.get(self.url + '?block_code=foo')
        self.assertEqual(
            resp.context['block_voucher_error'], 'Voucher code has expired'
        )

    def test_block_voucher_code_not_started(self):
        # expired voucher
        block = baker.make_recipe(
            'booking.block', block_type__cost=20, user=self.user, paid=False
        )
        self.block_voucher.block_types.add(block.block_type)
        self.block_voucher.start_date = timezone.now() + timedelta(4)
        self.block_voucher.expiry_date = timezone.now() + timedelta(20)
        self.block_voucher.save()
        resp = self.client.get(self.url + '?block_code=foo')
        self.assertIn(
            'Voucher code is not valid until', resp.context['block_voucher_error']
        )

    def test_block_voucher_code_not_activated(self):
        # expired voucher
        block = baker.make_recipe(
            'booking.block', block_type__cost=20, user=self.user, paid=False,
        )
        self.block_voucher.activated = False
        self.block_voucher.block_types.add(block.block_type)
        self.block_voucher.save()

        resp = self.client.get(self.url + '?block_code=foo')
        self.assertEqual(
            resp.context['block_voucher_error'], 'Voucher has not been activated yet'
        )

    def test_booking_voucher_used_up_for_user(self):
        booking = Booking.objects.first()
        ev_type = booking.event.event_type
        self.voucher.event_types.add(ev_type)
        self.voucher.max_per_user = 2
        self.voucher.save()
        baker.make(
            UsedEventVoucher, user=self.user, voucher=self.voucher, _quantity=2
        )
        resp = self.client.get(self.url + '?booking_code=foo')
        self.assertEqual(
            resp.context['booking_voucher_error'],
            'Voucher code has already been used the maximum number of times (2)'
        )

    def test_block_voucher_used_up_for_user(self):
        block = baker.make_recipe(
            'booking.block', block_type__cost=20, user=self.user, paid=False
        )
        self.block_voucher.block_types.add(block.block_type)
        self.block_voucher.max_per_user = 2
        self.voucher.save()
        baker.make(
            UsedBlockVoucher, user=self.user, voucher=self.block_voucher, _quantity=2
        )
        resp = self.client.get(self.url + '?block_code=foo')
        self.assertEqual(
            resp.context['block_voucher_error'],
            'Voucher code has already been used the maximum number of times (2)'
        )

    def test_block_voucher_not_valid_for_user(self):
        baker.make_recipe(
            'booking.block', block_type__cost=20, user=self.user, paid=False
        )
        resp = self.client.get(self.url + '?block_code=foo')
        self.assertEqual(
            resp.context['block_voucher_error'],
            'Code is not valid for any of your currently unpaid blocks'
        )

    def test_booking_voucher_will_be_used_up_for_user_with_basket_bookings(self):
        booking = Booking.objects.first()
        ev_type = booking.event.event_type
        self.voucher.event_types.add(ev_type)
        self.voucher.max_per_user = 3
        self.voucher.save()
        baker.make(
            UsedEventVoucher, user=self.user, voucher=self.voucher, _quantity=2
        )
        resp = self.client.get(self.url + '?booking_code=foo')

        # no voucher error b/c voucher is valid for at least one more use
        self.assertIsNone(resp.context.get('booking_voucher_error'))
        self.assertEqual(
            resp.context['booking_voucher_msg'],
            ['Voucher not applied to some bookings; you can only use this '
             'voucher a total of 3 times.']
        )
        # 6 bookings, events each £8, only one with 10% discount applied
        self.assertEqual(resp.context['total_unpaid_booking_cost'], Decimal('47.20'))

    def test_block_voucher_will_be_used_up_for_user_with_basket_blocks(self):
        block = baker.make_recipe(
            'booking.block', block_type__cost=20, user=self.user, paid=False
        )
        block1 = baker.make_recipe(
            'booking.block', block_type__cost=20, user=self.user, paid=False
        )
        self.block_voucher.block_types.add(block.block_type)
        self.block_voucher.block_types.add(block1.block_type)
        self.block_voucher.max_per_user = 2
        self.voucher.save()
        baker.make(
            UsedBlockVoucher, user=self.user, voucher=self.block_voucher
        )
        resp = self.client.get(self.url + '?block_code=foo')

        # no voucher error b/c voucher is valid for at least one more use
        self.assertIsNone(resp.context.get('block_voucher_error'))
        self.assertEqual(
            resp.context['block_voucher_msg'],
            ['Voucher not applied to some blocks; you can only use this '
             'voucher a total of 2 times.']
        )
        # 6 bookings, events each £8, only one with 10% discount applied
        self.assertEqual(resp.context['total_unpaid_block_cost'], Decimal('38.00'))

    def test_booking_voucher_used_max_total_times(self):
        booking = Booking.objects.first()
        ev_type = booking.event.event_type
        self.voucher.event_types.add(ev_type)
        self.voucher.max_vouchers = 4
        self.voucher.save()
        other_user = baker.make_recipe('booking.user')
        baker.make(
            UsedEventVoucher, user=other_user, voucher=self.voucher,
            _quantity=4
        )

        resp = self.client.get(self.url + '?booking_code=foo')
        self.assertEqual(
            resp.context['booking_voucher_error'],
            'Voucher has limited number of total uses and has now expired'
        )
    
    def test_booking_voucher_not_activated_yet(self):
        booking = Booking.objects.first()
        ev_type = booking.event.event_type
        self.voucher.event_types.add(ev_type)
        self.voucher.activated = False
        self.voucher.save()

        resp = self.client.get(self.url + '?booking_code=foo')
        self.assertEqual(
            resp.context['booking_voucher_error'],
            'Voucher has not been activated yet'
        )


    def test_block_voucher_used_max_total_times(self):
        block = baker.make_recipe(
            'booking.block', block_type__cost=20, user=self.user, paid=False
        )
        self.block_voucher.block_types.add(block.block_type)
        self.block_voucher.max_vouchers = 2
        self.block_voucher.save()

        other_user = baker.make_recipe('booking.user')
        baker.make(
            UsedBlockVoucher, user=other_user, voucher=self.block_voucher,
            _quantity=2
        )

        resp = self.client.get(self.url + '?block_code=foo')
        self.assertEqual(
            resp.context['block_voucher_error'],
            'Voucher has limited number of uses and has now expired'
        )
    
    def test_block_voucher_will_be_used_max_total_times(self):
        block_type = baker.make_recipe('booking.blocktype5', cost=20)
        blocks = baker.make_recipe(
            'booking.block', block_type=block_type, user=self.user, paid=False,
            _quantity=2
        )
        self.block_voucher.block_types.add(block_type)
        self.block_voucher.max_vouchers = 2
        self.block_voucher.save()

        other_user = baker.make_recipe('booking.user')
        baker.make(
            UsedBlockVoucher, user=other_user, voucher=self.block_voucher,
            _quantity=1
        )

        resp = self.client.get(self.url + '?block_code=foo')
        assert resp.context['block_voucher_msg'] == [
            'Voucher not applied to some blocks; voucher has limited '
            'number of total uses.'
        ]
        for block in blocks:
            block.refresh_from_db()
        assert sum(1 for bl in blocks if bl.voucher_code == "foo") == 1

    def test_booking_voucher_will_be_used_max_total_times_with_basket_bookings(self):
        ev_types = [
            booking.event.event_type for booking in Booking.objects.all()
        ]
        for ev_type in ev_types:
            self.voucher.event_types.add(ev_type)

        resp = self.client.get(self.url + '?booking_code=foo')

        # 6 bookings, events each £8 with 10% discount applied
        self.assertEqual(resp.context['total_unpaid_booking_cost'], Decimal('43.20'))

        # add max total
        self.voucher.max_vouchers = 10
        self.voucher.save()

        other_user = baker.make_recipe('booking.user')
        baker.make(
            UsedEventVoucher, user=other_user, voucher=self.voucher, _quantity=9
        )

        resp = self.client.get(self.url + '?booking_code=foo')

        # no voucher error b/c voucher is valid for at least one more use
        self.assertIsNone(resp.context['booking_voucher_error'])
        self.assertEqual(
            resp.context['booking_voucher_msg'],
            ['Voucher not applied to some bookings; voucher has limited '
            'number of total uses.']
        )
        # 6 bookings, events each £8, only one with 10% discount applied
        self.assertEqual(resp.context['total_unpaid_booking_cost'], Decimal('47.20'))

    @override_settings(PAYMENT_METHOD="paypal")
    def test_paypal_cart_form_created(self):
        resp = self.client.get(self.url)
        paypalform = resp.context['bookings_paypalform']

        booking_ids_str = ','.join(
            [
                str(id) for id in Booking.objects.values_list('id', flat=True)
            ]
        )
        self.assertEqual(
            paypalform.initial['custom'], 'obj=booking ids={} usr={}'.format(
                booking_ids_str, Booking.objects.first().user.email
            )
        )
        for i, booking in enumerate(Booking.objects.all()):
            self.assertIn('item_name_{}'.format(i + 1) , paypalform.initial)
            self.assertEqual(
                paypalform.initial['amount_{}'.format(i + 1)], 8
            )

    @override_settings(PAYMENT_METHOD="paypal")
    def test_paypal_form_for_single_cart_item(self):
        # single cart item uses a single paypal dict format
        booking = Booking.objects.first()
        Booking.objects.exclude(id=booking.id).delete()

        resp = self.client.get(self.url)
        self.assertEqual(len(resp.context['unpaid_bookings']), 1)
        paypalform = resp.context['bookings_paypalform']

        self.assertEqual(
            paypalform.initial['custom'], 'obj=booking ids={} usr={}'.format(
                booking.id, booking.user.email
            )
        )
        self.assertIn('item_name', paypalform.initial)
        self.assertNotIn('item_name_1', paypalform.initial)
        self.assertEqual(paypalform.initial['amount'], 8)

    @override_settings(PAYMENT_METHOD="paypal")
    def test_paypal_cart_form_created_with_booking_voucher(self):
        booking = Booking.objects.first()
        ev_type = booking.event.event_type
        self.voucher.event_types.add(ev_type)

        resp = self.client.get(self.url + '?booking_code=foo')

        paypalform = resp.context['bookings_paypalform']
        booking_ids_str = ','.join(
            [
                str(id) for id in Booking.objects.values_list('id', flat=True)
                ]
        )
        # voucher only applied to first booking
        self.assertEqual(
            paypalform.initial['custom'],
            f'obj=booking ids={booking_ids_str} usr={self.user.email} cde=foo apd={booking.id}'
        )
        for i, booking in enumerate(Booking.objects.all()):
            self.assertIn('item_name_{}'.format(i + 1), paypalform.initial)

            if i == 0:
                self.assertEqual(
                    paypalform.initial['amount_{}'.format(i + 1)],
                    Decimal('7.20')
                )
            else:
                self.assertEqual(
                    paypalform.initial['amount_{}'.format(i + 1)], 8
                )

    @override_settings(PAYMENT_METHOD="stripe")
    def test_with_booking_voucher_applied(self):
        booking = Booking.objects.first()
        ev_type = booking.event.event_type
        self.voucher.event_types.add(ev_type)

        assert booking.voucher_code is None
        self.client.get(self.url + '?booking_code=foo')
        booking.refresh_from_db()
        assert booking.voucher_code == "foo"

        # applying an invalid code resets the booking's voucher code
        self.client.get(self.url + '?booking_code=unknown_code')
        booking.refresh_from_db()
        assert booking.voucher_code is None

    @override_settings(PAYMENT_METHOD="paypal")
    def test_paypal_cart_form_created_with_block_voucher(self):
        block = baker.make_recipe(
            'booking.block', block_type__cost=20, user=self.user, paid=False
        )
        block1 = baker.make_recipe(
            'booking.block', block_type__cost=20, user=self.user, paid=False
        )
        self.block_voucher.block_types.add(block.block_type)

        resp = self.client.get(self.url + '?block_code=foo')

        paypalform = resp.context['blocks_paypalform']
        booking_ids_str = ','.join(
            [
                str(id) for id in Block.objects.order_by('id').values_list('id', flat=True)
                ]
        )
        # voucher applied to first block
        self.assertEqual(
            paypalform.initial['custom'],
            f'obj=block ids={booking_ids_str} usr={self.user.email} cde=foo apd={block.id}'
        )
        for i, block in enumerate(Block.objects.all()):
            self.assertIn('item_name_{}'.format(i + 1), paypalform.initial)

            if i == 0:
                self.assertEqual(
                    paypalform.initial['amount_1'],
                    Decimal('18.00')
                )
            else:
                self.assertEqual(
                    paypalform.initial['amount_{}'.format(i + 1)], Decimal('20.00')
                )


    @override_settings(PAYMENT_METHOD="stripe")
    def test_block_with_voucher_applied(self):
        block = baker.make_recipe(
            'booking.block', block_type__cost=20, user=self.user, paid=False
        )
        block1 = baker.make_recipe(
            'booking.block', block_type__cost=20, user=self.user, paid=False
        )
        self.block_voucher.block_types.add(block.block_type)

        self.client.get(self.url + '?block_code=foo')
        block.refresh_from_db()
        block1.refresh_from_db()
        assert block.voucher_code == "foo"
        assert block1.voucher_code is None

        self.client.get(self.url + '?block_code=unknown')
        block.refresh_from_db()
        block1.refresh_from_db()
        assert block.voucher_code is None
        assert block1.voucher_code is None

    @override_settings(PAYMENT_METHOD="paypal")
    def test_100_pct_booking_gift_voucher_payment_buttons(self):
        # update button instead of paypal form for a 100% gift voucher
        booking = Booking.objects.first()
        Booking.objects.exclude(id=booking.id).delete()
        ev_type = booking.event.event_type
        self.gift_voucher.event_types.add(ev_type)

        resp = self.client.get(self.url + '?booking_code=gift_booking')
        self.assertEqual(len(resp.context['unpaid_bookings']), 1)

        self.assertNotIn('bookings_paypalform', resp.context_data)
        self.assertEqual(resp.context_data['total_unpaid_booking_cost'], 0)

    @override_settings(PAYMENT_METHOD="paypal")
    def test_100_pct_booking_gift_voucher_payment_buttons_with_unapplied_booking(self):
        # paypal form if there are bookings as well as the gift-voucher applied ones
        bookings = Booking.objects.all()[:2]
        Booking.objects.exclude(id__in=bookings.values_list('id', flat=True)).delete()
        ev_type = bookings[0].event.event_type
        self.gift_voucher.event_types.add(ev_type)

        resp = self.client.get(self.url + '?booking_code=gift_booking')
        self.assertEqual(len(resp.context['unpaid_bookings']), 2    )

        self.assertIn('bookings_paypalform', resp.context_data)
        self.assertEqual(resp.context_data['total_unpaid_booking_cost'], 8)

    @override_settings(PAYMENT_METHOD="paypal")
    def test_100_pct_block_gift_voucher_payment_buttons(self):
        # update button instead of paypal form for a 100% gift voucher
        block = baker.make_recipe(
            'booking.block', block_type__cost=20, user=self.user, paid=False
        )
        self.block_gift_voucher.block_types.add(block.block_type)

        resp = self.client.get(self.url + '?block_code=gift_block')
        self.assertEqual(len(resp.context['unpaid_blocks']), 1)

        self.assertNotIn('block_paypalform', resp.context_data)
        self.assertEqual(resp.context_data['total_unpaid_block_cost'], 0)

    @override_settings(PAYMENT_METHOD="paypal")
    def test_100_pct_block_gift_voucher_payment_buttons_with_unapplied_booking(self):
        # paypal form if there are bookings as well as the gift-voucher applied ones
        block = baker.make_recipe(
            'booking.block', block_type__cost=20, user=self.user, paid=False
        )
        baker.make_recipe(
            'booking.block', block_type__cost=10, user=self.user, paid=False
        )
        self.block_gift_voucher.block_types.add(block.block_type)

        resp = self.client.get(self.url + '?block_code=gift_block')
        self.assertEqual(len(resp.context['unpaid_blocks']), 2)

        self.assertNotIn('block_paypalform', resp.context_data)
        self.assertEqual(resp.context_data['total_unpaid_block_cost'], 10)

    @override_settings(PAYMENT_METHOD="paypal")
    def test_paypal_cart_items_unpaid_bookings(self):
        # If we only have unpaid bookings, add the cart items to the session
        # 6 unpaid bookings, only 6 for self.user
        resp = self.client.get(self.url)
        self.assertEqual(len(resp.context['unpaid_bookings']), 6)
        booking_ids = ','.join(str(booking.id) for booking in self.user.bookings.all().order_by("id"))
        assert self.client.session["cart_items"] == f"obj=booking ids={booking_ids} usr={self.user.email}"

    @override_settings(PAYMENT_METHOD="paypal")
    def test_paypal_cart_items_unpaid_bookings_overridden(self):
        session = self.client.session
        session["cart_items"] = f"obj=booking ids=3,4,5 usr=foo@example.com"
        session.save()
        resp = self.client.get(self.url)
        self.assertEqual(len(resp.context['unpaid_bookings']), 6)
        booking_ids = ','.join(str(booking.id) for booking in self.user.bookings.all().order_by("id"))
        assert self.client.session["cart_items"] == f"obj=booking ids={booking_ids} usr={self.user.email}"

    @override_settings(PAYMENT_METHOD="paypal")
    def test_paypal_cart_items_unpaid_blocks(self):
        # If we only have unpaid blocks, add the cart items to the session
        Booking.objects.all().delete()
        block = baker.make_recipe(
            'booking.block', block_type__cost=5, user=self.user, paid=False
        )
        self.client.get(self.url)
        assert self.client.session["cart_items"] == f"obj=block ids={block.id} usr={self.user.email}"

    @override_settings(PAYMENT_METHOD="paypal")
    def test_paypal_cart_items_bookings_and_blocks(self):
        # If we have both unpaid bookings and blocks, don't add the cart items to the session as
        # we can't be sure which paypal button they'll use
        unpaid = baker.make_recipe(
            'booking.block', block_type__cost=10, user=self.user, paid=False
        )
        baker.make_recipe(
            'booking.block', block_type__cost=5, user=self.user, paid=True
        )
        self.client.get(self.url)
        assert "cart_items" not in self.client.session

        unpaid.delete()
        self.client.get(self.url)
        assert "cart_items" in self.client.session

    @override_settings(PAYMENT_METHOD="paypal")
    def test_paypal_cart_items_deleted_from_session_on_get(self):
        Booking.objects.all().delete()
        self.client.session["cart_items"] = "test"
        self.client.get(self.url)
        assert "cart_items" not in self.client.session


class UpdateBlockBookingsTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.url = reverse('booking:update_block_bookings')
        cls.blocktype_cl_5 = baker.make_recipe('booking.blocktype5')

        # need to specify subtype for free block creation to happen
        cls.blocktype_cl_10 = baker.make_recipe(
            'booking.blocktype10', event_type__subtype="Pole level class",
            assign_free_class_on_completion=True
        )
        # create free block type associated with blocktype_cl_10
        cls.free_blocktype = baker.make_recipe(
            'booking.blocktype', size=1, cost=0,
            event_type=cls.blocktype_cl_10.event_type, identifier='free class'
        )
        cls.pc1 = baker.make_recipe(
            'booking.future_PC', event_type=cls.blocktype_cl_5.event_type,
            cost=10
        )
        cls.pc2 = baker.make_recipe(
            'booking.future_PC', event_type=cls.blocktype_cl_5.event_type,
            cost=10
        )
        cls.ev =  baker.make_recipe('booking.future_EV', cost=10)

    def setUp(self):
        super().setUp()
        self.client.login(username=self.user.username, password='test')

    def test_use_block_for_all_eligible_bookings(self):
        block = baker.make_recipe(
            'booking.block', user=self.user,
            block_type=self.blocktype_cl_5, paid=True
        )
        self.assertTrue(block.active_block())
        for ev in Event.objects.all():
            baker.make_recipe('booking.booking', user=self.user, event=ev)

        # block is eligible for 2 of the 3 bookings
        resp = self.client.post(self.url)
        self.assertEqual(
            Booking.objects.get(user=self.user, event=self.pc1).block, block
        )
        self.assertEqual(
            Booking.objects.get(user=self.user, event=self.pc2).block, block
        )
        self.assertIsNone(
            Booking.objects.get(user=self.user, event=self.ev).block
        )

        split_redirect_url = urlsplit(resp.url)
        self.assertEqual(
            split_redirect_url.path, reverse('booking:shopping_basket')
        )

        # email sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.user.email])
        self.assertIn('Blocks used for 2 bookings', email.subject)

    def test_use_block_for_all_with_no_eligible_booking(self):
        # redirects with code
        for ev in Event.objects.all():
            baker.make_recipe('booking.booking', user=self.user, event=ev)

        self.client.post(self.url)

        # no valid blocks
        for booking in Booking.objects.filter(user=self.user):
            self.assertIsNone(booking.block)

        # no email sent
        self.assertEqual(len(mail.outbox), 0)

    def test_use_block_for_all_with_voucher_codes(self):
        # redirects with code
        for ev in Event.objects.all():
            baker.make_recipe('booking.booking', user=self.user, event=ev)

        resp = self.client.post(
            self.url, {'booking_code': 'bar', 'block_code': 'foo'}
        )

        # no valid blocks
        for booking in Booking.objects.filter(user=self.user):
            self.assertIsNone(booking.block)

        split_redirect_url = urlsplit(resp.url)
        self.assertEqual(
            split_redirect_url.path, reverse('booking:shopping_basket')
        )
        self.assertIn('booking_code=bar', split_redirect_url.query)
        self.assertIn('block_code=foo', split_redirect_url.query)

    def test_use_block_for_all_with_more_bookings_than_blocks(self):
        baker.make_recipe(
            'booking.future_PC', event_type=self.blocktype_cl_5.event_type,
            cost=10, _quantity=6
        )
        block = baker.make_recipe(
            'booking.block', user=self.user,
            block_type=self.blocktype_cl_5, paid=True
        )
        self.assertTrue(block.active_block())
        for ev in Event.objects.all():
            baker.make_recipe('booking.booking', user=self.user, event=ev)

        self.assertEqual(Booking.objects.filter(user=self.user).count(), 9)
        # 8 bookings are eligible for block booking
        self.assertEqual(
            Booking.objects.filter(
                user=self.user, event__event_type=block.block_type.event_type
            ).count(), 8
        )
        self.client.post(self.url)
        # 5 bookings are updated with available blocks
        self.assertEqual(
            Booking.objects.filter(user=self.user, block__isnull=False).count(),
            5
        )

    def test_use_block_for_all_uses_last_block_free_class_created(self):
        baker.make_recipe(
            'booking.future_PC', event_type=self.blocktype_cl_10.event_type,
            cost=10, _quantity=11
        )

        # free class created and used
        block = baker.make_recipe(
            'booking.block', user=self.user,
            block_type=self.blocktype_cl_10, paid=True,
        )
        self.assertTrue(block.active_block())

        for ev in Event.objects.all():
            baker.make_recipe('booking.booking', user=self.user, event=ev)

        self.assertEqual(Booking.objects.filter(user=self.user).count(), 14)
        # 11 bookings are eligible for block booking
        self.assertEqual(
            Booking.objects.filter(
                user=self.user, event__event_type=block.block_type.event_type
            ).count(), 11
        )
        self.client.post(self.url)
        # 10 bookings are updated with available blocks,
        # 10 from existing block, 1 free block created and used
        self.assertEqual(
            Booking.objects.filter(user=self.user, block__isnull=False).count(),
            11
        )
        self.assertEqual(
            Block.objects.latest('id').block_type, self.free_blocktype
        )

    def test_uses_last_block_free_class_block_already_exists(self):
        baker.make_recipe(
            'booking.future_PC', event_type=self.blocktype_cl_10.event_type,
            cost=10, _quantity=11
        )

        block = baker.make_recipe(
            'booking.block', user=self.user,
            block_type=self.blocktype_cl_10, paid=True
        )
        # free related block already exists
        free_block = baker.make_recipe(
            'booking.block', user=self.user,
            block_type=self.free_blocktype, paid=True, parent=block
        )
        self.assertTrue(block.active_block())
        self.assertTrue(free_block.active_block())

        for ev in Event.objects.all():
            baker.make_recipe('booking.booking', user=self.user, event=ev)

        self.assertEqual(Booking.objects.filter(user=self.user).count(), 14)
        # 11 bookings are eligible for block booking with block or free block
        self.assertEqual(
            Booking.objects.filter(
                user=self.user, event__event_type=block.block_type.event_type
            ).count(), 11
        )
        self.assertEqual(
            Booking.objects.filter(
                user=self.user, event__event_type=free_block.block_type.event_type
            ).count(), 11
        )
        self.client.post(self.url)
        # 10 bookings are updated with available blocks,
        # 10 from existing block, 1 free block used
        self.assertEqual(
            Booking.objects.filter(user=self.user, block__isnull=False).count(),
            11
        )
        # no additional free block created
        self.assertEqual(Block.objects.count(), 2)


class SubmitZeroBookingPaymentViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.url = reverse('booking:submit_zero_booking_payment')
        cls.pc1 = baker.make_recipe('booking.future_PC', cost=10)

    def setUp(self):
        super().setUp()
        self.client.login(username=self.user.username, password='test')
        self.gift_voucher = EventVoucher.objects.create(code='gift', discount=100)

    def test_submit_zero_booking_payment_no_blocks(self):
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=self.pc1, paid=False
        )
        self.gift_voucher.event_types.add(booking.event.event_type)
        resp = self.client.post(
            self.url,
            {'booking_code': 'gift', 'unpaid_booking_ids': json.dumps([booking.id])}
        )
        booking.refresh_from_db()
        # booking has been changed to paid and voucher updated
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)
        user_vouchers = UsedEventVoucher.objects.filter(voucher=self.gift_voucher)
        self.assertEqual(user_vouchers.count(), 1)
        self.assertEqual(user_vouchers[0].booking_id, str(booking.id))

        # no blocks to pay for, so return to booking page
        self.assertEqual(resp.url, reverse('booking:bookings'))

    def test_submit_zero_booking_payment_with_unpaid_block(self):
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=self.pc1, paid=False
        )
        self.gift_voucher.event_types.add(booking.event.event_type)
        resp = self.client.post(
            self.url,
            {
                'booking_code': 'gift',
                'unpaid_booking_ids': json.dumps([booking.id]),
                'total_unpaid_block_cost': 20
            }
        )
        booking.refresh_from_db()
        # booking has been changed to paid and voucher updated
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)
        user_vouchers = UsedEventVoucher.objects.filter(voucher=self.gift_voucher)
        self.assertEqual(user_vouchers.count(), 1)
        self.assertEqual(user_vouchers[0].booking_id, str(booking.id))

        # blocks to pay for, so return to shopping basket
        self.assertEqual(resp.url, reverse('booking:shopping_basket'))

    def test_submit_zero_booking_payment_with_unpaid_block_and_code(self):
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=self.pc1, paid=False
        )
        self.gift_voucher.event_types.add(booking.event.event_type)
        resp = self.client.post(
            self.url,
            {
                'booking_code': 'gift',
                'unpaid_booking_ids': json.dumps([booking.id]),
                'block_code': 'gift_block',
                'total_unpaid_block_cost': 20
            }
        )
        booking.refresh_from_db()
        # booking has been changed to paid and voucher updated
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)
        user_vouchers = UsedEventVoucher.objects.filter(voucher=self.gift_voucher)
        self.assertEqual(user_vouchers.count(), 1)
        self.assertEqual(user_vouchers[0].booking_id, str(booking.id))

        # blocks to pay for, so return to shopping basket
        self.assertEqual(resp.url, reverse('booking:shopping_basket') + '?block_code=gift_block')

    def test_submit_zero_booking_payment_invalid_code(self):
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=self.pc1, paid=False
        )
        self.gift_voucher.event_types.add(booking.event.event_type)
        resp = self.client.post(
            self.url,
            {'booking_code': 'gift_foo', 'unpaid_booking_ids': json.dumps([booking.id])}
        )
        self.assertEqual(resp.status_code, 404)
        booking.refresh_from_db()
        # booking has not been changed
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)
        user_vouchers = UsedEventVoucher.objects.filter(voucher=self.gift_voucher)
        self.assertEqual(user_vouchers.count(), 0)


class SubmitZeroBlockPaymentViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.url = reverse('booking:submit_zero_block_payment')
        cls.pc1 = baker.make_recipe('booking.future_PC', cost=10)

    def setUp(self):
        super().setUp()
        self.client.login(username=self.user.username, password='test')
        self.gift_block_voucher = BlockVoucher.objects.create(code='gift', discount=100)

    def test_submit_zero_block_payment_no_blocks(self):
        block = baker.make_recipe(
            'booking.block', user=self.user, paid=False
        )
        self.gift_block_voucher.block_types.add(block.block_type)
        resp = self.client.post(
            self.url,
            {'block_code': 'gift', 'unpaid_block_ids': json.dumps([block.id])}
        )
        block.refresh_from_db()
        # block has been changed to paid and voucher updated
        self.assertTrue(block.paid)
        user_vouchers = UsedBlockVoucher.objects.filter(voucher=self.gift_block_voucher)
        self.assertEqual(user_vouchers.count(), 1)
        self.assertEqual(user_vouchers[0].block_id, str(block.id))

        # no blocks to pay for, so return to block page
        self.assertEqual(resp.url, reverse('booking:block_list'))

    def test_submit_zero_block_payment_with_unpaid_booking(self):
        block = baker.make_recipe(
            'booking.block', user=self.user, paid=False
        )
        self.gift_block_voucher.block_types.add(block.block_type)
        resp = self.client.post(
            self.url,
            {
                'block_code': 'gift',
                'unpaid_block_ids': json.dumps([block.id]),
                'total_unpaid_booking_cost': 10
            }
        )
        block.refresh_from_db()
        # block has been changed to paid and voucher updated
        self.assertTrue(block.paid)
        user_vouchers = UsedBlockVoucher.objects.filter(voucher=self.gift_block_voucher)
        self.assertEqual(user_vouchers.count(), 1)
        self.assertEqual(user_vouchers[0].block_id, str(block.id))

        # blocks to pay for, so return to shopping basket
        self.assertEqual(resp.url, reverse('booking:shopping_basket'))

    def test_submit_zero_block_payment_with_unpaid_booking_and_code(self):
        block = baker.make_recipe(
            'booking.block', user=self.user, paid=False
        )
        self.gift_block_voucher.block_types.add(block.block_type)
        resp = self.client.post(
            self.url,
            {
                'block_code': 'gift',
                'unpaid_block_ids': json.dumps([block.id]),
                'total_unpaid_booking_cost': 10,
                'booking_code': 'booking_gift'
            }
        )
        block.refresh_from_db()
        # block has been changed to paid and voucher updated
        self.assertTrue(block.paid)
        user_vouchers = UsedBlockVoucher.objects.filter(voucher=self.gift_block_voucher)
        self.assertEqual(user_vouchers.count(), 1)
        self.assertEqual(user_vouchers[0].block_id, str(block.id))

        # blocks to pay for, so return to shopping basket
        self.assertEqual(resp.url, reverse('booking:shopping_basket') + '?booking_code=booking_gift')

    def test_submit_zero_block_payment_invalid_code(self):
        block = baker.make_recipe(
            'booking.block', user=self.user, paid=False
        )
        self.gift_block_voucher.block_types.add(block.block_type)
        resp = self.client.post(
            self.url,
            {'block_code': 'gift_foo', 'unpaid_block_ids': json.dumps([block.id])}
        )
        self.assertEqual(resp.status_code, 404)
        block.refresh_from_db()
        # block has not been changed to paid
        self.assertFalse(block.paid)
        user_vouchers = UsedBlockVoucher.objects.filter(voucher=self.gift_block_voucher)
        self.assertEqual(user_vouchers.count(), 0)
