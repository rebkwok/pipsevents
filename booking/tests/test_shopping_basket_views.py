# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from decimal import Decimal
from model_mommy import mommy
from urllib.parse import urlsplit

from django.core import mail
from django.core.urlresolvers import reverse
from django.test import override_settings, TestCase, RequestFactory
from django.utils import timezone

from booking.models import Event, Booking, \
    Block, EventVoucher, UsedEventVoucher
from common.tests.helpers import TestSetupMixin


class ShoppingBasketViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.url = reverse('booking:shopping_basket')

    def setUp(self):
        super().setUp()
        self.client.login(username=self.user.username, password='test')
        mommy.make_recipe(
            'booking.booking', event__event_type__event_type='CL',
            event__date=timezone.now() + timedelta(3),
            event__cost=8,
            user=self.user, _quantity=3
        )
        mommy.make_recipe(
            'booking.booking', event__event_type__event_type='EV',
            event__date=timezone.now() + timedelta(3),
            event__cost=8,
            user=self.user, _quantity=3
        )
        self.voucher = mommy.make(
            EventVoucher, code='foo', discount=10, max_per_user=10
        )

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)

        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_only_users_bookings_displayed(self):
        other_user = mommy.make_recipe('booking.user')
        mommy.make_recipe(
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
        mommy.make_recipe('booking.past_booking', user=self.user)

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
        mommy.make_recipe(
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
        mommy.make_recipe(
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
        mommy.make_recipe(
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

        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['unpaid_bookings']), 5)
        self.assertEqual(
            len(resp.context['unpaid_bookings_non_default_paypal']), 1
        )

    def test_cancellation_warning_shown(self):
        resp = self.client.get(self.url)
        self.assertFalse(resp.context['include_warning'])

        ev = Event.objects.first()
        ev.payment_time_allowed = 6
        ev.date = timezone.now() + timedelta(hours=3)
        ev.save()

        resp = self.client.get(self.url)
        self.assertTrue(resp.context['include_warning'])

    def test_block_booking_available(self):
        resp = self.client.get(self.url)
        self.assertFalse(resp.context['block_booking_available'])

        ev_type = Booking.objects.first().event.event_type
        block = mommy.make_recipe(
            'booking.block_5', block_type__event_type=ev_type,
            user=self.user, paid=True, start_date=timezone.now() - timedelta(1)
        )

        resp = self.client.get(self.url)
        self.assertTrue(resp.context['block_booking_available'])

    def test_total_displayed(self):
        resp = self.client.get(self.url)
        # 6 bookings, events each £8
        self.assertEqual(resp.context['total_cost'], 48)

    def test_voucher_code(self):
        # valid voucher
        booking = Booking.objects.first()
        ev_type = booking.event.event_type
        self.voucher.event_types.add(ev_type)
        resp = self.client.get(self.url + '?code=foo')
        self.assertIsNone(resp.context['voucher_error'])
        self.assertTrue(resp.context['valid_voucher'])
        self.assertEqual(resp.context['times_voucher_used'], 0)

        # 6 bookings, events each £8, one with 10% discount
        self.assertEqual(resp.context['total_cost'], Decimal('47.20'))
        self.assertEqual(
            resp.context['voucher_applied_bookings'], [booking.id]
        )
        self.assertIn(
            'Voucher cannot be used for some bookings',
            resp.context['voucher_msg'][0]
        )

        # invalid voucher code
        resp = self.client.get(self.url + '?code=bar')
        self.assertEqual(resp.context['voucher_error'], 'Invalid code')

    def test_voucher_code_expired(self):
        # expired voucher
        booking = Booking.objects.first()
        ev_type = booking.event.event_type
        self.voucher.event_types.add(ev_type)
        self.voucher.start_date = timezone.now() - timedelta(4)
        self.voucher.expiry_date = timezone.now() - timedelta(2)
        self.voucher.save()
        resp = self.client.get(self.url + '?code=foo')
        self.assertEqual(
            resp.context['voucher_error'], 'Voucher code has expired'
        )

    def test_voucher_used_up_for_user(self):
        booking = Booking.objects.first()
        ev_type = booking.event.event_type
        self.voucher.event_types.add(ev_type)
        self.voucher.max_per_user = 2
        self.voucher.save()
        mommy.make(
            UsedEventVoucher, user=self.user, voucher=self.voucher, _quantity=2
        )
        resp = self.client.get(self.url + '?code=foo')
        self.assertEqual(
            resp.context['voucher_error'],
            'Voucher code has already been used the maximum number of times (2)'
        )

    def test_voucher_will_be_used_up_for_user_with_basket_bookings(self):
        booking = Booking.objects.first()
        ev_type = booking.event.event_type
        self.voucher.event_types.add(ev_type)
        self.voucher.max_per_user = 3
        self.voucher.save()
        mommy.make(
            UsedEventVoucher, user=self.user, voucher=self.voucher, _quantity=2
        )
        resp = self.client.get(self.url + '?code=foo')

        # no voucher error b/c voucher is valid for at least one more use
        self.assertIsNone(resp.context['voucher_error'])
        self.assertEqual(
            resp.context['voucher_msg'],
            ['Voucher not applied to some bookings; you can only use this '
             'voucher a total of 3 times.']
        )
        # 6 bookings, events each £8, only one with 10% discount applied
        self.assertEqual(resp.context['total_cost'], Decimal('47.20'))

    def test_voucher_used_max_total_times(self):
        booking = Booking.objects.first()
        ev_type = booking.event.event_type
        self.voucher.event_types.add(ev_type)
        self.voucher.max_vouchers = 4
        self.voucher.save()
        other_user = mommy.make_recipe('booking.user')
        mommy.make(
            UsedEventVoucher, user=other_user, voucher=self.voucher,
            _quantity=4
        )

        resp = self.client.get(self.url + '?code=foo')
        self.assertEqual(
            resp.context['voucher_error'],
            'Voucher has limited number of total uses and has now expired'
        )

    def test_voucher_will_be_used_max_total_times_with_basket_bookings(self):
        ev_types = [
            booking.event.event_type for booking in Booking.objects.all()
        ]
        for ev_type in ev_types:
            self.voucher.event_types.add(ev_type)

        resp = self.client.get(self.url + '?code=foo')

        # 6 bookings, events each £8 with 10% discount applied
        self.assertEqual(resp.context['total_cost'], Decimal('43.20'))

        # add max total
        self.voucher.max_vouchers = 10
        self.voucher.save()

        other_user = mommy.make_recipe('booking.user')
        mommy.make(
            UsedEventVoucher, user=other_user, voucher=self.voucher, _quantity=9
        )

        resp = self.client.get(self.url + '?code=foo')

        # no voucher error b/c voucher is valid for at least one more use
        self.assertIsNone(resp.context['voucher_error'])
        self.assertEqual(
            resp.context['voucher_msg'],
            ['Voucher not applied to some bookings; voucher has limited '
            'number of total uses.']
        )
        # 6 bookings, events each £8, only one with 10% discount applied
        self.assertEqual(resp.context['total_cost'], Decimal('47.20'))

    def test_paypal_cart_form_created(self):
        resp = self.client.get(self.url)
        paypalform = resp.context['paypalform']

        booking_ids_str = ','.join(
            [
                str(id) for id in Booking.objects.values_list('id', flat=True)
            ]
        )
        self.assertEqual(
            paypalform.initial['custom'], 'booking {} {}'.format(
                booking_ids_str, Booking.objects.first().user.email
            )
        )
        for i, booking in enumerate(Booking.objects.all()):
            self.assertIn('item_name_{}'.format(i + 1) , paypalform.initial)
            self.assertEqual(
                paypalform.initial['amount_{}'.format(i + 1)], 8
            )

    def test_paypal_form_for_single_cart_item(self):
        # single cart item uses a single paypal dict format
        booking = Booking.objects.first()
        Booking.objects.exclude(id=booking.id).delete()

        resp = self.client.get(self.url)
        self.assertEqual(len(resp.context['unpaid_bookings']), 1)
        paypalform = resp.context['paypalform']

        self.assertEqual(
            paypalform.initial['custom'],'booking {} {}'.format(
                booking.id, booking.user.email
            )
        )
        self.assertIn('item_name', paypalform.initial)
        self.assertNotIn('item_name_1', paypalform.initial)
        self.assertEqual(paypalform.initial['amount'], 8)

    def test_paypal_cart_form_created_with_voucher(self):
        booking = Booking.objects.first()
        ev_type = booking.event.event_type
        self.voucher.event_types.add(ev_type)

        resp = self.client.get(self.url + '?code=foo')

        paypalform = resp.context['paypalform']
        booking_ids_str = ','.join(
            [
                str(id) for id in Booking.objects.values_list('id', flat=True)
            ]
        )
        self.assertEqual(
            paypalform.initial['custom'],
            'booking {} {} foo'.format(booking_ids_str, booking.user.email)
        )
        for i, booking in enumerate(Booking.objects.all()):
            self.assertIn('item_name_{}'.format(i + 1) , paypalform.initial)

            if i == 0:
                self.assertEqual(
                    paypalform.initial['amount_{}'.format(i + 1)],
                    Decimal('7.20')
                )
            else:
                self.assertEqual(
                    paypalform.initial['amount_{}'.format(i + 1)], 8
                )

    def test_cart_items_added_to_session(self):
        self.client.get(self.url)
        booking_ids_str = ','.join(
            [
                str(id) for id in Booking.objects.values_list('id', flat=True)
            ]
        )
        self.assertEqual(
            self.client.session['cart_items'],
            'booking {} {}'.format(
                booking_ids_str, Booking.objects.first().user.email
            )
        )


class UpdateBlockBookingsTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.url = reverse('booking:update_block_bookings')
        cls.blocktype_cl_5 = mommy.make_recipe('booking.blocktype5')

        # need to specify subtype for free block creation to happen
        cls.blocktype_cl_10 = mommy.make_recipe(
            'booking.blocktype10', event_type__subtype="Pole level class"
        )
        # create free block type associated with blocktype_cl_10
        cls.free_blocktype = mommy.make_recipe(
            'booking.blocktype', size=1, cost=0,
            event_type=cls.blocktype_cl_10.event_type, identifier='free class'
        )
        cls.pc1 = mommy.make_recipe(
            'booking.future_PC', event_type=cls.blocktype_cl_5.event_type,
            cost=10
        )
        cls.pc2 = mommy.make_recipe(
            'booking.future_PC', event_type=cls.blocktype_cl_5.event_type,
            cost=10
        )
        cls.ev =  mommy.make_recipe('booking.future_EV', cost=10)

    def setUp(self):
        super().setUp()
        self.client.login(username=self.user.username, password='test')

    def test_use_block_for_all_eligible_bookings(self):
        block = mommy.make_recipe(
            'booking.block', user=self.user,
            block_type=self.blocktype_cl_5, paid=True
        )
        self.assertTrue(block.active_block())
        for ev in Event.objects.all():
            mommy.make_recipe('booking.booking', user=self.user, event=ev)

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
            mommy.make_recipe('booking.booking', user=self.user, event=ev)

        self.client.post(self.url)

        # no valid blocks
        for booking in Booking.objects.filter(user=self.user):
            self.assertIsNone(booking.block)

        # no email sent
        self.assertEqual(len(mail.outbox), 0)

    def test_use_block_for_all_with_voucher_code(self):
        # redirects with code
        for ev in Event.objects.all():
            mommy.make_recipe('booking.booking', user=self.user, event=ev)

        resp = self.client.post(self.url, {'code': 'bar'})

        # no valid blocks
        for booking in Booking.objects.filter(user=self.user):
            self.assertIsNone(booking.block)

        split_redirect_url = urlsplit(resp.url)
        self.assertEqual(
            split_redirect_url.path, reverse('booking:shopping_basket')
        )
        self.assertEqual(split_redirect_url.query, 'code=bar')

    def test_use_block_for_all_with_more_bookings_than_blocks(self):
        mommy.make_recipe(
            'booking.future_PC', event_type=self.blocktype_cl_5.event_type,
            cost=10, _quantity=6
        )
        block = mommy.make_recipe(
            'booking.block', user=self.user,
            block_type=self.blocktype_cl_5, paid=True
        )
        self.assertTrue(block.active_block())
        for ev in Event.objects.all():
            mommy.make_recipe('booking.booking', user=self.user, event=ev)

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
        mommy.make_recipe(
            'booking.future_PC', event_type=self.blocktype_cl_10.event_type,
            cost=10, _quantity=11
        )

        # free class created and used
        block = mommy.make_recipe(
            'booking.block', user=self.user,
            block_type=self.blocktype_cl_10, paid=True
        )
        self.assertTrue(block.active_block())

        for ev in Event.objects.all():
            mommy.make_recipe('booking.booking', user=self.user, event=ev)

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
        mommy.make_recipe(
            'booking.future_PC', event_type=self.blocktype_cl_10.event_type,
            cost=10, _quantity=11
        )

        block = mommy.make_recipe(
            'booking.block', user=self.user,
            block_type=self.blocktype_cl_10, paid=True
        )
        # free related block already exists
        free_block = mommy.make_recipe(
            'booking.block', user=self.user,
            block_type=self.free_blocktype, paid=True, parent=block
        )
        self.assertTrue(block.active_block())
        self.assertTrue(free_block.active_block())

        for ev in Event.objects.all():
            mommy.make_recipe('booking.booking', user=self.user, event=ev)

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
