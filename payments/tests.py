from datetime import datetime
from model_mommy import mommy
from mock import Mock, patch

from django.contrib.admin.sites import AdminSite
from django.conf import settings
from django.core import mail
from django.core.urlresolvers import reverse
from django.test import TestCase, Client, override_settings
from django.utils import timezone

from booking.context_helpers import get_paypal_dict
from booking.models import Booking
from booking.tests.helpers import set_up_fb
from payments import helpers
from payments.admin import PaypalBookingTransactionAdmin, \
    PaypalBlockTransactionAdmin
from payments.forms import PayPalPaymentsListForm, PayPalPaymentsUpdateForm
from payments.models import PaypalBookingTransaction, PaypalBlockTransaction, \
    PaypalTicketBookingTransaction
from payments.models import logger as payment_models_logger

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
        # str returns invoice id
        self.assertEqual(str(booking_txn), booking_txn.invoice_id)

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
        # str returns invoice id
        self.assertEqual(str(block_txn), block_txn.invoice_id)


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
        # str returns invoice id
        self.assertEqual(str(tbooking_txn), tbooking_txn.invoice_id)

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

    def test_create_booking_with_duplicate_invoice_number(self):
        user = mommy.make_recipe('booking.user', username="testuser")
        booking = mommy.make_recipe(
            'booking.booking', user=user, event__name='test event',
            event__date=datetime(2015, 2, 1, 10, 0, tzinfo=timezone.utc)
        )
        booking1 = mommy.make_recipe(
            'booking.booking', user=user, event__name='test event1',
            event__date=datetime(2015, 2, 1, 10, 0, tzinfo=timezone.utc)
        )
        booking_txn = helpers.create_booking_paypal_transaction(user, booking)
        self.assertEqual(booking_txn.booking, booking)
        self.assertEqual(
            booking_txn.invoice_id,
            'testuser-te-{}-inv#001'.format(
                booking.event.date.strftime("%d%m%y%H%M")
            )
        )

        booking1_txn = helpers.create_booking_paypal_transaction(user, booking1)
        self.assertEqual(booking1_txn.booking, booking1)
        self.assertNotEqual(
            booking1_txn.invoice_id,
            'testuser-te-{}-inv#001'.format(
                booking1.event.date.strftime("%d%m%y%H%M")
            )
        )
        # to avoid duplication, the counter is set to 6 digits, the first 3
        # random between 100 and 999
        self.assertEqual(len(booking1_txn.invoice_id.split('#')[-1]), 6)

    def test_create_existing_block_transaction_with_txn_id(self):
        user = mommy.make_recipe('booking.user', username="testuser")
        block = mommy.make_recipe(
            'booking.block', user=user,
            block_type__event_type__subtype="Pole Level Class",
            block_type__size=10
        )
        block_txn = helpers.create_block_paypal_transaction(user, block)
        block_txn.transaction_id = "test transaction id"
        block_txn.save()
        self.assertEqual(block_txn.block, block)
        self.assertEqual(
            block_txn.invoice_id,
            'testuser-PLC-10-{}-inv#001'.format(
                block.start_date.strftime("%d%m%y%H%M")
            )
        )
        self.assertEqual(PaypalBlockTransaction.objects.count(), 1)

        second_block_txn = helpers.create_block_paypal_transaction(user, block)
        self.assertEqual(PaypalBlockTransaction.objects.count(), 2)
        self.assertNotEqual(block_txn, second_block_txn)
        self.assertEqual(
            second_block_txn.invoice_id,
            'testuser-PLC-10-{}-inv#002'.format(
                block.start_date.strftime("%d%m%y%H%M")
            )
        )

    def test_create_block_transaction_with_duplicate_invoice_number(self):
        user = mommy.make_recipe('booking.user', username="testuser")
        block = mommy.make_recipe(
            'booking.block', user=user,
            block_type__event_type__subtype="Pole Level Class",
            block_type__size=10
        )
        block1 = mommy.make_recipe(
            'booking.block', user=user,
            block_type__event_type__subtype="Pole Level Class1",
            block_type__size=10,
            start_date=block.start_date
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

        second_block_txn = helpers.create_block_paypal_transaction(user, block1)
        self.assertEqual(PaypalBlockTransaction.objects.count(), 2)
        self.assertNotEqual(block_txn, second_block_txn)
        # to avoid duplication, the counter is set to 6 digits, the first 3
        # random between 100 and 999
        self.assertEqual(len(second_block_txn.invoice_id.split('#')[-1]), 6)

    def test_create_ticket_booking_with_duplicate_invoice_number(self):
        user = mommy.make_recipe('booking.user', username="testuser")
        tbooking = mommy.make_recipe('booking.ticket_booking', user=user)
        tbooking.booking_reference = "ref"
        tbooking.save()
        tbooking1 = mommy.make_recipe('booking.ticket_booking', user=user)
        tbooking1.booking_reference = "ref"
        tbooking1.save()

        tbooking_txn = helpers.create_ticket_booking_paypal_transaction(
            user, tbooking)

        self.assertEqual(tbooking_txn.ticket_booking, tbooking)
        self.assertEqual(
            tbooking_txn.invoice_id,
            '{}001'.format(
                tbooking.booking_reference
            )
        )

        tbooking1_txn = helpers.create_ticket_booking_paypal_transaction(
            user, tbooking1)

        self.assertEqual(tbooking1_txn.ticket_booking, tbooking1)
        self.assertNotEqual(
            tbooking1_txn.invoice_id,
            '{}001'.format(
                tbooking.booking_reference
            )
        )
        # to avoid duplication, the counter is set to 6 digits, the first 3
        # random between 100 and 999
        self.assertEqual(len(tbooking_txn.invoice_id), 6)
        self.assertEqual(len(tbooking1_txn.invoice_id), 9)

    def test_create_existing_ticket_booking_transation_with_txn_id(self):
        user = mommy.make_recipe('booking.user', username="testuser")
        tbooking = mommy.make_recipe(
            'booking.ticket_booking', user=user
        )
        tbooking_txn = helpers.create_ticket_booking_paypal_transaction(
            user, tbooking)
        tbooking_txn.transaction_id = "test txn id"
        tbooking_txn.save()
        self.assertEqual(tbooking_txn.ticket_booking, tbooking)
        self.assertEqual(
            tbooking_txn.invoice_id, '{}001'.format(tbooking.booking_reference)
        )
        self.assertEqual(PaypalTicketBookingTransaction.objects.count(), 1)

        second_tbooking_txn = helpers.create_ticket_booking_paypal_transaction(
            user, tbooking
        )
        self.assertEqual(PaypalTicketBookingTransaction.objects.count(), 2)
        self.assertNotEqual(tbooking_txn, second_tbooking_txn)
        self.assertEqual(
            second_tbooking_txn.invoice_id, '{}002'.format(tbooking.booking_reference)
        )


# Parameters are all bytestrings, so we can construct a bytestring
# request the same way that Paypal does.
CHARSET = "windows-1252"
IPN_POST_PARAMS = {
    "mc_gross": b"7.00",
    "invoice": b"user-PL1-2411152010-inv001",
    "protection_eligibility": b"Ineligible",
    "txn_id": b"51403485VH153354B",
    "last_name": b"User",
    "receiver_email": b"test-paypal@watermelon.com",
    "payer_id": b"BN5JZ2V7MLEV4",
    "tax": b"0.00",
    "payment_date": b"23:04:06 Feb 02, 2009 PST",
    "first_name": b"Test",
    "mc_fee": b"0.44",
    "notify_version": b"3.8",
    "custom": b"booking 1",
    "payer_status": b"verified",
    "payment_status": b"Completed",
    "business": b"thewatermelonstudio%40hotmail.com",
    "quantity": b"1",
    "verify_sign": b"An5ns1Kso7MWUdW4ErQKJJJ4qi4-AqdZy6dD.sGO3sDhTf1wAbuO2IZ7",
    "payer_email": b"test_user@gmail.com",
    "payment_type": b"instant",
    "payment_fee": b"",
    "receiver_id": b"258DLEHY2BDK6",
    "txn_type": b"web_accept",
    "item_name": "Pole Level 1 - 24 Nov 2015 20:10",
    "mc_currency": b"GBP",
    "item_number": b"",
    "residence_country": "GB",
    "handling_amount": b"0.00",
    "charset": b(CHARSET),
    "payment_gross": b"",
    "transaction_subject": b"",
    "ipn_track_id": b"1bd9fe52f058e",
    "shipping": b"0.00",
}


class PaypalSignalsTests(TestCase):

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
        resp = self.paypal_post(
            {'charset': b(CHARSET), 'txn_id': 'test'}
        )
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

    def test_paypal_notify_url_with_unknown_obj_type(self):
        self.assertFalse(PayPalIPN.objects.exists())
        resp = self.paypal_post(
            {'charset': b(CHARSET), 'custom': b'test 1', 'txn_id': 'test'}
        )
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

        resp = self.paypal_post(
            {'custom': b'booking 1', 'charset': b(CHARSET), 'txn_id': 'test'}
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
                ppipn.flag_info, 'Booking with id 1 does not exist'
            )
        )

    def test_paypal_notify_url_with_no_matching_block(self):
        self.assertFalse(PayPalIPN.objects.exists())

        resp = self.paypal_post(
            {'custom': b'block 1', 'charset': b(CHARSET), 'txn_id': 'test'}
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
                ppipn.flag_info, 'Block with id 1 does not exist'
            )
        )

    def test_paypal_notify_url_with_no_matching_ticket_booking(self):
        self.assertFalse(PayPalIPN.objects.exists())

        resp = self.paypal_post(
            {'custom': b'ticket_booking 1', 'charset': b(CHARSET),
             'txn_id': 'test'}
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

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_url_with_complete_status(self, mock_postback):
        mock_postback.return_value = b"VERIFIED"
        booking = mommy.make_recipe('booking.booking')
        pptrans = helpers.create_booking_paypal_transaction(
            booking.user, booking
        )

        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking {}'.format(booking.id)),
                'invoice': b(pptrans.invoice_id),
                'txn_id': b'test_txn_id'
            }
        )
        self.assertIsNone(pptrans.transaction_id)
        resp = self.paypal_post(params)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PayPalIPN.objects.count(), 1)
        ppipn = PayPalIPN.objects.first()
        self.assertFalse(ppipn.flag)
        self.assertEqual(ppipn.flag_info, '')

        # check paypal trans obj is updated
        pptrans.refresh_from_db()
        self.assertEqual(pptrans.transaction_id, 'test_txn_id')

        # 2 emails sent, to user and studio
        self.assertEqual(
            len(mail.outbox), 2,
            "NOTE: Fails if SEND_ALL_STUDIO_EMAILS!=True in env/test settings"
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_url_with_complete_status_unmatching_object(self, mock_postback):
        mock_postback.return_value = b"VERIFIED"

        self.assertFalse(PayPalIPN.objects.exists())
        self.assertFalse(Booking.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b'booking 1',
            }
        )
        resp = self.paypal_post(params)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PayPalIPN.objects.count(), 1)
        ppipn = PayPalIPN.objects.first()

        # paypal ipn is not flagged
        self.assertFalse(ppipn.flag)
        self.assertEqual(ppipn.flag_info, '')

        # we can't match up the payment to booking, so raise error and send
        # emails
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            'WARNING! Error processing PayPal IPN'
        )
        self.assertEqual(
            mail.outbox[0].body,
            'Valid Payment Notification received from PayPal but an error '
            'occurred during processing.\n\nTransaction id {}\n\nThe flag info '
            'was "{}"\n\nError raised: Booking with id 1 does not exist'.format(
                ppipn.txn_id, ppipn.flag_info,
            )
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_successful_paypal_payment_sends_emails(self, mock_postback):
        mock_postback.return_value = b"VERIFIED"
        booking = mommy.make_recipe('booking.booking')
        invoice_id = helpers.create_booking_paypal_transaction(
            booking.user, booking
        ).invoice_id

        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking {}'.format(booking.id)),
                'invoice': b(invoice_id)
            }
        )
        resp = self.paypal_post(params)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PayPalIPN.objects.count(), 1)
        ppipn = PayPalIPN.objects.first()

        # 2 emails sent, to user and studio
        self.assertEqual(
            len(mail.outbox), 2,
            "NOTE: Fails if SEND_ALL_STUDIO_EMAILS!=True in env/test settings"
        )
        self.assertEqual(mail.outbox[0].to, [settings.DEFAULT_STUDIO_EMAIL])
        self.assertEqual(mail.outbox[1].to, [booking.user.email])

    @override_settings(SEND_ALL_STUDIO_EMAILS=False)
    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_sends_emails_to_user_only_if_studio_emails_off(self, mock_postback):
        mock_postback.return_value = b"VERIFIED"
        booking = mommy.make_recipe('booking.booking')
        invoice_id = helpers.create_booking_paypal_transaction(
            booking.user, booking
        ).invoice_id

        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking {}'.format(booking.id)),
                'invoice': b(invoice_id)
            }
        )
        resp = self.paypal_post(params)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PayPalIPN.objects.count(), 1)
        ppipn = PayPalIPN.objects.first()

        # 1 email sent, to studio only
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [booking.user.email])

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_successful_paypal_payment_updates_booking(self, mock_postback):
        mock_postback.return_value = b"VERIFIED"
        booking = mommy.make_recipe('booking.booking', payment_confirmed=False,
                                    paid=False)
        invoice_id = helpers.create_booking_paypal_transaction(
            booking.user, booking
        ).invoice_id

        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking {}'.format(booking.id)),
                'invoice': b(invoice_id)
            }
        )
        resp = self.paypal_post(params)
        booking.refresh_from_db()
        self.assertTrue(booking.payment_confirmed)
        self.assertTrue(booking.paid)

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_url_with_complete_status_no_invoice_number(self, mock_postback):
        mock_postback.return_value = b"VERIFIED"
        booking = mommy.make_recipe('booking.booking', payment_confirmed=False,
                                    paid=False)
        invoice_id = helpers.create_booking_paypal_transaction(
            booking.user, booking
        ).invoice_id

        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking {}'.format(booking.id)),
                'invoice': b''
            }
        )
        resp = self.paypal_post(params)
        booking.refresh_from_db()
        self.assertTrue(booking.payment_confirmed)
        self.assertTrue(booking.paid)

        # 3 emails sent - studio, user, support to notify about missing inv
        self.assertEqual(
            len(mail.outbox), 3,
            "NOTE: Fails if SEND_ALL_STUDIO_EMAILS!=True in env/test settings"
        )
        self.assertEqual(
            mail.outbox[2].subject,
            '{} No invoice number on paypal ipn for booking id {}'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.id
            )
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_url_with_block(self, mock_postback):
        mock_postback.return_value = b"VERIFIED"
        block = mommy.make_recipe('booking.block_10', paid=False)
        invoice_id = helpers.create_block_paypal_transaction(
            block.user, block
        ).invoice_id

        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('block {}'.format(block.id)),
                'invoice': b(invoice_id)
            }
        )
        resp = self.paypal_post(params)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PayPalIPN.objects.count(), 1)
        ppipn = PayPalIPN.objects.first()
        self.assertFalse(ppipn.flag)
        self.assertEqual(ppipn.flag_info, '')

        block.refresh_from_db()
        self.assertTrue(block.paid)
        # 2 emails sent, to user and studio
        self.assertEqual(
            len(mail.outbox), 2,
            "NOTE: Fails if SEND_ALL_STUDIO_EMAILS!=True in env/test settings"
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_url_with_ticket_booking(self, mock_postback):
        mock_postback.return_value = b"VERIFIED"
        ticket_booking = mommy.make_recipe('booking.ticket_booking', paid=False)
        invoice_id = helpers.create_ticket_booking_paypal_transaction(
            ticket_booking.user, ticket_booking
        ).invoice_id

        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('ticket_booking {}'.format(ticket_booking.id)),
                'invoice': b(invoice_id)
            }
        )
        resp = self.paypal_post(params)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PayPalIPN.objects.count(), 1)
        ppipn = PayPalIPN.objects.first()
        self.assertFalse(ppipn.flag)
        self.assertEqual(ppipn.flag_info, '')

        ticket_booking.refresh_from_db()
        self.assertTrue(ticket_booking.paid)
        # 2 emails sent, to user and studio
        self.assertEqual(
            len(mail.outbox), 2,
            "NOTE: Fails if SEND_ALL_STUDIO_EMAILS!=True in env/test settings"
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_only_updates_relevant_booking(self, mock_postback):
        mock_postback.return_value = b"VERIFIED"
        user = mommy.make_recipe('booking.user')
        booking = mommy.make_recipe('booking.booking', paid=False)
        mommy.make_recipe('booking.booking', paid=False, _quantity=5)
        invoice_id = helpers.create_booking_paypal_transaction(
            booking.user, booking
        ).invoice_id

        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking {}'.format(booking.id)),
                'invoice': b(invoice_id)
            }
        )
        resp = self.paypal_post(params)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PayPalIPN.objects.count(), 1)
        ppipn = PayPalIPN.objects.first()
        self.assertFalse(ppipn.flag)
        self.assertEqual(ppipn.flag_info, '')

        booking.refresh_from_db()
        self.assertTrue(booking.paid)
        # 2 emails sent, to user and studio
        self.assertEqual(
            len(mail.outbox), 2,
            "NOTE: Fails if SEND_ALL_STUDIO_EMAILS!=True in env/test settings"
        )

        for bkg in Booking.objects.all():
            if bkg.id == booking.id:
                self.assertTrue(bkg.paid)
            else:
                self.assertFalse(bkg.paid)

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_url_without_booking_trans_object(self, mock_postback):
        """
        A PayPalBooking/Block/TicketBookingTransaction object should be created
        when the paypal form button is created (to generate and store the inv
        number and transaction id against each booking type.  In case it isn't,
        we create one when processing the payment
        """
        mock_postback.return_value = b"VERIFIED"
        booking = mommy.make_recipe('booking.booking', paid=False)

        self.assertFalse(PayPalIPN.objects.exists())
        self.assertFalse(PaypalBookingTransaction.objects.exists())

        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking {}'.format(booking.id)),
                'invoice': b''
            }
        )
        resp = self.paypal_post(params)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PayPalIPN.objects.count(), 1)
        ppipn = PayPalIPN.objects.first()
        self.assertFalse(ppipn.flag)
        self.assertEqual(ppipn.flag_info, '')

        self.assertEqual(PaypalBookingTransaction.objects.count(), 1)
        booking.refresh_from_db()
        self.assertTrue(booking.paid)
        # 3 emails sent, to user and studio and support because there is no inv
        self.assertEqual(
            len(mail.outbox), 3,
            "NOTE: Fails if SEND_ALL_STUDIO_EMAILS!=True in env/test settings"
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_url_with_more_than_one_booking_trans_object(
            self, mock_postback
    ):
        """
        The PayPalBooking/Block/TicketBookingTransaction object is created and
        retrieved using the username and event name/date.  If the user changes
        their username between booking and paying, a second Transaction object
        will be created.  In this case, we use the Transaction object that has
        the invoice number that matches the paypal ipn; if the paypal ipn has
        no invoice associated, we use the latest one.
        """
        mock_postback.return_value = b"VERIFIED"
        booking = mommy.make_recipe('booking.booking', paid=False)

        self.assertFalse(PayPalIPN.objects.exists())
        self.assertFalse(PaypalBookingTransaction.objects.exists())

        pptn = helpers.create_booking_paypal_transaction(booking.user, booking)
        pptn.invoice_id = 'invoice_1'
        pptn.save()
        pptn1 = helpers.create_booking_paypal_transaction(booking.user, booking)
        pptn1.invoice_id = 'invoice_2'
        pptn1.save()

        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking {}'.format(booking.id)),
                'invoice': b'invoice_1'
            }
        )
        self.paypal_post(params)
        pptn.refresh_from_db()
        self.assertEqual(b(pptn.transaction_id), IPN_POST_PARAMS['txn_id'])

        booking.refresh_from_db()
        self.assertTrue(booking.paid)
        # 2 emails sent, to user and studio
        self.assertEqual(
            len(mail.outbox), 2,
            "NOTE: Fails if SEND_ALL_STUDIO_EMAILS!=True in env/test settings"
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_url_with_more_than_one_booking_trans_object_no_invoice(
            self, mock_postback
    ):
        mock_postback.return_value = b"VERIFIED"
        booking = mommy.make_recipe('booking.booking', paid=False)

        self.assertFalse(PayPalIPN.objects.exists())
        self.assertFalse(PaypalBookingTransaction.objects.exists())

        pptn = helpers.create_booking_paypal_transaction(booking.user, booking)
        pptn.invoice_id = 'invoice_1'
        pptn.save()
        pptn1 = helpers.create_booking_paypal_transaction(booking.user, booking)
        pptn1.invoice_id = 'invoice_2'
        pptn1.save()

        # if paypal ipn doesn't contain invoice number
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking {}'.format(booking.id)),
                'invoice': b''
            }
        )
        self.paypal_post(params)
        pptn1.refresh_from_db()
        self.assertEqual(b(pptn1.transaction_id), IPN_POST_PARAMS['txn_id'])

        booking.refresh_from_db()
        self.assertTrue(booking.paid)
        # 3 emails sent, to user and studio, and support b/c no invoice id
        self.assertEqual(
            len(mail.outbox), 3,
            "NOTE: Fails if SEND_ALL_STUDIO_EMAILS!=True in env/test settings"
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_url_without_block_trans_object(self, mock_postback):
        """
        A PayPalBooking/Block/TicketBookingTransaction object should be created
        when the paypal form button is created (to generate and store the inv
        number and transaction id against each booking type.  In case it isn't,
        we create one when processing the payment
        """
        mock_postback.return_value = b"VERIFIED"
        block = mommy.make_recipe('booking.block_5', paid=False)

        self.assertFalse(PayPalIPN.objects.exists())
        self.assertFalse(PaypalBlockTransaction.objects.exists())

        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('block {}'.format(block.id)),
                'invoice': b''
            }
        )
        resp = self.paypal_post(params)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PayPalIPN.objects.count(), 1)
        ppipn = PayPalIPN.objects.first()
        self.assertFalse(ppipn.flag)
        self.assertEqual(ppipn.flag_info, '')

        self.assertEqual(PaypalBlockTransaction.objects.count(), 1)
        block.refresh_from_db()
        self.assertTrue(block.paid)
        pptrans = PaypalBlockTransaction.objects.first()
        self.assertEqual(ppipn.invoice, pptrans.invoice_id)

        # 3 emails sent, to user and studio and support because there is no inv
        self.assertEqual(
            len(mail.outbox), 3,
            "NOTE: Fails if SEND_ALL_STUDIO_EMAILS!=True in env/test settings"
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_url_with_more_than_one_block_trans_object(
            self, mock_postback
    ):
        """
        The PayPalBooking/Block/TicketBookingTransaction object is created and
        retrieved using the username and event name/date.  If the user changes
        their username between booking and paying, a second Transaction object
        will be created.  In this case, we use the Transaction object that has
        the invoice number that matches the paypal ipn; if the paypal ipn has
        no invoice associated, we use the latest one.
        """
        mock_postback.return_value = b"VERIFIED"
        block = mommy.make_recipe('booking.block_5', paid=False)

        self.assertFalse(PayPalIPN.objects.exists())
        self.assertFalse(PaypalBlockTransaction.objects.exists())

        pptn = helpers.create_block_paypal_transaction(block.user, block)
        pptn.invoice_id = 'invoice_1'
        pptn.save()
        pptn1 = helpers.create_block_paypal_transaction(block.user, block)
        pptn1.invoice_id = 'invoice_2'
        pptn1.save()

        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('block {}'.format(block.id)),
                'invoice': b'invoice_1'
            }
        )
        self.paypal_post(params)
        pptn.refresh_from_db()
        self.assertEqual(b(pptn.transaction_id), IPN_POST_PARAMS['txn_id'])

        block.refresh_from_db()
        self.assertTrue(block.paid)
        # 2 emails sent, to user and studio
        self.assertEqual(
            len(mail.outbox), 2,
            "NOTE: Fails if SEND_ALL_STUDIO_EMAILS!=True in env/test settings"
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_url_with_more_than_one_block_trans_object_no_invoice(
            self, mock_postback
    ):
        mock_postback.return_value = b"VERIFIED"
        block = mommy.make_recipe('booking.block_5', paid=False)

        self.assertFalse(PayPalIPN.objects.exists())
        self.assertFalse(PaypalBlockTransaction.objects.exists())

        pptn = helpers.create_block_paypal_transaction(block.user, block)
        pptn.invoice_id = 'invoice_1'
        pptn.save()
        pptn1 = helpers.create_block_paypal_transaction(block.user, block)
        pptn1.invoice_id = 'invoice_2'
        pptn1.save()

        # if paypal ipn doesn't contain invoice number
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('block {}'.format(block.id)),
                'invoice': b''
            }
        )
        self.paypal_post(params)
        pptn1.refresh_from_db()
        self.assertEqual(b(pptn1.transaction_id), IPN_POST_PARAMS['txn_id'])

        block.refresh_from_db()
        self.assertTrue(block.paid)
        # 3 emails sent, to user and studio, and support b/c no invoice id
        self.assertEqual(
            len(mail.outbox), 3,
            "NOTE: Fails if SEND_ALL_STUDIO_EMAILS!=True in env/test settings"
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_url_without_tck_bkg_trans_object(self, mock_postback):
        """
        A PayPalBooking/Block/TicketBookingTransaction object should be created
        when the paypal form button is created (to generate and store the inv
        number and transaction id against each booking type.  In case it isn't,
        we create one when processing the payment
        """
        mock_postback.return_value = b"VERIFIED"
        tbooking = mommy.make_recipe('booking.ticket_booking', paid=False)

        self.assertFalse(PayPalIPN.objects.exists())
        self.assertFalse(PaypalTicketBookingTransaction.objects.exists())

        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('ticket_booking {}'.format(tbooking.id)),
                'invoice': b''
            }
        )
        resp = self.paypal_post(params)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PayPalIPN.objects.count(), 1)
        ppipn = PayPalIPN.objects.first()
        self.assertFalse(ppipn.flag)
        self.assertEqual(ppipn.flag_info, '')

        self.assertEqual(PaypalTicketBookingTransaction.objects.count(), 1)
        tbooking.refresh_from_db()
        self.assertTrue(tbooking.paid)
        pptrans = PaypalTicketBookingTransaction.objects.first()
        self.assertEqual(ppipn.invoice, pptrans.invoice_id)
        # 3 emails sent, to user and studio and support because there is no inv
        self.assertEqual(
            len(mail.outbox), 3,
            "NOTE: Fails if SEND_ALL_STUDIO_EMAILS!=True in env/test settings"
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_url_with_more_than_one_ticket_booking_trans_object(
            self, mock_postback
    ):
        """
        The PayPalBooking/Block/TicketBookingTransaction object is created and
        retrieved using the username and event name/date.  If the user changes
        their username between booking and paying, a second Transaction object
        will be created.  In this case, we use the Transaction object that has
        the invoice number that matches the paypal ipn; if the paypal ipn has
        no invoice associated, we use the latest one.
        """
        mock_postback.return_value = b"VERIFIED"
        tbooking = mommy.make_recipe('booking.ticket_booking', paid=False)

        self.assertFalse(PayPalIPN.objects.exists())
        self.assertFalse(PaypalTicketBookingTransaction.objects.exists())

        pptn = helpers.create_ticket_booking_paypal_transaction(
            tbooking.user, tbooking
        )
        pptn.invoice_id = 'invoice_1'
        pptn.save()
        pptn1 = helpers.create_ticket_booking_paypal_transaction(
            tbooking.user, tbooking
        )
        pptn1.invoice_id = 'invoice_2'
        pptn1.save()

        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('ticket_booking {}'.format(tbooking.id)),
                'invoice': b'invoice_1'
            }
        )
        self.paypal_post(params)
        pptn.refresh_from_db()
        self.assertEqual(b(pptn.transaction_id), IPN_POST_PARAMS['txn_id'])

        tbooking.refresh_from_db()
        self.assertTrue(tbooking.paid)
        # 2 emails sent, to user and studio
        self.assertEqual(
            len(mail.outbox), 2,
            "NOTE: Fails if SEND_ALL_STUDIO_EMAILS!=True in env/test settings"
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_url_with_more_than_one_tbkng_trans_object_no_invoice(
            self, mock_postback
    ):
        mock_postback.return_value = b"VERIFIED"
        tbooking = mommy.make_recipe('booking.ticket_booking', paid=False)
        self.assertFalse(PayPalIPN.objects.exists())
        self.assertFalse(PaypalTicketBookingTransaction.objects.exists())

        pptn = helpers.create_ticket_booking_paypal_transaction(
            tbooking.user, tbooking
        )
        pptn.invoice_id = 'invoice_1'
        pptn.save()
        pptn1 = helpers.create_ticket_booking_paypal_transaction(
            tbooking.user, tbooking
        )
        pptn1.invoice_id = 'invoice_2'
        pptn1.save()

        # if paypal ipn doesn't contain invoice number
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('ticket_booking {}'.format(tbooking.id)),
                'invoice': b''
            }
        )
        self.paypal_post(params)
        pptn1.refresh_from_db()
        self.assertEqual(b(pptn1.transaction_id), IPN_POST_PARAMS['txn_id'])

        tbooking.refresh_from_db()
        self.assertTrue(tbooking.paid)
        # 3 emails sent, to user and studio, and support b/c no invoice id
        self.assertEqual(
            len(mail.outbox), 3,
            "NOTE: Fails if SEND_ALL_STUDIO_EMAILS!=True in env/test settings"
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_url_with_refunded_status(self, mock_postback):
        """
        when a paypal payment is refunded, it looks like it posts back to the
        notify url again (since the PayPalIPN is updated).  Test that we can
        identify and process refunded payments.
        """
        mock_postback.return_value = b"VERIFIED"
        booking = mommy.make_recipe('booking.booking', payment_confirmed=True,
                                    paid=True)
        pptrans = helpers.create_booking_paypal_transaction(
            booking.user, booking
        )
        pptrans.transaction_id = "test_trans_id"
        pptrans.save()

        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking {}'.format(booking.id)),
                'invoice': b(pptrans.invoice_id),
                'payment_status': b'Refunded'
            }
        )
        resp = self.paypal_post(params)
        booking.refresh_from_db()
        self.assertFalse(booking.payment_confirmed)
        self.assertFalse(booking.paid)

        self.assertEqual(
            len(mail.outbox), 1,
            "NOTE: Fails if SEND_ALL_STUDIO_EMAILS!=True in env/test settings"
        )

        # emails sent to studio and support
        self.assertEqual(
            mail.outbox[0].to,
            [settings.DEFAULT_STUDIO_EMAIL, settings.SUPPORT_EMAIL],
        )

    @override_settings(SEND_ALL_STUDIO_EMAILS=False)
    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_refunded_emails_not_sent_if_studio_emails_off(self, mock_postback):
        """
        when a paypal payment is refunded, it looks like it posts back to the
        notify url again (since the PayPalIPN is updated).  Test that we can
        identify and process refunded payments.
        """
        mock_postback.return_value = b"VERIFIED"
        booking = mommy.make_recipe('booking.booking', payment_confirmed=True,
                                    paid=True)
        pptrans = helpers.create_booking_paypal_transaction(
            booking.user, booking
        )
        pptrans.transaction_id = "test_trans_id"
        pptrans.save()

        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking {}'.format(booking.id)),
                'invoice': b(pptrans.invoice_id),
                'payment_status': b'Refunded'
            }
        )
        resp = self.paypal_post(params)
        booking.refresh_from_db()
        self.assertFalse(booking.payment_confirmed)
        self.assertFalse(booking.paid)

        # emails not sent
        self.assertEqual(len(mail.outbox), 0)

    def test_paypal_notify_url_with_invalid_date(self):
        """
        There has been one instance of a returned payment which has no info
        except a flag invalid date in the paypal form.  Check that this will
        send a support email
        """
        self.assertFalse(PayPalIPN.objects.exists())
        resp = self.paypal_post(
            {
                "payment_date": b"2015-10-25 01:21:32",
                'charset': b(CHARSET),
                'txn_id': 'test'
            }
        )
        ppipn = PayPalIPN.objects.first()
        self.assertTrue(ppipn.flag)
        self.assertEqual(
            ppipn.flag_info,
            'Invalid form. (payment_date: Enter a valid date/time.)'
        )

        self.assertEqual(mail.outbox[0].to, [settings.SUPPORT_EMAIL])
        self.assertEqual(
            mail.outbox[0].subject,
            'WARNING! Error processing Invalid Payment Notification from PayPal'
        )
        self.assertEqual(
            mail.outbox[0].body,
            'PayPal sent an invalid transaction notification while attempting '
            'to process payment;.\n\nThe flag info was "Invalid form. '
            '(payment_date: Enter a valid date/time.)"\n\nAn additional error '
            'was raised: Unknown object type for payment'
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_payment_received_with_duplicate_txn_flag(self, mock_postback):
        """
        If we get a flagged completed payment, send a warning email.  Most
        likely to happen with a duplicate transaction id
        """
        mock_postback.return_value = b"VERIFIED"
        booking = mommy.make_recipe('booking.booking')
        pptrans = helpers.create_booking_paypal_transaction(
            booking.user, booking
        )
        # make an existing completed paypal ipn
        mommy.make(PayPalIPN, txn_id='test_txn_id', payment_status='Completed')
        self.assertEqual(PayPalIPN.objects.count(), 1)

        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking {}'.format(booking.id)),
                'invoice': b(pptrans.invoice_id),
                'txn_id': 'test_txn_id'
            }
        )
        resp = self.paypal_post(params)
        booking.refresh_from_db()
        ppipn = PayPalIPN.objects.all()[0]
        ppipn1 = PayPalIPN.objects.all()[1]

        self.assertFalse(ppipn.flag)
        self.assertTrue(ppipn1.flag)
        self.assertEqual(ppipn1.flag_info, 'Duplicate txn_id. (test_txn_id)')

        # even if the postback is verified, it is flagged and processed as
        # invalid
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            'WARNING! Invalid Payment Notification received from PayPal'
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    @patch('payments.models.send_processed_payment_emails')
    def test_error_sending_emails_payment_received(
            self, mock_send_emails, mock_postback
    ):
        """
        We send a warning email with the exception if anything else goes wrong
        during the payment processing; most likely to be something wrong with
        sending the emails
        """
        mock_send_emails.side_effect = Exception('Error sending mail')
        mock_postback.return_value = b"VERIFIED"

        booking = mommy.make_recipe('booking.booking')
        pptrans = helpers.create_booking_paypal_transaction(
            booking.user, booking
        )

        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking {}'.format(booking.id)),
                'invoice': b(pptrans.invoice_id),
                'txn_id': 'test_txn_id'
            }
        )
        resp = self.paypal_post(params)
        booking.refresh_from_db()

        ppipn = PayPalIPN.objects.first()
        self.assertFalse(ppipn.flag)

        # even if the postback is verified, it is flagged and processed as
        # invalid
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            '{} There was some problem processing payment for {} id {}'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, 'booking', booking.id
            ),
        )

        self.assertEqual(
            mail.outbox[0].body,
            'Please check your booking and paypal records for invoice # {}, '
            'paypal transaction id test_txn_id.\n\nThe exception '
            'raised was "Error sending mail"'.format(pptrans.invoice_id)
        )

    @patch('payments.models.send_mail')
    def test_error_sending_emails_payment_not_received(self, mock_send_emails):
        """
        We send a warning email with the exception if anything else goes wrong
        during the payment processing; most likely to be something wrong with
        sending the emails, so we need to check the logs
        """
        mock_send_emails.side_effect = Exception('Error sending mail')
        payment_models_logger.warning = Mock()

        booking = mommy.make_recipe('booking.booking')
        pptrans = helpers.create_booking_paypal_transaction(
            booking.user, booking
        )

        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking {}'.format(booking.id)),
                'invoice': b(pptrans.invoice_id),
                'txn_id': 'test_txn_id'
            }
        )

        with self.assertRaises(Exception):
            resp = self.paypal_post(params)
            payment_models_logger.warning.assert_called_with(
                'Problem processing payment_not_received for Booking {}; '
                'invoice_id {}, transaction id: test_txn_id. Exception: '
                'Error sending mail'.format(booking.id, pptrans.invoice)
            )

        booking.refresh_from_db()
        ppipn = PayPalIPN.objects.first()

        self.assertTrue(ppipn.flag)
        self.assertEqual(ppipn.flag_info, 'Invalid postback. (INVALID)')


