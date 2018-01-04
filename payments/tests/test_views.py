from model_mommy import mommy

from django.core.urlresolvers import reverse
from django.test import TestCase

from paypal.standard.ipn.models import PayPalIPN
from common.tests.helpers import PatchRequestMixin, set_up_fb


class TestViews(PatchRequestMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        set_up_fb()


    def test_confirm_return(self):
        booking = mommy.make_recipe('booking.booking')
        url = reverse('payments:paypal_confirm')
        resp = self.client.post(
            url,
            {
                'custom': '{} {}'.format('booking', booking.id),
                'payment_status': 'paid',
                'item_name': booking.event.name
            }
        )
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context_data['obj_type'], 'booking')
        self.assertEquals(
            [obj for obj in resp.context_data['objs']], [booking]
        )

        block = mommy.make_recipe('booking.block')

        resp = self.client.post(
            url,
            {
                'custom': '{} {}'.format('block', block.id),
                'payment_status': 'paid',
                'item_name': block
            }
        )
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context_data['obj_type'], 'block')
        self.assertEquals(
            [obj for obj in resp.context_data['objs']], [block]
        )

        ticket_booking = mommy.make_recipe('booking.ticket_booking')

        resp = self.client.post(
            url,
            {
                'custom': '{} {}'.format('ticket_booking', ticket_booking.id),
                'payment_status': 'paid',
                'item_name': ticket_booking.ticketed_event.name
            }
        )
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context_data['obj_type'], 'ticket_booking')
        self.assertEquals(
            [obj for obj in resp.context_data['objs']], [ticket_booking]
        )

    def test_confirm_return_with_unknown_obj(self):
        block = mommy.make_recipe('booking.block')
        url = reverse('payments:paypal_confirm')
        resp = self.client.post(
            url,
            {
                'custom': '{} {}'.format('other', block.id),
                'payment_status': 'paid',
                'item_name': block
            }
        )
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context_data['obj_unknown'], True)
        self.assertIn(
            'Everything is probably fine...',
            resp.rendered_content
        )

    def test_confirm_return_with_paypal_test(self):
        url = reverse('payments:paypal_confirm')
        resp = self.client.post(
            url,
            {
                'custom': 'paypal_test 0 testpp@test.com_123456 '
                          'testpp@test.com testpp@test.com '
                          'user@test.com',
                'payment_status': 'paid',
                'item_name': 'paypal_test'
            }
        )
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(
            resp.context_data['test_paypal_email'], 'testpp@test.com'
        )
        self.assertIn(
            'The test payment is being processed',
            resp.rendered_content
        )

    def test_confirm_return_with_paypal_test_and_valid_ipn(self):
        url = reverse('payments:paypal_confirm')
        mommy.make(
            PayPalIPN, invoice='testpp@test.com_123456',
            payment_status='Completed'
        )
        resp = self.client.post(
            url,
            {
                'custom': 'paypal_test 0 testpp@test.com_123456 '
                          'testpp@test.com user@test.com',
                'payment_status': 'paid',
                'item_name': 'paypal_test'
            }
        )
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(
            resp.context_data['test_paypal_email'], 'testpp@test.com'
        )
        self.assertIn(
            'The test payment has completed successfully',
            resp.rendered_content
        )

    def test_confirm_return_with_no_custom_field(self):
        mommy.make_recipe('booking.booking')

        url = reverse('payments:paypal_confirm')
        resp = self.client.post(
            url,
            {
                'payment_status': 'paid',
            }
        )
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context_data['obj_unknown'], True)
        self.assertIn(
            'Everything is probably fine...',
            resp.rendered_content
        )

    def test_confirm_return_with_custom_multiple_bookings(self):
        bookings = mommy.make_recipe('booking.booking', _quantity=3)
        url = reverse('payments:paypal_confirm')
        resp = self.client.post(
            url,
            {
                'custom': '{} {}'.format(
                    'booking', ','.join([str(booking.id) for booking in bookings])
                ),
                'payment_status': 'paid',
            }
        )
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context_data['obj_type'], 'booking')
        self.assertCountEqual(
            [obj for obj in resp.context_data['objs']], bookings
        )

    def test_confirm_return_with_booking_cart_items(self):
        bookings = mommy.make_recipe('booking.booking', _quantity=3)
        url = reverse('payments:paypal_confirm')
        session = self.client.session
        session['cart_items'] = 'booking {}'.format(
            ','.join([str(booking.id) for booking in bookings])
        )
        session.save()

        resp = self.client.post(url)
        self.assertEquals(resp.status_code, 200)
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

    def test_confirm_return_with_booking_cart_items_already_paid(self):
        unpaid_bookings = mommy.make_recipe('booking.booking', _quantity=2)
        paid_booking = mommy.make_recipe('booking.booking', paid=True)
        all_bookings = unpaid_bookings + [paid_booking]

        url = reverse('payments:paypal_confirm')
        session = self.client.session
        session['cart_items'] = 'booking {}'.format(
            ','.join([str(booking.id) for booking in all_bookings])
        )
        session.save()

        resp = self.client.post(url)
        self.assertEquals(resp.status_code, 200)
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
        blocks = mommy.make_recipe('booking.block', _quantity=2)
        url = reverse('payments:paypal_confirm')
        session = self.client.session
        session['cart_items'] = 'block {}'.format(
            ','.join([str(block.id) for block in blocks])
        )
        session.save()

        resp = self.client.post(url)
        self.assertEquals(resp.status_code, 200)
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
        bookings = mommy.make_recipe('booking.booking', _quantity=3)
        url = reverse('payments:paypal_confirm')
        session = self.client.session
        session['cart_items'] = 'unknown {}'.format(
            ','.join([str(booking.id) for booking in bookings])
        )
        session.save()

        resp = self.client.post(url)
        self.assertEquals(resp.status_code, 200)
        self.assertTrue(resp.context_data['obj_unknown'])

        self.assertEqual(resp.context_data['cart_items'], [])

        # cart items deleted from session
        self.assertIsNone(self.client.session.get('cart_items'))

    def test_cancel_return(self):
        url = reverse('payments:paypal_cancel')
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)

    def test_cancel_return_removes_cart_items_from_session(self):
        session = self.client.session
        session['cart_items'] = 'booking 1,2,3,4'
        session.save()

        self.assertIsNotNone(self.client.session.get('cart_items'))
        url = reverse('payments:paypal_cancel')
        self.client.post(url)
        self.assertIsNone(self.client.session.get('cart_items'))

