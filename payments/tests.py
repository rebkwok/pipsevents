import json

from model_mommy import mommy

from django.core import mail
from django.core.urlresolvers import reverse
from django.test import TestCase, Client

from booking.tests.helpers import set_up_fb
from payments import helpers
from payments.models import PaypalBookingTransaction, PaypalBlockTransaction, \
    PaypalTicketBookingTransaction
from paypal.standard.ipn.models import PayPalIPN

from six import b, text_type
from six.moves.urllib.parse import urlencode


class TestViews(TestCase):

    def setUp(self):
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
        self.assertEquals(resp.context_data['obj'], booking)

        block = mommy.make_recipe('booking.block')

        resp = self.client.post(
            url,
            {
                'custom': '{} {}'.format('block', block.id),
                'payment_status': 'paid',
                'item_name': booking.event.name
            }
        )
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context_data['obj_type'], 'block')
        self.assertEquals(resp.context_data['obj'], block)

        resp = self.client.post(
            url,
            {
                'custom': '{} {}'.format('other', block.id),
                'payment_status': 'paid',
                'item_name': booking.event.name
            }
        )
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context_data['obj_type'], 'other')
        self.assertEquals(resp.context_data['obj'], 'unknown')

    def test_cancel_return(self):
        url = reverse('payments:paypal_cancel')
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)


class TestHelpers(TestCase):

    def test_create_booking_transaction(self):
        user = mommy.make_recipe('booking.user', username="testuser")
        booking = mommy.make_recipe(
            'booking.booking', user=user, event__name='test event'
        )
        booking_txn = helpers.create_booking_paypal_transaction(user, booking)
        self.assertEqual(booking_txn.booking, booking)
        self.assertEqual(
            booking_txn.invoice_id,
            'testuser-te-{}-inv#001'.format(
                booking.event.date.strftime("%d%m%y%H%M")
            )
        )

    def test_create_existing_booking_transaction(self):
        user = mommy.make_recipe('booking.user', username="testuser")
        booking = mommy.make_recipe(
            'booking.booking', user=user, event__name='test event'
        )
        booking_txn = helpers.create_booking_paypal_transaction(user, booking)
        self.assertEqual(booking_txn.booking, booking)
        self.assertEqual(
            booking_txn.invoice_id,
            'testuser-te-{}-inv#001'.format(
                booking.event.date.strftime("%d%m%y%H%M")
            )
        )
        self.assertEqual(PaypalBookingTransaction.objects.count(), 1)

        dp_booking_txn = helpers.create_booking_paypal_transaction(user, booking)
        self.assertEqual(PaypalBookingTransaction.objects.count(), 1)
        self.assertEqual(booking_txn, dp_booking_txn)

    def test_create_existing_booking_txn_with_txn_id(self):
        """
        if the existing transaction is already associated with a paypal
        transaction_id, we do need to create a new transaction, with new
        invoice number with incremented counter
        """
        user = mommy.make_recipe('booking.user', username="testuser")
        booking = mommy.make_recipe(
            'booking.booking', user=user, event__name='test event'
        )
        booking_txn = helpers.create_booking_paypal_transaction(user, booking)
        self.assertEqual(booking_txn.booking, booking)
        self.assertEqual(
            booking_txn.invoice_id,
            'testuser-te-{}-inv#001'.format(
                booking.event.date.strftime("%d%m%y%H%M")
            )
        )
        self.assertEqual(PaypalBookingTransaction.objects.count(), 1)
        booking_txn.transaction_id = "123"
        booking_txn.save()
        new_booking_txn = helpers.create_booking_paypal_transaction(user, booking)
        self.assertEqual(PaypalBookingTransaction.objects.count(), 2)
        self.assertEqual(
            new_booking_txn.invoice_id,
            'testuser-te-{}-inv#002'.format(
                booking.event.date.strftime("%d%m%y%H%M")
            )
        )

    def test_create_block_transaction(self):
        user = mommy.make_recipe('booking.user', username="testuser")
        block = mommy.make_recipe(
            'booking.block', user=user,
            block_type__event_type__subtype="Pole Level Class",
            block_type__size=10
        )
        block_txn = helpers.create_block_paypal_transaction(user, block)
        self.assertEqual(block_txn.block, block)
        self.assertEqual(
            block_txn.invoice_id,
            'testuser-PLC-10-{}-inv#001'.format(
                block.start_date.strftime("%d%m%y%H%M")
            )
        )

    def test_create_existing_block_transaction(self):
        user = mommy.make_recipe('booking.user', username="testuser")
        block = mommy.make_recipe(
            'booking.block', user=user,
            block_type__event_type__subtype="Pole Level Class",
            block_type__size=10
        )
        block_txn = helpers.create_block_paypal_transaction(user, block)
        self.assertEqual(block_txn.block, block)
        self.assertEqual(
            block_txn.invoice_id,
            'testuser-PLC-10-{}-inv#001'.format(
                block.start_date.strftime("%d%m%y%H%M")
            )
        )
        self.assertEqual(PaypalBlockTransaction.objects.count(), 1)

        dp_block_txn = helpers.create_block_paypal_transaction(user, block)
        self.assertEqual(PaypalBlockTransaction.objects.count(), 1)
        self.assertEqual(block_txn, dp_block_txn)

    def test_create_ticket_booking_transaction(self):
        user = mommy.make_recipe('booking.user', username="testuser")
        tbooking = mommy.make_recipe(
            'booking.ticket_booking', user=user
        )
        tbooking_txn = helpers.create_ticket_booking_paypal_transaction(
            user, tbooking)
        self.assertEqual(tbooking_txn.ticket_booking, tbooking)
        self.assertEqual(
            tbooking_txn.invoice_id, '{}001'.format(tbooking.booking_reference)
        )


    def test_create_existing_ticket_booking_transaction(self):
        user = mommy.make_recipe('booking.user', username="testuser")
        tbooking = mommy.make_recipe(
            'booking.ticket_booking', user=user
        )
        tbooking_txn = helpers.create_ticket_booking_paypal_transaction(
            user, tbooking)
        self.assertEqual(tbooking_txn.ticket_booking, tbooking)
        self.assertEqual(
            tbooking_txn.invoice_id, '{}001'.format(tbooking.booking_reference)
        )
        self.assertEqual(PaypalTicketBookingTransaction.objects.count(), 1)

        dp_tbooking_txn = helpers.create_ticket_booking_paypal_transaction(
            user, tbooking
        )
        self.assertEqual(PaypalTicketBookingTransaction.objects.count(), 1)
        self.assertEqual(tbooking_txn, dp_tbooking_txn)