class PayPalFormTests(TestCase):

    def test_PayPalPaymentsListForm_renders_buy_it_now_button(self):
        booking = mommy.make_recipe('booking.booking')
        pptrans = helpers.create_booking_paypal_transaction(
            booking.user, booking
        )
        form = PayPalPaymentsListForm(
            initial=get_paypal_dict(
                        'http://example.com',
                        booking.event.cost,
                        booking.event,
                        pptrans.invoice_id,
                        '{} {}'.format('booking', booking.id)
                    )
        )
        self.assertIn('Buy it Now', form.render())

    def test_PayPalPaymentsUpdateForm_renders_buy_it_now_button(self):
        booking = mommy.make_recipe('booking.booking')
        pptrans = helpers.create_booking_paypal_transaction(
            booking.user, booking
        )
        form = PayPalPaymentsUpdateForm(
            initial=get_paypal_dict(
                        'http://example.com',
                        booking.event.cost,
                        booking.event,
                        pptrans.invoice_id,
                        '{} {}'.format('booking', booking.id)
                    )
        )
        self.assertIn('Buy it Now', form.render())


class PaymentsAdminTests(TestCase):

    def test_paypal_booking_admin_display(self):
        user = mommy.make_recipe(
            'booking.user', first_name='Test', last_name='User')
        booking = mommy.make_recipe('booking.booking', user=user)
        pptrans = helpers.create_booking_paypal_transaction(
            booking.user, booking
        )

        ppbooking_admin = PaypalBookingTransactionAdmin(
            PaypalBookingTransaction, AdminSite()
        )
        ppbooking_query = ppbooking_admin.get_queryset(None)[0]

        self.assertEqual(
            ppbooking_admin.get_booking_id(ppbooking_query), booking.id
        )
        self.assertEqual(
            ppbooking_admin.get_user(ppbooking_query), 'Test User'
        )
        self.assertEqual(
            ppbooking_admin.get_event(ppbooking_query), booking.event
        )
        self.assertEqual(
            ppbooking_admin.cost(ppbooking_query),
            u"\u00A3{}.00".format(booking.event.cost)
        )

    def test_paypal_block_admin_display(self):
        user = mommy.make_recipe(
            'booking.user', first_name='Test', last_name='User')
        block = mommy.make_recipe('booking.block_5', user=user)
        pptrans = helpers.create_block_paypal_transaction(
            block.user, block
        )

        ppblock_admin = PaypalBlockTransactionAdmin(
            PaypalBlockTransaction, AdminSite()
        )
        ppblock_query = ppblock_admin.get_queryset(None)[0]

        self.assertEqual(
            ppblock_admin.get_block_id(ppblock_query), block.id
        )
        self.assertEqual(
            ppblock_admin.get_user(ppblock_query), 'Test User'
        )
        self.assertEqual(
            ppblock_admin.get_blocktype(ppblock_query), block.block_type
        )
        self.assertEqual(
            ppblock_admin.cost(ppblock_query),
            u"\u00A3{:.2f}".format(block.block_type.cost)
        )
        self.assertEqual(
            ppblock_admin.block_start(ppblock_query),
            block.start_date.strftime('%d %b %Y, %H:%M')
        )
        self.assertEqual(
            ppblock_admin.block_expiry(ppblock_query),
            block.expiry_date.strftime('%d %b %Y, %H:%M')
        )
