from model_bakery import baker

from django.contrib.auth.models import User
from django.urls import reverse
from django.test import TestCase

from paypal.standard.ipn.models import PayPalIPN

from booking.context_helpers import get_paypal_custom
from booking.models import Block, Booking
from common.tests.helpers import PatchRequestMixin, set_up_fb
from payments.helpers import create_multibooking_paypal_transaction, \
    create_multiblock_paypal_transaction, \
    create_ticket_booking_paypal_transaction
from payments.models import PaypalBookingTransaction, PaypalBlockTransaction


class ConfirmReturnViewTests(PatchRequestMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        set_up_fb()

    def test_confirm_return(self):
        booking = baker.make_recipe('booking.booking')
        url = reverse('payments:paypal_confirm')
        resp = self.client.post(
            url,
            {
                'custom': 'obj={} ids={}'.format('booking', booking.id),
                'payment_status': 'paid',
                'item_name': booking.event.name
            }
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context_data['obj_type'], 'booking')
        self.assertEqual(
            [obj for obj in resp.context_data['objs']], [booking]
        )

        block = baker.make_recipe('booking.block')

        resp = self.client.post(
            url,
            {
                'custom': 'obj={} ids={}'.format('block', block.id),
                'payment_status': 'paid',
                'item_name': block
            }
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context_data['obj_type'], 'block')
        self.assertEqual(
            [obj for obj in resp.context_data['objs']], [block]
        )

        ticket_booking = baker.make_recipe('booking.ticket_booking')

        resp = self.client.post(
            url,
            {
                'custom': 'obj={} ids={}'.format('ticket_booking', ticket_booking.id),
                'payment_status': 'paid',
                'item_name': ticket_booking.ticketed_event.name
            }
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context_data['obj_type'], 'ticket_booking')
        self.assertEqual(
            [obj for obj in resp.context_data['objs']], [ticket_booking]
        )

    def test_confirm_return_with_unknown_obj(self):
        block = baker.make_recipe('booking.block')
        url = reverse('payments:paypal_confirm')
        resp = self.client.post(
            url,
            {
                'custom': 'obj={} ids={}'.format('other', block.id),
                'payment_status': 'paid',
                'item_name': block
            }
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context_data['obj_unknown'], True)
        self.assertIn(
            'Thank you for your payment which is currently being processed',
            resp.rendered_content
        )

    def test_confirm_return_with_paypal_test(self):
        url = reverse('payments:paypal_confirm')
        resp = self.client.post(
            url,
            {
                'custom': 'obj=paypal_test ids=0 inv=testpp@test.com_123456 '
                          'pp=testpp@test.com usr=user@test.com',
                'payment_status': 'paid',
                'item_name': 'paypal_test'
            }
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.context_data['test_paypal_email'], 'testpp@test.com'
        )
        self.assertIn(
            'The test payment is being processed',
            resp.rendered_content
        )

    def test_confirm_return_with_paypal_test_and_valid_ipn(self):
        url = reverse('payments:paypal_confirm')
        baker.make(
            PayPalIPN, invoice='testpp@test.com_123456',
            payment_status='Completed'
        )
        resp = self.client.post(
            url,
            {
                'custom': 'obj=paypal_test ids=0 inv=testpp@test.com_123456 '
                          'pp=testpp@test.com usr=user@test.com',
                'payment_status': 'paid',
                'item_name': 'paypal_test'
            }
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.context_data['test_paypal_email'], 'testpp@test.com'
        )
        self.assertIn(
            'The test payment has completed successfully',
            resp.rendered_content
        )

    def test_confirm_return_with_no_custom_field(self):
        baker.make_recipe('booking.booking')

        url = reverse('payments:paypal_confirm')
        resp = self.client.post(
            url,
            {
                'payment_status': 'paid',
            }
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context_data['obj_unknown'], True)
        self.assertIn(
            'Thank you for your payment which is currently being processed',
            resp.rendered_content
        )

    def test_confirm_return_with_custom_multiple_bookings(self):
        bookings = baker.make_recipe('booking.booking', _quantity=3)
        url = reverse('payments:paypal_confirm')
        resp = self.client.post(
            url,
            {
                'custom': 'obj={} ids={}'.format(
                    'booking', ','.join([str(booking.id) for booking in bookings])
                ),
                'payment_status': 'paid',
            }
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context_data['obj_type'], 'booking')
        self.assertCountEqual(
            [obj for obj in resp.context_data['objs']], bookings
        )

    def test_confirm_return_with_booking_cart_items(self):
        bookings = baker.make_recipe('booking.booking', _quantity=3)
        url = reverse('payments:paypal_confirm')
        session = self.client.session
        session['cart_items'] = 'obj=booking ids={} usr={}'.format(
            ','.join([str(booking.id) for booking in bookings]),
            bookings[0].user.email
        )
        session.save()

        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context_data['obj_unknown'])

        self.assertCountEqual(
            resp.context_data['cart_items'],
            [booking.event for booking in bookings]
        )
        # cart items deleted from session
        self.assertIsNone(self.client.session.get('cart_items'))

        # paypal_pending set on bookings
        for booking in bookings:
            booking.refresh_from_db()
            self.assertTrue(booking.paypal_pending)

    def test_confirm_return_with_booking_cart_items_no_obj_type(self):
        bookings = baker.make_recipe('booking.booking', _quantity=3)
        url = reverse('payments:paypal_confirm')
        session = self.client.session
        session['cart_items'] = 'ids={} usr={}'.format(
            ','.join([str(booking.id) for booking in bookings]),
            bookings[0].user.email
        )
        session.save()

        resp = self.client.post(url)
        assert resp.status_code == 200
        assert resp.context_data['obj_unknown']
        assert resp.context_data['cart_items'] == []
        # cart items deleted from session
        assert self.client.session.get('cart_items') is None

        # paypal_pending not set on bookings
        for booking in bookings:
            booking.refresh_from_db()
            assert booking.paypal_pending is False
            assert booking.paid is False

    def test_confirm_return_with_booking_cart_items_already_paid(self):
        unpaid_bookings = baker.make_recipe('booking.booking', _quantity=2)
        paid_booking = baker.make_recipe('booking.booking', paid=True)
        all_bookings = unpaid_bookings + [paid_booking]

        url = reverse('payments:paypal_confirm')
        session = self.client.session
        session['cart_items'] = 'obj=booking ids={} usr={}'.format(
            ','.join([str(booking.id) for booking in all_bookings]),
            all_bookings[0].user.email
        )
        session.save()

        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context_data['obj_unknown'])

        # all cart items included
        self.assertCountEqual(
            resp.context_data['cart_items'],
            [booking.event for booking in all_bookings]
        )
        # cart items deleted from session
        self.assertIsNone(self.client.session.get('cart_items'))

        # paypal_pending set on bookings that are not paid
        for booking in unpaid_bookings:
            booking.refresh_from_db()
            self.assertTrue(booking.paypal_pending)

        paid_booking.refresh_from_db()
        self.assertFalse(paid_booking.paypal_pending)

    def test_confirm_return_with_block_cart_items(self):
        blocks = baker.make_recipe('booking.block', _quantity=2)
        url = reverse('payments:paypal_confirm')
        session = self.client.session
        session['cart_items'] = 'obj=block ids={} usr={}'.format(
            ','.join([str(block.id) for block in blocks]),
            blocks[0].user.email
        )
        session.save()

        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context_data['obj_unknown'])

        self.assertCountEqual(
            resp.context_data['cart_items'],
            [block.block_type for block in blocks]
        )
        # cart items deleted from session
        self.assertIsNone(self.client.session.get('cart_items'))

        # paypal_pending set on blocks
        for block in blocks:
            block.refresh_from_db()
            self.assertTrue(block.paypal_pending)

    def test_confirm_return_with_unknown_cart_items(self):
        bookings = baker.make_recipe('booking.booking', _quantity=3)
        url = reverse('payments:paypal_confirm')
        session = self.client.session
        session['cart_items'] = 'obj=unknown ids={} usr={}'.format(
            ','.join([str(booking.id) for booking in bookings]),
            bookings[0].user.email

        )
        session.save()

        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context_data['obj_unknown'])

        self.assertEqual(resp.context_data['cart_items'], [])

        # cart items deleted from session
        self.assertIsNone(self.client.session.get('cart_items'))