# Parameters are all bytestrings, so we can construct a bytestring
# request the same way that Paypal does.

CHARSET = "utf-8"
IPN_POST_PARAMS = {
    "protection_eligibility": b"Ineligible",
    "last_name": b"User",
    "txn_id": b"51403485VH153354B",
    "receiver_email": b'test@paypaltest.com',
    "payment_status": b"Completed",
    "payment_gross": b"10.00",
    "tax": b"0.00",
    "residence_country": b"US",
    "invoice": b"0004",
    "payer_status": b"verified",
    "txn_type": b"express_checkout",
    "handling_amount": b"0.00",
    "payment_date": b"23:04:06 Feb 02, 2009 PST",
    "first_name": b"J\xF6rg",
    "item_name": b"",
    "charset": b(CHARSET),
    "custom": b"",
    "notify_version": b"2.6",
    "transaction_subject": b"",
    "test_ipn": b"1",
    "item_number": b"",
    "receiver_id": b"258DLEHY2BDK6",
    "payer_id": b"BN5JZ2V7MLEV4",
    "verify_sign": b"An5ns1Kso7MWUdW4ErQKJJJ4qi4-AqdZy6dD.sGO3sDhTf1wAbuO2IZ7",
    "payment_fee": b"0.59",
    "mc_fee": b"0.59",
    "mc_currency": b"USD",
    "shipping": b"0.00",
    "payer_email": b"test_user@gmail.com",
    "payment_type": b"instant",
    "mc_gross": b"10.00",
    "quantity": b"1",
}


