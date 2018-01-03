# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from model_mommy import mommy

from django.conf import settings
from django.core import mail
from django.core.urlresolvers import reverse
from django.test import override_settings, TestCase, RequestFactory
from django.contrib.auth.models import Group, Permission, User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone

from activitylog.models import ActivityLog
from accounts.models import OnlineDisclaimer

from booking.models import BlockType, Event, EventType, Booking, \
    Block, EventVoucher,UsedEventVoucher,  WaitingListUser
from booking.views import BookingListView, BookingHistoryListView, \
    BookingCreateView, BookingDeleteView, BookingUpdateView, \
    duplicate_booking, fully_booked, cancellation_period_past, \
    update_booking_cancelled
from common.tests.helpers import _create_session, assert_mailchimp_post_data, \
    TestSetupMixin, format_content

from payments.helpers import create_booking_paypal_transaction


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
        voucher = mommy.make(EventVoucher, code='foo', discount=10)
        voucher.event_types.add(ev_type)
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
        voucher = mommy.make(EventVoucher, code='foo', discount=10)
        voucher.event_types.add(ev_type)
        voucher.start_date = timezone.now() - timedelta(4)
        voucher.expiry_date = timezone.now() - timedelta(2)
        voucher.save()
        resp = self.client.get(self.url + '?code=foo')
        self.assertEqual(
            resp.context['voucher_error'], 'Voucher code has expired'
        )

    def test_voucher_used_up(self):
        booking = Booking.objects.first()
        ev_type = booking.event.event_type
        voucher = mommy.make(EventVoucher, code='foo', discount=10)
        voucher.event_types.add(ev_type)
        voucher.max_per_user = 2
        voucher.save()
        mommy.make(
            UsedEventVoucher, user=self.user, voucher=voucher, _quantity=2
        )
        resp = self.client.get(self.url + '?code=foo')
        self.assertEqual(
            resp.context['voucher_error'],
            'Voucher code has already been used the maximum number of times (2)'
        )

    def test_paypal_cart_form_created(self):
        resp = self.client.get(self.url)
        paypalform = resp.context['paypalform']

        booking_ids_str = ','.join(
            [
                str(id) for id in Booking.objects.values_list('id', flat=True)
            ]
        )
        self.assertEqual(
            paypalform.initial['custom'], 'booking {}'.format(booking_ids_str)
        )
        for i, booking in enumerate(Booking.objects.all()):
            self.assertIn('item_name_{}'.format(i + 1) , paypalform.initial)
            self.assertEqual(
                paypalform.initial['amount_{}'.format(i + 1)], 8
            )

    def test_paypal_cart_form_created_with_voucher(self):
        booking = Booking.objects.first()
        ev_type = booking.event.event_type
        voucher = mommy.make(EventVoucher, code='foo', discount=10)
        voucher.event_types.add(ev_type)

        resp = self.client.get(self.url + '?code=foo')

        paypalform = resp.context['paypalform']
        booking_ids_str = ','.join(
            [
                str(id) for id in Booking.objects.values_list('id', flat=True)
            ]
        )
        self.assertEqual(
            paypalform.initial['custom'],
            'booking {} foo'.format(booking_ids_str)
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
        resp = self.client.get(self.url)
        booking_ids_str = ','.join(
            [
                str(id) for id in Booking.objects.values_list('id', flat=True)
            ]
        )
        self.assertEqual(
            self.client.session['cart_items'], booking_ids_str
        )


class UpdateBlockBookingsTests(TestSetupMixin, TestCase):

    def test_use_block_for_all_eligible_bookings(self):
        pass

    def test_use_block_for_all_eligible_bookings_with_voucher_code(self):
        # redirects with code
        pass

    def test_use_block_for_all_with_more_bookings_than_blocks(self):
        pass

    def test_use_block_for_all_uses_last_block(self):
        pass

    def test_use_block_for_all_uses_last_block_free_class_created(self):
        # free class created and used
        pass

    def test_use_block_for_all_with_no_eligible_booking(self):
        pass