class CancelReturnViewTests(PatchRequestMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        set_up_fb()
        cls.user = User.objects.create_user(
            username='test@test.com', email='test@test.com', password='test'
        )

    def setUp(self):
        super().setUp()
        self.client.login(username=self.user.username, password='test')

    def test_cancel_return(self):
        url = reverse('payments:paypal_cancel')
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)

    def test_cancel_return_removes_cart_items_from_session(self):
        session = self.client.session
        session['cart_items'] = 'obj=booking ids=1,2,3,4'
        session.save()

        self.assertIsNotNone(self.client.session.get('cart_items'))
        url = reverse('payments:paypal_cancel')
        self.client.post(url)
        self.assertIsNone(self.client.session.get('cart_items'))

    def test_cancel_return_with_cart_items_already_paid_bookings(self):
        # create unpaid bookings
        bookings = baker.make_recipe(
            'booking.booking', paid=False, payment_confirmed=False,
            user=self.user, _quantity=2
        )
        # create pptrans objs
        invoice_id = create_multibooking_paypal_transaction(self.user, bookings)

        # create ipn with transaction id and custom
        custom = get_paypal_custom(
            'booking', ','.join([str(bk.id) for bk in bookings]), None, [],
            self.user.email
        )
        baker.make(
            PayPalIPN, txn_id='testtxn', invoice=invoice_id,
            payment_status='Completed', custom=custom
        )

        # add cart_items to session
        session = self.client.session
        session['cart_items'] = custom
        session.save()

        self.client.post(reverse('payments:paypal_cancel'))
        bookings = Booking.objects.all()
        for booking in bookings:
            self.assertTrue(booking.paid)
            self.assertTrue(booking.payment_confirmed)
            self.assertIsNotNone(booking.date_payment_confirmed)

        for pptrans in PaypalBookingTransaction.objects.all():
            self.assertEqual(pptrans.transaction_id, 'testtxn')

    def test_cancel_return_with_cart_items_already_paid_blocks(self):
        # create unpaid blocks
        blocks = baker.make_recipe(
            'booking.block', paid=False, paypal_pending=True,
            user=self.user, _quantity=2
        )
        # create pptrans objs
        invoice_id = create_multiblock_paypal_transaction(self.user, blocks)

        # create ipn with transaction id and custom
        custom = get_paypal_custom(
            'block', ','.join([str(bk.id) for bk in blocks]), None, [],
            self.user.email
        )
        baker.make(
            PayPalIPN, txn_id='testtxn', invoice=invoice_id,
            payment_status='Completed', custom=custom
        )

        # add cart_items to session
        session = self.client.session
        session['cart_items'] = custom
        session.save()

        self.client.post(reverse('payments:paypal_cancel'))
        blocks = Block.objects.all()
        for block in blocks:
            self.assertTrue(block.paid)
            self.assertFalse(block.paypal_pending)

        for pptrans in PaypalBlockTransaction.objects.all():
            self.assertEqual(pptrans.transaction_id, 'testtxn')

    def test_cancel_return_with_cart_items_already_paid_ticket_booking(self):
        # create unpaid ticket booking
        ticket_booking = baker.make_recipe(
            'booking.ticket_booking', paid=False, user=self.user
        )
        # create pptrans objs
        pptrans = create_ticket_booking_paypal_transaction(
            self.user, ticket_booking
        )

        # create ipn with transaction id and custom
        custom = get_paypal_custom(
            'ticket_booking', str(ticket_booking.id), None, [],
            self.user.email
        )
        baker.make(
            PayPalIPN, txn_id='testtxn', invoice=pptrans.invoice_id,
            payment_status='Completed', custom=custom
        )

        # add cart_items to session
        session = self.client.session
        session['cart_items'] = custom
        session.save()

        self.client.post(reverse('payments:paypal_cancel'))
        ticket_booking.refresh_from_db()
        self.assertTrue(ticket_booking.paid)

        pptrans.refresh_from_db()
        self.assertEqual(pptrans.transaction_id, 'testtxn')

    def test_cancel_return_with_cart_items_already_paid_includes_voucher(self):
        # create unpaid bookings
        bookings = baker.make_recipe(
            'booking.booking', paid=False, payment_confirmed=False,
            user=self.user, _quantity=2
        )
        # create pptrans objs
        invoice_id = create_multibooking_paypal_transaction(self.user, bookings)

        # create ipn with transaction id and custom
        custom = get_paypal_custom(
            'booking', ','.join([str(bk.id) for bk in bookings]), 'foo', [bk.id for bk in bookings],
            self.user.email
        )
        baker.make(
            PayPalIPN, txn_id='testtxn', invoice=invoice_id,
            payment_status='Completed', custom=custom
        )

        # add cart_items to session
        session = self.client.session
        session['cart_items'] = custom
        session.save()

        self.client.post(reverse('payments:paypal_cancel'))
        bookings = Booking.objects.all()
        for booking in bookings:
            self.assertTrue(booking.paid)
            self.assertTrue(booking.payment_confirmed)
            self.assertIsNotNone(booking.date_payment_confirmed)

        for pptrans in PaypalBookingTransaction.objects.all():
            self.assertEqual(pptrans.transaction_id, 'testtxn')

    def test_cancel_return_with_matching_cart_items_already_paid_other_user(self):
        # create unpaid bookings
        bookings = baker.make_recipe(
            'booking.booking', paid=False, payment_confirmed=False,
            user=self.user, _quantity=2
        )
        # create pptrans objs
        invoice_id = create_multibooking_paypal_transaction(self.user, bookings)

        # create ipn with transaction id and custom
        custom = get_paypal_custom(
            'booking', ','.join([str(bk.id) for bk in bookings]), None, [],
            'other_user@test.com'
        )
        baker.make(
            PayPalIPN, txn_id='testtxn', invoice=invoice_id,
            payment_status='Completed', custom=custom
        )

        # add cart_items to session
        session = self.client.session
        session['cart_items'] = custom
        session.save()

        self.client.post(reverse('payments:paypal_cancel'))
        bookings = Booking.objects.all()
        for booking in bookings:
            self.assertFalse(booking.paid)
            self.assertFalse(booking.payment_confirmed)
            self.assertIsNone(booking.date_payment_confirmed)

        for pptrans in PaypalBookingTransaction.objects.all():
            self.assertIsNone(pptrans.transaction_id)

    def test_cancel_return_with_cart_items_and_email_no_matching_ipn(self):
        # create unpaid bookings
        bookings = baker.make_recipe(
            'booking.booking', paid=False, payment_confirmed=False,
            user=self.user, _quantity=2
        )
        # create pptrans objs
        create_multibooking_paypal_transaction(self.user, bookings)

        custom = get_paypal_custom(
            'booking', ','.join([str(bk.id) for bk in bookings]), None, [],
            self.user.email
        )

        # add cart_items to session, but no IPN
        session = self.client.session
        session['cart_items'] = custom
        session.save()

        self.client.post(reverse('payments:paypal_cancel'))
        bookings = Booking.objects.all()
        for booking in bookings:
            self.assertFalse(booking.paid)
            self.assertFalse(booking.payment_confirmed)
            self.assertIsNone(booking.date_payment_confirmed)

        for pptrans in PaypalBookingTransaction.objects.all():
            self.assertIsNone(pptrans.transaction_id)

    def test_cancel_return_with_cart_items_and_email_multiple_ipns(self):
        # create unpaid bookings
        bookings = baker.make_recipe(
            'booking.booking', paid=False, payment_confirmed=False,
            user=self.user, _quantity=2
        )
        # create pptrans objs
        invoice_id = create_multibooking_paypal_transaction(self.user, bookings)

        # create ipn with transaction id and custom
        custom = get_paypal_custom(
            'booking', ','.join([str(bk.id) for bk in bookings]), None, [],
            self.user.email
        )
        baker.make(
            PayPalIPN, txn_id='testtxn', invoice=invoice_id,
            payment_status='Completed', custom=custom
        )
        baker.make(
            PayPalIPN, txn_id='testtxn', invoice='other',
            payment_status='Completed', custom=custom
        )

        # add cart_items to session
        session = self.client.session
        session['cart_items'] = custom
        session.save()

        self.client.post(reverse('payments:paypal_cancel'))
        bookings = Booking.objects.all()
        for booking in bookings:
            self.assertFalse(booking.paid)
            self.assertFalse(booking.payment_confirmed)
            self.assertIsNone(booking.date_payment_confirmed)

        for pptrans in PaypalBookingTransaction.objects.all():
            self.assertIsNone(pptrans.transaction_id)

