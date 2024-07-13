from unittest.mock import patch
from model_bakery import baker
import pytest

from django.urls import reverse
from django.core import mail
from django.test import TestCase
from django.contrib.sites.models import Site

from booking.models import Booking, Block, TicketBooking, Ticket
from stripe_payments.models import Invoice
from studioadmin.tests.test_views.helpers import TestPermissionMixin


class ConfirmPaymentViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(ConfirmPaymentViewTests, self).setUp()
        self.booking = baker.make_recipe(
            'booking.booking', user=self.user,
            paid=False,
            payment_confirmed=False)
        self.url = reverse('studioadmin:confirm-payment', args=[self.booking.id])
        self.client.force_login(self.staff_user)

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        self.client.logout()
        redirected_url = reverse('account_login') + "?next={}".format(self.url)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_cannot_access(self):
        """
        test that the page redirects if user is in the instructor group but is
        not a staff user
        """
        self.client.force_login(self.instructor_user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_with_unpaid_booking(self):
        """
        Change an unpaid booking to paid and confirmed
        """
        self.assertFalse(self.booking.paid)
        self.assertFalse(self.booking.payment_confirmed)

        form_data = {
            'paid': 'true',
            'payment_confirmed': 'true'
        }
        resp = self.client.post(self.url, form_data)
        booking = Booking.objects.get(id=self.booking.id)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("paid and confirmed", email.body)

    def test_confirm_payment(self):
        """
        Changing payment_confirmed to True also sets booking to paid
        """
        self.assertFalse(self.booking.paid)
        self.assertFalse(self.booking.payment_confirmed)

        form_data = {
            'payment_confirmed': 'true'
        }
        resp = self.client.post(self.url, form_data)
        booking = Booking.objects.get(id=self.booking.id)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("paid and confirmed", email.body)

    def test_changing_paid_to_unpaid(self):
        """
        Changing a previously paid booking to unpaid also sets
        payment_confirmed to False
        """
        self.booking.paid = True
        self.booking.payment_confirmed = True
        self.booking.save()
        self.assertTrue(self.booking.paid)
        self.assertTrue(self.booking.payment_confirmed)

        form_data = {
            'paid': 'false',
            'payment_confirmed': 'true'
        }
        resp = self.client.post(self.url, form_data)
        booking = Booking.objects.get(id=self.booking.id)
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("not paid", email.body)

    def test_changing_payment_confirmed_only(self):
        """
        Changing a previously unpaid booking to confirmed also sets
        paid to True
        """
        self.booking.save()
        self.assertFalse(self.booking.paid)
        self.assertFalse(self.booking.payment_confirmed)

        form_data = {
            'paid': 'false',
            'payment_confirmed': 'true'
        }
        resp = self.client.post(self.url, form_data)
        booking = Booking.objects.get(id=self.booking.id)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)

    def test_payment_not_confirmed(self):
        form_data = {
            'paid': 'true',
            'payment_confirmed': 'false'
        }
        resp = self.client.post(self.url, form_data)
        booking = Booking.objects.get(id=self.booking.id)
        self.assertTrue(booking.paid)
        self.assertFalse(booking.payment_confirmed)

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("paid - payment not confirmed yet", email.body)

    def test_no_changes(self):
        form_data = {
            'paid': 'false',
            'payment_confirmed': 'false'
        }
        resp = self.client.post(self.url, form_data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:users'))

    @patch('studioadmin.views.misc.send_mail')
    def test_confirm_payment_with_email_errors(self, mock_send_mail):
        """
        Test booking is processed and support email sent
        """
        mock_send_mail.side_effect = Exception('Error sending email')
        self.assertFalse(self.booking.paid)
        self.assertFalse(self.booking.payment_confirmed)

        form_data = {
            'payment_confirmed': 'true'
        }
        resp = self.client.post(self.url, form_data)
        booking = Booking.objects.get(id=self.booking.id)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)

        self.assertEqual(len(mail.outbox), 0)


class ConfirmRefundViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(ConfirmRefundViewTests, self).setUp()
        self.booking = baker.make_recipe(
            'booking.booking', user=self.user,
            paid=True,
            payment_confirmed=True)
        self.url = reverse('studioadmin:confirm-refund', args=[self.booking.id])
        self.client.force_login(self.staff_user)

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        self.client.logout()
        url = reverse('studioadmin:confirm-refund', args=[self.booking.id])
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_cannot_access(self):
        """
        test that the page redirects if user is in the instructor group but is
        not a staff user
        """
        self.client.force_login(self.instructor_user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_confirm_refund_for_paid_booking(self):
        """
        test that the page can be accessed by a staff user
        """
        self.assertTrue(self.booking.paid)
        self.assertTrue(self.booking.payment_confirmed)
        resp = self.client.post(self.url, {'confirmed': ['Confirm']})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:users'))
        booking = Booking.objects.get(id=self.booking.id)
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)
        self.assertEqual(len(mail.outbox), 1)

    def test_confirm_refund_for_free_booking(self):
        """
        test that the page can be accessed by a staff user
        """
        self.booking.free_class = True
        self.booking.save()

        self.assertTrue(self.booking.paid)
        self.assertTrue(self.booking.payment_confirmed)
        resp = self.client.post(self.url, {'confirmed': ['Confirm']})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:users'))
        booking = Booking.objects.get(id=self.booking.id)
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)
        self.assertFalse(booking.free_class)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(
            'Your free booking for {} has been refunded/compensated.'.format(
                booking.event
            ),
            mail.outbox[0].body,
        )

    def test_cancel_confirm_form(self):
        """
        test that page redirects without changes if cancel button used
        """
        self.assertTrue(self.booking.paid)
        self.assertTrue(self.booking.payment_confirmed)
        resp = self.client.post(self.url, {'cancelled': ['Cancel']})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:users'))
        booking = Booking.objects.get(id=self.booking.id)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)
        self.assertEqual(len(mail.outbox), 0)


class TestPaypalViewTests(TestPermissionMixin, TestCase):

    def test_staff_login_required(self):
        url = reverse('studioadmin:test_paypal_email')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

        self.client.login(
            username=self.instructor_user.username, password='test'
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_post_created_paypal_form(self):
        url = reverse('studioadmin:test_paypal_email')
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.post(url, {'email': 'testpp@test.com'})
        self.assertEqual(resp.status_code, 200)

        self.assertIn('paypalform', resp.context_data)
        paypal_data = resp.context_data['paypalform'].initial

        self.assertTrue(paypal_data['invoice'].startswith('testpp@test.com'))
        # invoice is email plus '_' and 6 char uuid
        self.assertEqual(len(paypal_data['invoice']), len('testpp@test.com') + 7)
        self.assertEqual(paypal_data['amount'], 0.01)
        self.assertEqual(
            paypal_data['custom'],
            'obj=paypal_test ids=0 inv={} pp=testpp@test.com usr=staff@example.com'.format(
                paypal_data['invoice']
            )
        )

    def test_post_with_no_email_address(self):
        url = reverse('studioadmin:test_paypal_email')
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)

        self.assertNotIn('paypalform', resp.context_data)
        self.assertIn('email_errors', resp.context_data)
        self.assertEqual(
            resp.context_data['email_errors'],
            'Please enter an email address to test'
        )


@pytest.mark.django_db
def test_invoice_list(client, staff_user):
    invoice = baker.make(Invoice, invoice_id="foo123", paid=True)
    unpaid_invoice = baker.make(Invoice, invoice_id="foo345", paid=False)
    baker.make(Block, block_type__cost=10, invoice=invoice)
    baker.make(Booking, event__name="test event", event__cost=10, invoice=invoice)
    ticket_booking = baker.make(TicketBooking, ticketed_event__name="test show", ticketed_event__ticket_cost=10, invoice=invoice)
    baker.make(Ticket, ticket_booking=ticket_booking)
    # gift voucher
    blocktype = baker.make_recipe("booking.blocktype")
    block_gift_voucher = baker.make_recipe(
        "booking.block_gift_voucher", purchaser_email="test@test.com", activated=True,
        invoice=invoice
    )
    block_gift_voucher.block_types.add(blocktype)
    blocktype = block_gift_voucher.block_types.first()    
    baker.make("booking.GiftVoucherType", block_type=blocktype)

    client.force_login(staff_user)
    resp = client.get(reverse("studioadmin:invoices"))
    assert list(resp.context_data["invoices"]) == [invoice]


@pytest.mark.django_db
def test_stripe_test(client, staff_user):
    client.force_login(staff_user)
    resp = client.get(reverse("studioadmin:stripe_test"))

    # no seller
    assert "No Stripe account connected yet" in resp.rendered_content
    assert "checkout-test-stripe-form" not in resp.rendered_content

    baker.make("stripe_payments.Seller", site=Site.objects.get_current(), stripe_user_id="id123")
    resp = client.get(reverse("studioadmin:stripe_test"))
    assert "No Stripe account connected yet" not in resp.rendered_content
    assert "checkout-test-stripe-form" in resp.rendered_content
