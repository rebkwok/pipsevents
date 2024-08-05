from bs4 import BeautifulSoup
from datetime import timedelta
from unittest.mock import patch
from model_bakery import baker

from django.conf import settings
from django.contrib.sites.models import Site
from django.urls import reverse
from django.core import mail
from django.test import TestCase
from django.utils import timezone

from booking.models import Booking, Block, BlockType, EventType, \
    WaitingListUser
from common.tests.helpers import format_content
from payments.helpers import create_booking_paypal_transaction
from stripe_payments.tests.mock_connector import MockConnector
from studioadmin.tests.test_views.helpers import TestPermissionMixin


class UserPastBookingsViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super().setUp()

        past_classes1 = baker.make_recipe('booking.past_class', _quantity=2)
        past_classes2 = baker.make_recipe('booking.past_class', _quantity=2)
        future_classes1 = baker.make_recipe('booking.future_PC', _quantity=2)
        future_classes3 = baker.make_recipe('booking.future_PC', _quantity=2)

        self.future_user_bookings = [
                baker.make_recipe(
                'booking.booking', user=self.user, paid=True,
                payment_confirmed=True, event=event, status='OPEN',
            ) for event in future_classes1
        ]
        self.past_user_bookings = [
            baker.make_recipe(
                'booking.booking', user=self.user, paid=True,
                payment_confirmed=True, event=event, status='OPEN'
            ) for event in past_classes1
        ]
        self.past_cancelled_bookings = [
            baker.make_recipe(
                'booking.booking', user=self.user, paid=True,
                payment_confirmed=True, event=event, status='CANCELLED'
            ) for event in past_classes2
        ]
        [
            baker.make_recipe(
                'booking.booking', paid=True,
                payment_confirmed=True, event=event,
            ) for event in future_classes3
        ]
        self.client.force_login(self.staff_user)
    
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.past_url = reverse(
            'studioadmin:user_past_bookings_list',
            kwargs={'user_id': cls.user.id}
        )

    def test_filter_past_bookings_by_booking_status(self):

        # past bookings
        resp = self.client.get(self.past_url)
        # no formset in past list
        self.assertNotIn('userbookingformset', resp.context_data)
        bookings = resp.context_data['bookings']
        self.assertEqual(bookings.count(), 4)
        self.assertEqual(
            sorted([booking.id for booking in bookings]),
            sorted([
                       bk.id for bk in
                       self.past_user_bookings + self.past_cancelled_bookings
                    ])
        )

    def test_past_bookings_pagination(self):

        for i in range(20):
            baker.make(
                'booking.booking', user=self.user,
                event__date=timezone.now()-timedelta(10+i)
            )

        self.assertEqual(
            Booking.objects.filter(
                user=self.user, event__date__lt=timezone.now()
            ).count(),
            24
        )

        # no page in url, shows first page
        resp = self.client.get(self.past_url)
        bookings = resp.context_data['bookings']
        self.assertEqual(bookings.count(), 20)
        paginator = resp.context_data['page_obj']
        self.assertEqual(paginator.number, 1)

        # page 1
        resp = self.client.get(self.past_url + '?page=1')
        bookings = resp.context_data['bookings']
        self.assertEqual(bookings.count(), 20)
        paginator = resp.context_data['page_obj']
        self.assertEqual(paginator.number, 1)

        # page number > max pages gets last page
        resp = self.client.get(self.past_url + '?page=4')
        bookings = resp.context_data['bookings']
        self.assertEqual(bookings.count(), 4)
        paginator = resp.context_data['page_obj']
        self.assertEqual(paginator.number, 2)

        # page not a number > gets first page
        resp = self.client.get(self.past_url + '?page=foo')
        bookings = resp.context_data['bookings']
        self.assertEqual(bookings.count(), 20)
        paginator = resp.context_data['page_obj']
        self.assertEqual(paginator.number, 1)

 
class BookingEditViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(BookingEditViewTests, self).setUp()
        baker.make("stripe_payments.Seller", site=Site.objects.get_current())
        event = baker.make_recipe('booking.future_PC', cost=10)
        self.booking = baker.make_recipe(
                'booking.booking', paid=True,
                payment_confirmed=True, event=event, status='OPEN'
        )
        self.client.login(username=self.staff_user.username, password='test')
        self.url = reverse('studioadmin:bookingedit', args=[self.booking.id])

    def test_get_booking_edit_view(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_post_booking_with_changes(self):
        self.assertFalse(self.booking.attended)
        data = {
            'id': self.booking.id,
            'paid': self.booking.paid,
            'status': self.booking.status,
            'block': '',
            'free_class': self.booking.free_class,
            'attended': True,
            'no_show': self.booking.no_show
        }
        self.client.post(self.url, data=data)

        # get the user's booking list again to check for messages
        resp = self.client.get(
            reverse(
                'studioadmin:user_upcoming_bookings_list',
                args=[self.booking.user.id]
            )
        )

        self.assertIn(
            'Booking for {} has been updated'.format(self.booking.event),
            str(resp.content))
        self.booking.refresh_from_db()
        self.assertTrue(self.booking.attended)

    def test_post_booking_no_changes(self):
        data = {
            'id': self.booking.id,
            'paid': self.booking.paid,
            'status': self.booking.status,
            'block': '',
            'free_class': self.booking.free_class,
            'attended': self.booking.attended,
            'no_show': self.booking.no_show
        }
        self.client.post(self.url, data=data)
        # get the user's booking list again to check for messages
        resp = self.client.get(
            reverse(
                'studioadmin:user_upcoming_bookings_list',
                args=[self.booking.user.id]
            )
        )
        self.assertIn('No changes made', str(resp.content))
    
    def test_post_booking_no_changes_send_confirmation(self):
        data = {
            'id': self.booking.id,
            'paid': self.booking.paid,
            'status': self.booking.status,
            'block': '',
            'free_class': self.booking.free_class,
            'attended': self.booking.attended,
            'no_show': self.booking.no_show,
            'send_confirmation': True
        }
        self.client.post(self.url, data=data)
        # get the user's booking list again to check for messages
        resp = self.client.get(
            reverse(
                'studioadmin:user_upcoming_bookings_list',
                args=[self.booking.user.id]
            )
        )
        assert 'email has not been sent' in str(resp.content)

    def test_paid_booking_unpaid(self):
        assert not Block.objects.exists() 
        assert self.booking.paid
        assert self.booking.payment_confirmed
        data = {
            'id': self.booking.id,
            'paid': False,
            'status': "OPEN"
        }
        self.client.post(self.url, data=data)
        self.booking.refresh_from_db()
        # marking unpaid also unsets payment confirmed
        assert not self.booking.paid
        assert not self.booking.payment_confirmed

    def test_paid_booking_cancelled(self):
        assert not Block.objects.exists() 
        data = {
            'id': self.booking.id,
            'paid': self.booking.paid,
            'status': "CANCELLED",
            'block': '',
            'free_class': False,
            'send_confirmation': True
        }
        resp = self.client.post(self.url, data=data)
        assert Block.objects.exists()
        assert Block.objects.first().block_type.identifier == "transferred"
        # get the user's booking list again to check for messages
        resp = self.client.get(
            reverse(
                'studioadmin:user_upcoming_bookings_list',
                args=[self.booking.user.id]
            )
        )
        self.booking.refresh_from_db()
        assert self.booking.status == "CANCELLED"
        assert 'Booking status changed to cancelled' in mail.outbox[0].body

    def test_booking_cancelled_with_waiting_list(self):
        baker.make(
            "booking.WaitingListUser", event=self.booking.event, user__email="wl@example.com"
        )
        data = {
            'id': self.booking.id,
            'paid': self.booking.paid,
            'status': "CANCELLED",
            'block': '',
            'free_class': False,
        }
        self.client.post(self.url, data=data)
        self.booking.refresh_from_db()
        assert self.booking.status == "CANCELLED"
        assert len(mail.outbox) == 1
        assert mail.outbox[0].bcc == ["wl@example.com"]

    def test_booking_reopened(self):
        self.booking.status = "CANCELLED"
        self.booking.save()
        assert not Block.objects.exists() 
        data = {
            'id': self.booking.id,
            'paid': self.booking.paid,
            'status': "OPEN",
            'block': '',
            'free_class': False,
            'send_confirmation': True,
        }
        resp = self.client.post(self.url, data=data)
        assert not Block.objects.exists()
        
        # get the user's booking list again to check for messages
        resp = self.client.get(
            reverse(
                'studioadmin:user_upcoming_bookings_list',
                args=[self.booking.user.id]
            )
        )
        self.booking.refresh_from_db()
        assert self.booking.status == "OPEN"
        assert 'Booking status changed to reopened' in mail.outbox[0].body

    def test_booking_reopened_was_on_waiting_list(self):
        self.booking.status = "CANCELLED"
        self.booking.save()
        baker.make(
            "booking.WaitingListUser", event=self.booking.event, user=self.booking.user
        )
        assert WaitingListUser.objects.count() == 1
        data = {
            'id': self.booking.id,
            'paid': self.booking.paid,
            'status': "OPEN",
            'block': '',
            'free_class': False,
        }
        self.client.post(self.url, data=data)
        self.booking.refresh_from_db()
        assert self.booking.status == "OPEN"
        assert not WaitingListUser.objects.exists()

    def test_booking_reopened_from_no_show(self):
        self.booking.no_show = True
        self.booking.save()
        assert not Block.objects.exists() 
        data = {
            'id': self.booking.id,
            'paid': self.booking.paid,
            'status': "OPEN",
            'block': '',
            'free_class': False,
            "no_show": False,
            'send_confirmation': True
        }
        resp = self.client.post(self.url, data=data)
        assert not Block.objects.exists()
        
        # get the user's booking list again to check for messages
        resp = self.client.get(
            reverse(
                'studioadmin:user_upcoming_bookings_list',
                args=[self.booking.user.id]
            )
        )
        self.booking.refresh_from_db()
        assert self.booking.status == "OPEN"
        assert not self.booking.no_show
        assert 'Booking reopened' in mail.outbox[0].body
    
    def test_booking_cancelled_as_no_show(self):
        assert not Block.objects.exists() 
        data = {
            'id': self.booking.id,
            'paid': self.booking.paid,
            'status': "OPEN",
            'block': '',
            'free_class': False,
            "no_show": True,
            'send_confirmation': True
        }
        resp = self.client.post(self.url, data=data)
        assert not Block.objects.exists()
        
        # get the user's booking list again to check for messages
        resp = self.client.get(
            reverse(
                'studioadmin:user_upcoming_bookings_list',
                args=[self.booking.user.id]
            )
        )
        self.booking.refresh_from_db()
        assert self.booking.status == "OPEN"
        assert self.booking.no_show
        assert 'Booking cancelled' in mail.outbox[0].body
        assert not Block.objects.filter(block_type__identifier="transferred").exists()

    def test_can_update_booking_deposit_paid(self):
        unpaid_booking = baker.make_recipe(
            'booking.booking', user=self.user,
            event__date=timezone.now()+timedelta(3),
            status='OPEN', paid=False
        )
        data = {
            'id': unpaid_booking.id,
            'paid': unpaid_booking.paid,
            'status': "OPEN",
            'deposit_paid': True
        }
        url = reverse('studioadmin:bookingedit', args=[unpaid_booking.id])
        resp = self.client.post(url, data=data)
        unpaid_booking.refresh_from_db()
        assert unpaid_booking.deposit_paid
        assert not unpaid_booking.paid
        assert not unpaid_booking.payment_confirmed

    def test_changing_booking_status_to_cancelled_removed_block(self):
        block = baker.make_recipe(
            'booking.block', user=self.user
        )
        booking = baker.make_recipe(
            'booking.booking',
            event__event_type=block.block_type.event_type, block=block,
            user=self.user, paid=True, payment_confirmed=True
        )
        data = {
            'id': booking.id,
            'paid': booking.paid,
            'status': "CANCELLED",
            'block': block.id
        }

        url = reverse('studioadmin:bookingedit', args=[booking.id])
        resp = self.client.post(url, data=data)
        booking.refresh_from_db()
        assert booking.status == 'CANCELLED'
        assert booking.block is None
        assert not booking.paid
        # no transfer blocks created for block-paid
        assert not Block.objects.filter(block_type__identifier="transferred").exists()

    @patch("booking.models.membership_models.StripeConnector", MockConnector)   
    def test_changing_booking_status_to_cancelled_removed_membership(self):
        user_membership = baker.make(
            "booking.UserMembership", membership__name="mem", user=self.booking.user, subscription_status="active"
        )
        baker.make(
            "booking.MembershipItem", membership=user_membership.membership, event_type=self.booking.event.event_type, quantity=3
        )
        assert user_membership.valid_for_event(self.booking.event)
        self.booking.membership = user_membership
        self.booking.save()
        assert self.booking.membership == user_membership
       
        data = {
            'id': self.booking.id,
            'paid': self.booking.paid,
            'status': "CANCELLED",
            'membership': user_membership.id
        }

        resp = self.client.post(self.url, data=data)
        self.booking.refresh_from_db()
        assert self.booking.status == 'CANCELLED'
        assert self.booking.block is None
        assert self.booking.membership is None
        assert not self.booking.paid
        # no transfer blocks created for membership-paid
        assert not Block.objects.filter(block_type__identifier="transferred").exists()

    def test_can_assign_booking_to_available_block(self):
        booking = baker.make_recipe(
            'booking.booking',
            event__date=timezone.now()+timedelta(2),
            user=self.user,
            paid=False,
            payment_confirmed=False
        )
        block = baker.make_recipe(
            'booking.block', block_type__event_type=booking.event.event_type,
            user=self.user
        )
        assert booking.block is None
        data = {
            'id': booking.id,
            'paid': booking.paid,
            'status': booking.status,
            'block': block.id
        }
        url = reverse('studioadmin:bookingedit', args=[booking.id])
        resp = self.client.post(url, data=data)
        booking.refresh_from_db()
        assert booking.status == 'OPEN'
        assert booking.block == block
        assert booking.paid
    
    @patch("booking.models.membership_models.StripeConnector", MockConnector)
    def test_change_block_booking_to_membership(self):
        block_type = baker.make_recipe(
            'booking.blocktype5', event_type=self.booking.event.event_type
        )
        block = baker.make_recipe(
            "booking.block_5", user=self.user, block_type=block_type, paid=True,
            start_date=timezone.now() - timedelta(1),
        )
        assert block.active_block()
        self.booking.block = block
        self.booking.save()
        assert self.booking.block == block

        user_membership = baker.make(
            "booking.UserMembership", membership__name="mem", user=self.booking.user, subscription_status="active"
        )
        baker.make(
            "booking.MembershipItem", membership=user_membership.membership, event_type=self.booking.event.event_type, quantity=3
        )
        assert user_membership.valid_for_event(self.booking.event)

        data = {
            'id': self.booking.id,
            'paid': self.booking.paid,
            'status': 'OPEN',
            'block': '',
            'membership': user_membership.id
        }
        resp = self.client.post(self.url, data=data, follow=True)
        self.booking.refresh_from_db()
        assert self.booking.block is None
        assert self.booking.membership == user_membership
        assert "Payment method changed from block to membership" in resp.rendered_content

    def test_block_removed(self):
        block_type = baker.make_recipe(
            'booking.blocktype5', event_type=self.booking.event.event_type
        )
        block = baker.make_recipe(
            "booking.block_5", user=self.user, block_type=block_type, paid=True,
            start_date=timezone.now() - timedelta(1),
        )
        assert block.active_block()
        self.booking.block = block
        self.booking.save()
        assert self.booking.block == block

        data = {
            'id': self.booking.id,
            'paid': self.booking.paid,
            'status': 'OPEN',
            'block': '',
            'membership': ''
        }
        resp = self.client.post(self.url, data=data, follow=True)
        self.booking.refresh_from_db()
        assert self.booking.block is None
        assert not self.booking.paid
        assert not self.booking.payment_confirmed
        assert "Block removed" in resp.rendered_content

    @patch("booking.models.membership_models.StripeConnector", MockConnector)
    def test_change_membership_booking_to_block(self):
        block_type = baker.make_recipe(
            'booking.blocktype5', event_type=self.booking.event.event_type
        )
        block = baker.make_recipe(
            "booking.block_5", user=self.user, block_type=block_type, paid=True,
            start_date=timezone.now() - timedelta(1),
        )
        assert block.active_block()
        
        user_membership = baker.make(
            "booking.UserMembership", membership__name="mem", user=self.booking.user, subscription_status="active"
        )
        baker.make(
            "booking.MembershipItem", membership=user_membership.membership, event_type=self.booking.event.event_type, quantity=3
        )
        assert user_membership.valid_for_event(self.booking.event)
        self.booking.membership = user_membership
        self.booking.save()
        assert self.booking.membership == user_membership

        data = {
            'id': self.booking.id,
            'paid': self.booking.paid,
            'status': 'OPEN',
            'block': block.id,
            'membership': ''
        }
        resp = self.client.post(self.url, data=data, follow=True)
        self.booking.refresh_from_db()
        assert self.booking.block == block
        assert self.booking.membership is None
        assert "Payment method changed from membership to block" in resp.rendered_content

    @patch("booking.models.membership_models.StripeConnector", MockConnector)
    def test_membership_removed(self):
        user_membership = baker.make(
            "booking.UserMembership", membership__name="mem", user=self.booking.user, subscription_status="active"
        )
        baker.make(
            "booking.MembershipItem", membership=user_membership.membership, event_type=self.booking.event.event_type, quantity=3
        )
        assert user_membership.valid_for_event(self.booking.event)
        self.booking.membership = user_membership
        self.booking.save()
        assert self.booking.membership == user_membership

        data = {
            'id': self.booking.id,
            'paid': self.booking.paid,
            'status': 'OPEN',
            'block': '',
            'membership': ''
        }
        resp = self.client.post(self.url, data=data, follow=True)
        self.booking.refresh_from_db()
        assert self.booking.block is None
        assert not self.booking.paid
        assert not self.booking.payment_confirmed
        assert "Membership removed" in resp.rendered_content


class BookingEditPastViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(BookingEditPastViewTests, self).setUp()
        past_class = baker.make_recipe('booking.past_class')
        self.booking = baker.make_recipe(
                'booking.booking', paid=True,
                payment_confirmed=True, event=past_class, status='OPEN'
        )
        self.client.login(username=self.staff_user.username, password='test')
        self.url = reverse('studioadmin:bookingeditpast', args=[self.booking.id], )

    def test_get_booking_edit_view(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_post_booking_with_changes(self):
        self.assertFalse(self.booking.attended)
        data = {
            'id': self.booking.id,
            'paid': self.booking.paid,
            'status': self.booking.status,
            'block': '',
            'free_class': self.booking.free_class,
            'attended': True,
            'no_show': self.booking.no_show
        }
        self.client.post(self.url, data=data)

        # get the user's booking list again to check for messages
        resp = self.client.get(
            reverse(
                'studioadmin:user_past_bookings_list',
                args=[self.booking.user.id]
            )
        )

        self.assertIn('Saved!', str(resp.content))
        self.booking.refresh_from_db()
        self.assertTrue(self.booking.attended)

    def test_post_booking_no_changes(self):
        data = {
            'id': self.booking.id,
            'paid': self.booking.paid,
            'status': self.booking.status,
            'block': '',
            'free_class': self.booking.free_class,
            'attended': self.booking.attended,
            'no_show': self.booking.no_show
        }
        self.client.post(self.url, data=data)
        # get the user's booking list again to check for messages
        resp = self.client.get(
            reverse(
                'studioadmin:user_past_bookings_list',
                args=[self.booking.user.id]
            )
        )
        self.assertIn('No changes made', str(resp.content))


class UserBookingsModalViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(UserBookingsModalViewTests, self).setUp()
        past_classes1 = baker.make_recipe('booking.past_class', _quantity=2)
        past_classes2 = baker.make_recipe('booking.past_class', _quantity=2)
        future_classes1 = baker.make_recipe('booking.future_PC', _quantity=2)
        future_classes2 = baker.make_recipe('booking.future_PC', _quantity=2)
        future_classes3 = baker.make_recipe('booking.future_PC', _quantity=2)

        self.future_user_bookings = [
                baker.make_recipe(
                'booking.booking', user=self.user, paid=True,
                payment_confirmed=True, event=event, status='OPEN',
            ) for event in future_classes1
        ]
        self.past_user_bookings = [
            baker.make_recipe(
                'booking.booking', user=self.user, paid=True,
                payment_confirmed=True, event=event, status='OPEN'
            ) for event in past_classes1
        ]
        self.future_cancelled_bookings = [
                baker.make_recipe(
                'booking.booking', user=self.user, paid=True,
                payment_confirmed=True, event=event, status='CANCELLED'
            ) for event in future_classes2
        ]
        self.past_cancelled_bookings = [
            baker.make_recipe(
                'booking.booking', user=self.user, paid=True,
                payment_confirmed=True, event=event, status='CANCELLED'
            ) for event in past_classes2
        ]
        [
            baker.make_recipe(
                'booking.booking', paid=True,
                payment_confirmed=True, event=event,
            ) for event in future_classes3
        ]

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse(
            'studioadmin:user_upcoming_bookings_list',
            kwargs={'user_id': self.user.id}
        )
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        self.client.login(username=self.user.username, password='test')
        url = reverse(
            'studioadmin:user_upcoming_bookings_list',
            kwargs={'user_id': self.user.id}
        )
        resp = self.client.get(url)
        # resp = self._get_response(self.user, self.user.id)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_cannot_access(self):
        """
        test that the page redirects if user is in the instructor group but is
        not a staff user
        """
        self.client.login(username=self.instructor_user.username, password='test')
        url = reverse(
            'studioadmin:user_upcoming_bookings_list',
            kwargs={'user_id': self.user.id}
        )
        resp = self.client.get(url)
        # resp = self._get_response(self.instructor_user, self.user.id)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        self.client.login(username=self.staff_user.username, password='test')
        url = reverse(
            'studioadmin:user_upcoming_bookings_list',
            kwargs={'user_id': self.user.id}
        )
        resp = self.client.get(url)
        # resp = self._get_response(self.staff_user, self.user.id)
        self.assertEqual(resp.status_code, 200)

    def test_view_users_bookings(self):
        """
        Test only user's bookings for future events shown by default
        """
        self.assertEqual(Booking.objects.count(), 10)
        self.client.login(username=self.staff_user.username, password='test')
        url = reverse(
            'studioadmin:user_upcoming_bookings_list',
            kwargs={'user_id': self.user.id}
        )
        resp = self.client.get(url)
        # resp = self._get_response(self.staff_user, self.user.id)
        # get all but last form (last form is the empty extra one)
        bookings = resp.context_data['bookings']
        # show future bookings, both open and cancelled
        self.assertEqual(
            len(bookings),
            len(self.future_user_bookings) + len(self.future_cancelled_bookings)
        )

        self.assertEqual(
            sorted([booking.id for booking in bookings]),
            sorted(
                [bk.id for bk in
                 self.future_user_bookings + self.future_cancelled_bookings]
            )
        )

    @patch("booking.models.membership_models.StripeConnector", MockConnector)
    def test_payment_method(self):
        baker.make("stripe_payments.Seller", site=Site.objects.get_current())

        user = baker.make_recipe('booking.user')
        
        url = reverse(
            'studioadmin:user_upcoming_bookings_list',
            kwargs={'user_id': user.id}
        )
        self.client.login(username=self.staff_user.username, password='test')

        # unpaid
        unpaid_booking = baker.make_recipe(
            'booking.booking', 
            event__date=timezone.now() + timedelta(2),
            user=user, paid=False, status='OPEN'
        )
        # paid, no method
        paid_booking = baker.make_recipe(
            'booking.booking', 
            event__date=timezone.now() + timedelta(2),
            user=user, paid=True, status='OPEN'
        )
        # paid with block
        block = baker.make(Block)
        block_booking = baker.make_recipe(
            'booking.booking', 
            event__date=timezone.now() + timedelta(2),
            user=user, paid=True, block=block, status='OPEN'
        )

        # paid with membership
        membership_booking = baker.make_recipe(
            'booking.booking', 
            event__date=timezone.now() + timedelta(2),
            user=user, paid=True, membership__membership__name="Membership", status='OPEN'
        )

        # paid with paypal
        paypal_booking = baker.make_recipe(
            'booking.booking', 
            event__date=timezone.now() + timedelta(2),
            user=user, paid=True, status='OPEN'
        )
        ppbs = create_booking_paypal_transaction(booking=paypal_booking, user=user)
        ppbs.transaction_id = 'foo'
        ppbs.save()
        # paid with stripe
        invoice = baker.make("stripe_payments.Invoice", paid=True, amount=20)
        stripe_booking = baker.make_recipe(
            'booking.booking', 
            event__date=timezone.now() + timedelta(2),
            user=user, paid=True, status='OPEN', invoice=invoice
        )
        # paid with voucher via stripe
        invoice = baker.make("stripe_payments.Invoice", paid=True, amount=0)
        voucher_booking = baker.make_recipe(
            'booking.booking', 
            event__date=timezone.now() + timedelta(2),
            user=user, paid=True, status='OPEN', invoice=invoice
        )

        resp = self.client.get(url)
        soup = BeautifulSoup(resp.content, 'html.parser')
        assert soup.find(id=f'payment-method-{unpaid_booking.id}').text == ""
        assert soup.find(id=f'payment-method-{paid_booking.id}').text == ""
        assert soup.find(id=f'payment-method-{block_booking.id}').text == "Block"
        assert soup.find(id=f'payment-method-{paypal_booking.id}').text == "PayPal"
        assert soup.find(id=f'payment-method-{stripe_booking.id}').text == "Stripe"
        assert soup.find(id=f'payment-method-{voucher_booking.id}').text == "Voucher"
        assert soup.find(id=f'payment-method-{membership_booking.id}').text == "Membership"


class BookingAddViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(BookingAddViewTests, self).setUp()
        baker.make("stripe_payments.Seller", site=Site.objects.get_current())
        self.event = baker.make_recipe('booking.future_PC', event_type__event_type="CL", cost=10)
        self.block_type = baker.make_recipe(
            'booking.blocktype5', event_type=self.event.event_type
        )
        self.client.login(username=self.staff_user.username, password='test')
        self.url = reverse('studioadmin:bookingadd', args=[self.user.id])

    def test_get_booking_add_view(self):
        resp = self.client.get(self.url)
        form = resp.context_data['form']

        self.assertEqual(resp.status_code, 200)
        # form's initial user is set to the user passed to the view
        self.assertEqual(form.fields['user'].initial, self.user.id)

    def test_get_booking_add_view_with_block(self):
        block = baker.make_recipe(
            "booking.block_5", user=self.user, block_type__event_type=self.event.event_type, paid=True,
            start_date=timezone.now() - timedelta(1),
        )
        resp = self.client.get(self.url)
        form = resp.context_data['form']

        self.assertEqual(resp.status_code, 200)
        # form's initial user is set to the user passed to the view
        self.assertEqual(form.fields['user'].initial, self.user.id)
        # 2 choices, None and the available block
        assert len(form.fields["block"].choices) == 2

    @patch("booking.models.membership_models.StripeConnector", MockConnector)
    def test_get_booking_add_view_with_membership(self):
        baker.make(
            "booking.UserMembership", membership__name="mem", user=self.user, subscription_status="active",
        )
        resp = self.client.get(self.url)
        form = resp.context_data['form']

        self.assertEqual(resp.status_code, 200)
        # form's initial user is set to the user passed to the view
        self.assertEqual(form.fields['user'].initial, self.user.id)
        # 2 choices, None and the available membership
        assert len(form.fields["membership"].choices) == 2
        # None only for blocks
        assert len(form.fields["block"].choices) == 1

    def test_post_new_booking(self):
        self.assertFalse(Booking.objects.filter(user=self.user).exists())
        data = {
            'user': self.user.id,
            'event': self.event.id,
            'paid': True,
            'status': 'OPEN',
        }
        self.client.post(self.url, data=data)

        self.assertTrue(Booking.objects.filter(user=self.user).exists())
        # get the user's booking list again to check for messages
        resp = self.client.get(
            reverse(
                'studioadmin:user_upcoming_bookings_list',
                args=[self.user.id]
            )
        )

        self.assertIn(
            'Booking for {} has been created'.format(self.event),
            str(resp.content))

    def test_create_new_booking_with_block(self):
        assert not self.user.bookings.exists()
        block = baker.make_recipe(
            "booking.block_5", user=self.user, block_type=self.block_type, paid=True,
            start_date=timezone.now() - timedelta(1),
        )
        assert block.active_block()
        data = {
            'user': self.user.id,
            'event': self.event.id,
            'paid': True,
            'status': 'OPEN',
            'block': block.id
        }
        resp = self.client.post(self.url, data=data)
        assert self.user.bookings.exists()
        assert self.user.bookings.first().block == block

    def test_create_new_free_booking(self):
        assert not self.user.bookings.exists()
        data = {
            'user': self.user.id,
            'event': self.event.id,
            'status': 'OPEN',
            'free_class': True
        }
        resp = self.client.post(self.url, data=data)
        assert self.user.bookings.exists()
        booking = self.user.bookings.first()
        assert booking.free_class
        assert booking.paid

    @patch("booking.models.membership_models.StripeConnector", MockConnector)
    def test_create_new_booking_with_membership(self):
        assert not self.user.bookings.exists()
        block = baker.make_recipe(
            "booking.block_5", user=self.user, block_type=self.block_type, paid=True,
            start_date=timezone.now() - timedelta(1),
        )
        assert block.active_block()
        user_membership = baker.make("booking.UserMembership", membership__name="mem", user=self.user, subscription_status="active")
        baker.make("booking.MembershipItem", membership=user_membership.membership, event_type=self.event.event_type, quantity=3)

        data = {
            'user': self.user.id,
            'event': self.event.id,
            'paid': True,
            'status': 'OPEN',
            'membership': user_membership.id
        }
        resp = self.client.post(self.url, data=data)
        assert self.user.bookings.exists()
        assert self.user.bookings.first().membership == user_membership