class TestPaypalSignals(TestCase):

    def setUp(self):
        self.client = Client()

    def paypal_post(self, params):
        """
        Does an HTTP POST the way that PayPal does, using the params given.
        Taken from django-paypal
        """
        # We build params into a bytestring ourselves, to avoid some encoding
        # processing that is done by the test client.
        cond_encode = lambda v: v.encode(CHARSET) if isinstance(v, text_type) else v
        byte_params = {
            cond_encode(k): cond_encode(v) for k, v in params.items()
            }
        post_data = urlencode(byte_params)
        return self.client.post(
            reverse('paypal-ipn'),
            post_data, content_type='application/x-www-form-urlencoded'
        )

    def test_paypal_notify_url_with_no_data(self):
        self.assertFalse(PayPalIPN.objects.exists())
        resp = self.paypal_post({'charset': CHARSET})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PayPalIPN.objects.count(), 1)

        ppipn = PayPalIPN.objects.first()
        self.assertTrue(ppipn.flag)

        # one warning email sent
        self.assertEqual(len(mail.outbox), 1)

        self.assertEqual(
            mail.outbox[0].subject,
            'WARNING! Error processing Invalid Payment Notification from PayPal'
        )
        self.assertEqual(
            mail.outbox[0].body,
            'PayPal sent an invalid transaction notification while '
            'attempting to process payment;.\n\nThe flag '
            'info was "{}"\n\nAn additional error was raised: {}'.format(
                ppipn.flag_info, 'Unknown object type for payment'
            )
        )

    def test_paypal_notify_url_with_no_data(self):
        self.assertFalse(PayPalIPN.objects.exists())
        resp = self.paypal_post({'charset': CHARSET, 'custom': 'test 1'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PayPalIPN.objects.count(), 1)

        ppipn = PayPalIPN.objects.first()
        self.assertTrue(ppipn.flag)

        # one warning email sent
        self.assertEqual(len(mail.outbox), 1)

        self.assertEqual(
            mail.outbox[0].subject,
            'WARNING! Error processing Invalid Payment Notification from PayPal'
        )
        self.assertEqual(
            mail.outbox[0].body,
            'PayPal sent an invalid transaction notification while '
            'attempting to process payment;.\n\nThe flag '
            'info was "{}"\n\nAn additional error was raised: {}'.format(
                ppipn.flag_info, 'Unknown object type for payment'
            )
        )

    def test_paypal_notify_url_with_no_matching_booking(self):
        self.assertFalse(PayPalIPN.objects.exists())

        resp = self.paypal_post({'custom': 'booking 1', 'charset': CHARSET})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PayPalIPN.objects.count(), 1)
        ppipn = PayPalIPN.objects.first()

        # one warning email sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            'WARNING! Error processing Invalid Payment Notification from PayPal'
        )
        self.assertEqual(
            mail.outbox[0].body,
            'PayPal sent an invalid transaction notification while '
            'attempting to process payment;.\n\nThe flag '
            'info was "{}"\n\nAn additional error was raised: {}'.format(
                ppipn.flag_info, 'Booking with id 1 does not exist'
            )
        )

    def test_paypal_notify_url_with_no_matching_block(self):
        self.assertFalse(PayPalIPN.objects.exists())

        resp = self.paypal_post({'custom': 'block 1', 'charset': CHARSET})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PayPalIPN.objects.count(), 1)
        ppipn = PayPalIPN.objects.first()

        # one warning email sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            'WARNING! Error processing Invalid Payment Notification from PayPal'
        )
        self.assertEqual(
            mail.outbox[0].body,
            'PayPal sent an invalid transaction notification while '
            'attempting to process payment;.\n\nThe flag '
            'info was "{}"\n\nAn additional error was raised: {}'.format(
                ppipn.flag_info, 'Block with id 1 does not exist'
            )
        )

    def test_paypal_notify_url_with_no_matching_ticket_booking(self):
        self.assertFalse(PayPalIPN.objects.exists())

        resp = self.paypal_post(
            {'custom': 'ticket_booking 1', 'charset': CHARSET}
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PayPalIPN.objects.count(), 1)
        ppipn = PayPalIPN.objects.first()

        # one warning email sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            'WARNING! Error processing Invalid Payment Notification from PayPal'
        )
        self.assertEqual(
            mail.outbox[0].body,
            'PayPal sent an invalid transaction notification while '
            'attempting to process payment;.\n\nThe flag '
            'info was "{}"\n\nAn additional error was raised: {}'.format(
                ppipn.flag_info, 'Ticket Booking with id 1 does not exist'
            )
        )

    def test_paypal_notify_url_with_invalid_status(self):
        pass

    def test_paypal_notify_url_with_complete_status(self):
        pass

    def test_paypal_notify_url_with_complete_status_no_matching_object(self):
        pass

    def test_paypal_notify_url_sends_emails(self):
        pass

    def test_paypal_notify_url_with_complete_status_no_invoice_number(self):
        pass

    def test_paypal_notify_url_with_refunded_status(self):
        # TODO send emails for refunded and set paid to False
        pass
