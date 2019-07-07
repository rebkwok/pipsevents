# -*- coding: utf-8 -*-

from model_mommy import mommy
from unittest.mock import Mock, patch

from django.conf import settings
from django.core import mail
from django.urls import reverse
from django.test import TestCase, override_settings

from booking.models import Booking, BlockVoucher, EventVoucher, \
    UsedBlockVoucher, UsedEventVoucher
from common.tests.helpers import PatchRequestMixin

from payments import helpers
from payments.models import PaypalBookingTransaction, PaypalBlockTransaction, \
    PaypalTicketBookingTransaction
from payments.models import logger as payment_models_logger

from paypal.standard.ipn.models import PayPalIPN

from six import b, text_type
from six.moves.urllib.parse import urlencode


# Parameters are all bytestrings, so we can construct a bytestring
# request the same way that Paypal does.
CHARSET = "windows-1252"
TEST_RECEIVER_EMAIL = 'dummy-email@hotmail.com'
IPN_POST_PARAMS = {
    "mc_gross": b"7.00",
    "invoice": b"user-PL1-2411152010-inv001",
    "protection_eligibility": b"Ineligible",
    "txn_id": b"51403485VH153354B",
    "last_name": b"User",
    "receiver_email": b(TEST_RECEIVER_EMAIL),
    "payer_id": b"BN5JZ2V7MLEV4",
    "tax": b"0.00",
    "payment_date": b"23:04:06 Feb 02, 2009 PST",
    "first_name": b"Test",
    "mc_fee": b"0.44",
    "notify_version": b"3.8",
    "custom": b"booking 1",
    "payer_status": b"verified",
    "payment_status": b"Completed",
    "business": b(TEST_RECEIVER_EMAIL),
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


@override_settings(DEFAULT_PAYPAL_EMAIL=TEST_RECEIVER_EMAIL)
class PaypalSignalsTests(PatchRequestMixin, TestCase):

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
                ppipn.flag_info, 'Booking(s) with id(s) 1 does not exist'
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
                ppipn.flag_info, 'Block(s) with id(s) 1 does not exist'
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
        booking = mommy.make_recipe(
            'booking.booking_with_user',
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
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
    def test_paypal_notify_url_with_complete_status_multiple_bookings(
            self, mock_postback
    ):
        mock_postback.return_value = b"VERIFIED"
        user = mommy.make_recipe('booking.user')
        bookings = mommy.make_recipe(
            'booking.booking', user=user,
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL,
            _quantity=3
        )
        invoice = helpers.create_multibooking_paypal_transaction(
            user, bookings
        )
        self.assertEqual(PaypalBookingTransaction.objects.count(), 3)

        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking {}'.format(
                    ','.join([str(booking.id) for booking in bookings])
                )),
                'invoice': b(invoice),
                'txn_id': b'test_txn_id'
            }
        )
        for pptrans in PaypalBookingTransaction.objects.all():
            self.assertIsNone(pptrans.transaction_id)
        resp = self.paypal_post(params)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PayPalIPN.objects.count(), 1)
        ppipn = PayPalIPN.objects.first()
        self.assertFalse(ppipn.flag)
        self.assertEqual(ppipn.flag_info, '')

        # check paypal trans objs are updated
        for pptrans in PaypalBookingTransaction.objects.all():
            self.assertEqual(pptrans.transaction_id, 'test_txn_id')

        for booking in bookings:
            booking.refresh_from_db()
            self.assertTrue(booking.paid)
            self.assertTrue(booking.payment_confirmed)
            self.assertFalse(booking.paypal_pending)

        # 2 emails sent, to user and studio
        self.assertEqual(
            len(mail.outbox), 2,
            "NOTE: Fails if SEND_ALL_STUDIO_EMAILS!=True in env/test settings"
        )

        for email in mail.outbox:
            self.assertIn(
                'Payment processed for booking id {}'.format(
                    ', '.join([str(booking.id) for booking in bookings])
                ),
                email.subject
            )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_complete_status_multiple_bookings_some_invalid(
            self, mock_postback
    ):
        mock_postback.return_value = b"VERIFIED"
        user = mommy.make_recipe('booking.user')
        bookings = mommy.make_recipe(
            'booking.booking', user=user,
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL,
            _quantity=3
        )
        invoice = helpers.create_multibooking_paypal_transaction(
            user, bookings
        )
        self.assertEqual(PaypalBookingTransaction.objects.count(), 3)

        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking {},0'.format(
                    ','.join([str(booking.id) for booking in bookings])
                )),
                'invoice': b(invoice),
                'txn_id': b'test_txn_id'
            }
        )
        for pptrans in PaypalBookingTransaction.objects.all():
            self.assertIsNone(pptrans.transaction_id)
        resp = self.paypal_post(params)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PayPalIPN.objects.count(), 1)
        ppipn = PayPalIPN.objects.first()
        self.assertFalse(ppipn.flag)
        self.assertEqual(ppipn.flag_info, '')

        # support emails sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [settings.SUPPORT_EMAIL])
        self.assertEqual(email.subject, 'WARNING! Error processing PayPal IPN')
        self.assertIn(
            'Error raised: Booking(s) with id(s) 0 does not exist', email.body)

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_url_with_complete_status_multiple_blocks(
            self, mock_postback
    ):
        mock_postback.return_value = b"VERIFIED"
        user = mommy.make_recipe('booking.user')
        blocks = mommy.make_recipe(
            'booking.block', user=user,
            block_type__paypal_email=settings.DEFAULT_PAYPAL_EMAIL,
            _quantity=3
        )
        invoice = helpers.create_multiblock_paypal_transaction(
            user, blocks
        )
        self.assertEqual(PaypalBlockTransaction.objects.count(), 3)

        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('block {}'.format(
                    ','.join([str(block.id) for block in blocks])
                )),
                'invoice': b(invoice),
                'txn_id': b'test_txn_id'
            }
        )
        for pptrans in PaypalBlockTransaction.objects.all():
            self.assertIsNone(pptrans.transaction_id)
        resp = self.paypal_post(params)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PayPalIPN.objects.count(), 1)
        ppipn = PayPalIPN.objects.first()
        self.assertFalse(ppipn.flag)
        self.assertEqual(ppipn.flag_info, '')

        # check paypal trans objs are updated
        for pptrans in PaypalBlockTransaction.objects.all():
            self.assertEqual(pptrans.transaction_id, 'test_txn_id')

        for block in blocks:
            block.refresh_from_db()
            self.assertTrue(block.paid)
            self.assertFalse(block.paypal_pending)

        # 2 emails sent, to user and studio
        self.assertEqual(
            len(mail.outbox), 2,
            "NOTE: Fails if SEND_ALL_STUDIO_EMAILS!=True in env/test settings"
        )

        for email in mail.outbox:
            self.assertIn(
                'Payment processed for block id {}'.format(
                    ', '.join([str(block.id) for block in blocks])
                ),
                email.subject
            )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_complete_status_multiple_blocks_some_invalid(
            self, mock_postback
    ):
        mock_postback.return_value = b"VERIFIED"
        user = mommy.make_recipe('booking.user')
        blocks = mommy.make_recipe(
            'booking.block', user=user,
            block_type__paypal_email=settings.DEFAULT_PAYPAL_EMAIL,
            _quantity=3
        )
        invoice = helpers.create_multiblock_paypal_transaction(
            user, blocks
        )
        self.assertEqual(PaypalBlockTransaction.objects.count(), 3)

        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('block 0,{},99999'.format(
                    ','.join([str(block.id) for block in blocks])
                )),
                'invoice': b(invoice),
                'txn_id': b'test_txn_id'
            }
        )
        for pptrans in PaypalBlockTransaction.objects.all():
            self.assertIsNone(pptrans.transaction_id)
        resp = self.paypal_post(params)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PayPalIPN.objects.count(), 1)
        ppipn = PayPalIPN.objects.first()
        self.assertFalse(ppipn.flag)
        self.assertEqual(ppipn.flag_info, '')

        # support emails sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [settings.SUPPORT_EMAIL])
        self.assertEqual(email.subject, 'WARNING! Error processing PayPal IPN')
        self.assertIn(
            'Error raised: Block(s) with id(s) 0, 99999 does not exist',
            email.body
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_ipn_obj_with_space_replaced(self, mock_postback):
        # occasionally paypal sends back the custom field with the space
        # replaced with '+'. i.e. "booking+1" instead of "booking 1"
        mock_postback.return_value = b"VERIFIED"
        booking = mommy.make_recipe(
            'booking.booking_with_user',
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
        pptrans = helpers.create_booking_paypal_transaction(
            booking.user, booking
        )

        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking+{}'.format(booking.id)),
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
            'was "{}"\n\nError raised: Booking(s) with id(s) 1 does not exist'.format(
                ppipn.txn_id, ppipn.flag_info,
            )
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_successful_paypal_payment_sends_emails(self, mock_postback):
        mock_postback.return_value = b"VERIFIED"
        booking = mommy.make_recipe(
            'booking.booking_with_user',
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
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
        booking = mommy.make_recipe(
            'booking.booking_with_user',
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
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

        # 1 email sent, to studio only
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [booking.user.email])

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_successful_paypal_payment_updates_booking(self, mock_postback):
        mock_postback.return_value = b"VERIFIED"
        booking = mommy.make_recipe(
            'booking.booking_with_user', payment_confirmed=False, paid=False,
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
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
        self.paypal_post(params)
        booking.refresh_from_db()
        self.assertTrue(booking.payment_confirmed)
        self.assertTrue(booking.paid)

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_url_with_complete_status_no_invoice_number(self, mock_postback):
        mock_postback.return_value = b"VERIFIED"
        booking = mommy.make_recipe(
            'booking.booking_with_user', payment_confirmed=False, paid=False,
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
        helpers.create_booking_paypal_transaction(
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
        self.paypal_post(params)
        booking.refresh_from_db()
        self.assertTrue(booking.payment_confirmed)
        self.assertTrue(booking.paid)

        # 3 emails sent - support to notify about missing inv, studio, user
        self.assertEqual(
            len(mail.outbox), 3,
            "NOTE: Fails if SEND_ALL_STUDIO_EMAILS!=True in env/test settings"
        )
        self.assertEqual(
            mail.outbox[0].subject,
            '{} No invoice number on paypal ipn for booking id {}'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.id
            )
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_url_with_block(self, mock_postback):
        mock_postback.return_value = b"VERIFIED"
        block = mommy.make_recipe(
            'booking.block_10', paid=False,
            block_type__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
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
        ticket_booking = mommy.make_recipe(
            'booking.ticket_booking', paid=False,
            ticketed_event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
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
        booking = mommy.make_recipe(
            'booking.booking_with_user', paid=False,
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
        mommy.make_recipe('booking.booking_with_user', paid=False, _quantity=5)
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
        booking = mommy.make_recipe(
            'booking.booking_with_user', paid=False,
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )

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
        booking = mommy.make_recipe(
            'booking.booking_with_user', paid=False,
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )

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
        booking = mommy.make_recipe(
            'booking.booking_with_user', paid=False,
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )

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
        block = mommy.make_recipe(
            'booking.block_5', paid=False,
            block_type__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )

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
        block = mommy.make_recipe(
            'booking.block_5', paid=False,
            block_type__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )

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
        block = mommy.make_recipe(
            'booking.block_5', paid=False,
            block_type__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )

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
        tbooking = mommy.make_recipe(
            'booking.ticket_booking', paid=False,
            ticketed_event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )

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
        tbooking = mommy.make_recipe(
            'booking.ticket_booking', paid=False,
            ticketed_event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )

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
        tbooking = mommy.make_recipe(
            'booking.ticket_booking', paid=False,
            ticketed_event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
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
        booking = mommy.make_recipe(
            'booking.booking_with_user', payment_confirmed=True, paid=True,
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
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
        self.paypal_post(params)
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
        booking = mommy.make_recipe(
            'booking.booking_with_user', payment_confirmed=True, paid=True,
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
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
        self.paypal_post(params)
        booking.refresh_from_db()
        self.assertFalse(booking.payment_confirmed)
        self.assertFalse(booking.paid)

        # emails not sent
        self.assertEqual(len(mail.outbox), 0)

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_used_event_voucher_deleted_on_refund(self, mock_postback):
        mock_postback.return_value = b"VERIFIED"
        booking = mommy.make_recipe(
            'booking.booking_with_user', payment_confirmed=True, paid=True,
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
        voucher = mommy.make(EventVoucher, code='test')
        voucher.event_types.add(booking.event.event_type)
        mommy.make(UsedEventVoucher, voucher=voucher, user=booking.user)
        pptrans = helpers.create_booking_paypal_transaction(
            booking.user, booking
        )
        pptrans.transaction_id = "test_trans_id"
        pptrans.voucher_code = voucher.code
        pptrans.save()

        self.assertFalse(PayPalIPN.objects.exists())
        self.assertEqual(UsedEventVoucher.objects.count(), 1)
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking {} test'.format(booking.id)),
                'invoice': b(pptrans.invoice_id),
                'payment_status': b'Refunded'
            }
        )
        self.paypal_post(params)
        booking.refresh_from_db()
        self.assertFalse(booking.payment_confirmed)
        self.assertFalse(booking.paid)

        # used voucher has been deleted
        self.assertFalse(UsedEventVoucher.objects.exists())

        # paypal trans object still has record of voucher code used
        pptrans.refresh_from_db()
        self.assertEqual(pptrans.voucher_code, 'test')

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_only_1_used_event_voucher_deleted_on_refund(self, mock_postback):
        mock_postback.return_value = b"VERIFIED"
        booking = mommy.make_recipe(
            'booking.booking_with_user', payment_confirmed=True, paid=True,
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
        voucher = mommy.make(EventVoucher, code='test')
        voucher.event_types.add(booking.event.event_type)
        mommy.make(
            UsedEventVoucher, voucher=voucher, user=booking.user, _quantity=3
        )
        pptrans = helpers.create_booking_paypal_transaction(
            booking.user, booking
        )
        pptrans.transaction_id = "test_trans_id"
        pptrans.voucher_code = voucher.code
        pptrans.save()

        self.assertFalse(PayPalIPN.objects.exists())
        self.assertEqual(UsedEventVoucher.objects.count(), 3)
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking {} test'.format(booking.id)),
                'invoice': b(pptrans.invoice_id),
                'payment_status': b'Refunded'
            }
        )
        self.paypal_post(params)
        booking.refresh_from_db()
        self.assertFalse(booking.payment_confirmed)
        self.assertFalse(booking.paid)

        # one of the 3 used vouchers has been deleted
        self.assertEqual(UsedEventVoucher.objects.count(), 2)

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_used_block_voucher_deleted_on_refund(self, mock_postback):
        mock_postback.return_value = b"VERIFIED"
        block = mommy.make_recipe(
            'booking.block',
            block_type__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
        voucher = mommy.make(BlockVoucher, code='test')
        voucher.block_types.add(block.block_type)
        mommy.make(UsedBlockVoucher, voucher=voucher, user=block.user)
        pptrans = helpers.create_block_paypal_transaction(block.user, block)
        pptrans.transaction_id = "test_trans_id"
        pptrans.voucher_code = voucher.code
        pptrans.save()

        self.assertFalse(PayPalIPN.objects.exists())
        self.assertEqual(UsedBlockVoucher.objects.count(), 1)
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('block {} test'.format(block.id)),
                'invoice': b(pptrans.invoice_id),
                'payment_status': b'Refunded'
            }
        )
        self.paypal_post(params)
        block.refresh_from_db()
        self.assertFalse(block.paid)

        # used voucher has been deleted
        self.assertFalse(UsedBlockVoucher.objects.exists())

        # paypal trans object still has record of voucher code used
        pptrans.refresh_from_db()
        self.assertEqual(pptrans.voucher_code, 'test')

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_refund_processed_if_no_used_voucher(self, mock_postback):
        mock_postback.return_value = b"VERIFIED"
        booking = mommy.make_recipe(
            'booking.booking_with_user', payment_confirmed=True, paid=True,
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
        voucher = mommy.make(EventVoucher, code='test')
        voucher.event_types.add(booking.event.event_type)

        # voucher exists, but not UsedEventVoucher
        pptrans = helpers.create_booking_paypal_transaction(
            booking.user, booking
        )
        pptrans.transaction_id = "test_trans_id"
        pptrans.voucher_code = voucher.code
        pptrans.save()

        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking {} test'.format(booking.id)),
                'invoice': b(pptrans.invoice_id),
                'payment_status': b'Refunded'
            }
        )
        self.paypal_post(params)
        booking.refresh_from_db()
        # refund processed
        self.assertFalse(booking.payment_confirmed)
        self.assertFalse(booking.paid)

        # paypal trans object still has record of voucher code used
        pptrans.refresh_from_db()
        self.assertEqual(pptrans.voucher_code, 'test')

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_refund_processed_if_no_used_block_voucher(self, mock_postback):
        mock_postback.return_value = b"VERIFIED"
        block = mommy.make_recipe('booking.block')
        voucher = mommy.make(BlockVoucher, code='test')
        voucher.block_types.add(block.block_type)

        # voucher exists, but not UsedBlockVoucher
        pptrans = helpers.create_block_paypal_transaction(block.user, block)
        pptrans.transaction_id = "test_trans_id"
        pptrans.voucher_code = voucher.code
        pptrans.save()

        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('block {} test'.format(block.id)),
                'invoice': b(pptrans.invoice_id),
                'payment_status': b'Refunded'
            }
        )
        self.paypal_post(params)
        block.refresh_from_db()
        # refund processed
        self.assertFalse(block.paid)

        # paypal trans object still has record of voucher code used
        pptrans.refresh_from_db()
        self.assertEqual(pptrans.voucher_code, 'test')

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_date_format_with_extra_spaces(self, mock_postback):
        mock_postback.return_value = b"VERIFIED"
        booking = mommy.make_recipe(
            'booking.booking_with_user', payment_confirmed=True, paid=True,
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
        pptrans = helpers.create_booking_paypal_transaction(
            booking.user, booking
        )
        pptrans.transaction_id = "test_trans_id"
        pptrans.save()

        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                "payment_date": b"01:21:32  Jan   25  2015 PDT",
                'invoice': b(pptrans.invoice_id),
                'custom': b('booking {}'.format(booking.id))
            }
        )

        # Check extra spaces
        self.paypal_post(params)
        ppipn = PayPalIPN.objects.latest('id')
        self.assertFalse(ppipn.flag)

    def test_paypal_notify_url_with_invalid_date(self):
        """
        There has been one instance of a returned payment which has no info
        except a flag invalid date in the paypal form.  Check that this will
        send a support email
        """
        self.assertFalse(PayPalIPN.objects.exists())
        self.paypal_post(
            {
                "payment_date": b"2015-10-25 01:21:32",
                'charset': b(CHARSET),
                'txn_id': 'test',
            }
        )
        ppipn = PayPalIPN.objects.first()
        self.assertTrue(ppipn.flag)
        self.assertEqual(
            ppipn.flag_info,
            'Invalid form. (payment_date: Invalid date format '
            '2015-10-25 01:21:32: not enough values to unpack (expected 5, got 2))'
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
            '(payment_date: Invalid date format '
            '2015-10-25 01:21:32: not enough values to unpack (expected 5, got 2))"'
            '\n\nAn additional error was raised: Unknown object type for '
            'payment'
        )

    def test_paypal_notify_url_with_invalid_date_formats(self):
        """
        Check other invalid date formats
        %H:%M:%S %b. %d, %Y PDT is the expected format

        """
        # Fails because 25th cannot be convered to int
        self.paypal_post(
            {
                "payment_date": b"01:21:32 Jan 25th 2015 PDT",
                'charset': b(CHARSET),
                'txn_id': 'test'
            }
        )
        ppipn = PayPalIPN.objects.latest('id')
        self.assertTrue(ppipn.flag)
        self.assertEqual(
            ppipn.flag_info,
            "Invalid form. (payment_date: Invalid date format "
            "01:21:32 Jan 25th 2015 PDT: invalid literal for int() with "
            "base 10: '25th')"
        )

        # Fails because month is not in Mmm format
        self.paypal_post(
            {
                "payment_date": b"01:21:32 01 25 2015 PDT",
                'charset': b(CHARSET),
                'txn_id': 'test'
            }
        )
        ppipn = PayPalIPN.objects.latest('id')
        self.assertTrue(ppipn.flag)
        self.assertEqual(
            ppipn.flag_info,
            "Invalid form. (payment_date: Invalid date format "
            "01:21:32 01 25 2015 PDT: '01' is not in list)"
        )

        # Fails because month is not in Mmm format
        self.paypal_post(
            {
                "payment_date": b"01:21:32 January 25 2015 PDT",
                'charset': b(CHARSET),
                'txn_id': 'test'
            }
        )
        ppipn = PayPalIPN.objects.latest('id')
        self.assertTrue(ppipn.flag)
        self.assertEqual(
            ppipn.flag_info,
            "Invalid form. (payment_date: Invalid date format "
            "01:21:32 January 25 2015 PDT: 'January' is not in list)"
        )

        # Fails because year part cannot be convered to int
        self.paypal_post(
            {
                "payment_date": b"01:21:32 Jan 25 2015a PDT",
                'charset': b(CHARSET),
                'txn_id': 'test'
            }
        )
        ppipn = PayPalIPN.objects.latest('id')
        self.assertTrue(ppipn.flag)
        self.assertEqual(
            ppipn.flag_info,
            "Invalid form. (payment_date: Invalid date format "
            "01:21:32 Jan 25 2015a PDT: invalid literal for int() with "
            "base 10: '2015a')"
        )

        # No seconds part; fails on splitting the time
        self.paypal_post(
            {
                "payment_date": b"01:28 Jan 25 2015 PDT",
                'charset': b(CHARSET),
                'txn_id': 'test'
            }
        )
        ppipn = PayPalIPN.objects.latest('id')
        self.assertTrue(ppipn.flag)
        self.assertEqual(
            ppipn.flag_info,
            "Invalid form. (payment_date: Invalid date format "
            "01:28 Jan 25 2015 PDT: not enough values to unpack (expected 3, got 2))"
        )

        # Can be split and day/month/year parts converted but invalid date so
        #  conversion to datetime sails
        self.paypal_post(
            {
                "payment_date": b"01:21:32 Jan 49 2015 PDT",
                'charset': b(CHARSET),
                'txn_id': 'test'
            }
        )
        ppipn = PayPalIPN.objects.latest('id')
        self.assertTrue(ppipn.flag)
        self.assertEqual(
            ppipn.flag_info,
            "Invalid form. (payment_date: Invalid date format "
            "01:21:32 Jan 49 2015 PDT: day is out of range for month)"
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_payment_received_with_duplicate_txn_flag(self, mock_postback):
        """
        If we get a flagged completed duplicate transaction id payment, send a warning email.
        """
        mock_postback.return_value = b"VERIFIED"
        booking = mommy.make_recipe(
            'booking.booking_with_user',
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
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
        self.paypal_post(params)
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
    def test_payment_received_with_non_duplicate_txn_flag(self, mock_postback):
        """
        If we get a flagged completed payment with flag other than duplicate transaction,
        process payment and send a warning email.  Do not send email to student.
        """
        mock_postback.return_value = b"Internal Server Error"
        booking = mommy.make_recipe(
            'booking.booking_with_user',
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
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
        self.paypal_post(params)
        booking.refresh_from_db()
        ppipn = PayPalIPN.objects.first()

        self.assertTrue(ppipn.flag)
        self.assertEqual(ppipn.flag_info, 'Invalid postback. (Internal Server Error)')

        # even though the ipn is flagged, it is processed, and warning email sent
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)
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

        booking = mommy.make_recipe(
            'booking.booking_with_user',
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
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
        self.paypal_post(params)
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

        booking = mommy.make_recipe(
            'booking.booking_with_user',
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
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
            self.paypal_post(params)
            payment_models_logger.warning.assert_called_with(
                'Problem processing payment_not_received for Booking {}; '
                'invoice_id {}, transaction id: test_txn_id. Exception: '
                'Error sending mail'.format(booking.id, pptrans.invoice)
            )

        booking.refresh_from_db()
        ppipn = PayPalIPN.objects.first()

        self.assertTrue(ppipn.flag)
        self.assertEqual(ppipn.flag_info, 'Invalid postback. (INVALID)')

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_with_voucher_code(self, mock_postback):
        mock_postback.return_value = b"VERIFIED"
        ev_type = mommy.make_recipe('booking.event_type_PC')
        voucher = mommy.make(EventVoucher, code='test', discount=10)
        voucher.event_types.add(ev_type)
        user = mommy.make_recipe('booking.user')
        booking = mommy.make_recipe(
            'booking.booking_with_user', event__event_type=ev_type,
            event__name='pole level 1', user=user,
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
        pptrans = helpers.create_booking_paypal_transaction(
            booking.user, booking
        )

        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking {} {} {}'.format(
                    booking.id, booking.user.email, voucher.code
                )),
                'invoice': b(pptrans.invoice_id),
                'txn_id': b'test_txn_id',
            }
        )
        self.assertIsNone(pptrans.transaction_id)
        self.paypal_post(params)
        self.assertEqual(PayPalIPN.objects.count(), 1)
        ppipn = PayPalIPN.objects.first()
        self.assertFalse(ppipn.flag)
        self.assertEqual(ppipn.flag_info, '')

        booking.refresh_from_db()
        self.assertTrue(booking.paid)

        pptrans.refresh_from_db()
        self.assertEqual(pptrans.voucher_code, voucher.code)
        self.assertEqual(UsedEventVoucher.objects.count(), 1)
        self.assertEqual(UsedEventVoucher.objects.first().user, user)

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_with_invalid_voucher_code(self, mock_postback):
        """
        Test that paypal is processed properly and marked as paid if an
        invalid voucher code is included. Warning mail sent to support.
        """
        mock_postback.return_value = b"VERIFIED"
        ev_type = mommy.make_recipe('booking.event_type_PC')

        user = mommy.make_recipe('booking.user')
        booking = mommy.make_recipe(
            'booking.booking_with_user', event__event_type=ev_type,
            event__name='pole level 1', user=user,
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
        pptrans = helpers.create_booking_paypal_transaction(
            booking.user, booking
        )

        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking {} {} invalid_code'.format(
                    booking.id, booking.user.email
                )),
                'invoice': b(pptrans.invoice_id),
                'txn_id': b'test_txn_id',
            }
        )
        self.assertIsNone(pptrans.transaction_id)
        self.paypal_post(params)
        self.assertEqual(PayPalIPN.objects.count(), 1)
        ppipn = PayPalIPN.objects.first()
        self.assertFalse(ppipn.flag)
        self.assertEqual(ppipn.flag_info, '')

        booking.refresh_from_db()
        self.assertTrue(booking.paid)

        # email to user, studio, and support email
        self.assertEqual(len(mail.outbox), 3)
        support_email = mail.outbox[2]
        self.assertEqual(support_email.to, [settings.SUPPORT_EMAIL])
        self.assertEqual(
            support_email.subject,
            '{} There was some problem processing payment for booking '
            'id {}'.format(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.id)
        )
        self.assertIn(
            'The exception raised was "EventVoucher matching query does '
            'not exist.',
            support_email.body
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_with_block_voucher_code(self, mock_postback):
        mock_postback.return_value = b"VERIFIED"
        block_type = mommy.make_recipe(
            'booking.blocktype', paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
        voucher = mommy.make(BlockVoucher, code='test', discount=10)
        voucher.block_types.add(block_type)
        user = mommy.make_recipe('booking.user')
        block = mommy.make_recipe(
            'booking.block', block_type=block_type,
            user=user,
        )
        pptrans = helpers.create_block_paypal_transaction(
            block.user, block
        )

        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('block {} {} {}'.format(
                    block.id, block.user.email, voucher.code
                )),
                'invoice': b(pptrans.invoice_id),
                'txn_id': b'test_txn_id',
            }
        )
        self.assertIsNone(pptrans.transaction_id)
        self.paypal_post(params)
        self.assertEqual(PayPalIPN.objects.count(), 1)
        ppipn = PayPalIPN.objects.first()
        self.assertFalse(ppipn.flag)
        self.assertEqual(ppipn.flag_info, '')

        block.refresh_from_db()
        self.assertTrue(block.paid)

        pptrans.refresh_from_db()
        self.assertEqual(pptrans.voucher_code, voucher.code)
        self.assertEqual(UsedBlockVoucher.objects.count(), 1)
        self.assertEqual(UsedBlockVoucher.objects.first().user, user)

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_with_invalid_block_voucher_code(self, mock_postback):
        """
        Test that paypal is processed properly and marked as paid if an
        invalid voucher code is included. Warning mail sent to support.
        """
        mock_postback.return_value = b"VERIFIED"
        block_type = mommy.make_recipe(
            'booking.blocktype', paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )

        user = mommy.make_recipe('booking.user')
        block = mommy.make_recipe(
            'booking.block', block_type=block_type,
            user=user,
        )
        pptrans = helpers.create_block_paypal_transaction(
            block.user, block
        )

        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('block {} {} invalid_code'.format(
                    block.id, block.user.email
                )),
                'invoice': b(pptrans.invoice_id),
                'txn_id': b'test_txn_id',
            }
        )
        self.assertIsNone(pptrans.transaction_id)
        self.paypal_post(params)
        self.assertEqual(PayPalIPN.objects.count(), 1)
        ppipn = PayPalIPN.objects.first()
        self.assertFalse(ppipn.flag)
        self.assertEqual(ppipn.flag_info, '')

        block.refresh_from_db()
        self.assertTrue(block.paid)

        # email to user, studio, and support email
        self.assertEqual(len(mail.outbox), 3)
        support_email = mail.outbox[2]
        self.assertEqual(support_email.to, [settings.SUPPORT_EMAIL])
        self.assertEqual(
            support_email.subject,
            '{} There was some problem processing payment for block '
            'id {}'.format(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, block.id)
        )
        self.assertIn(
            'The exception raised was "BlockVoucher matching query does not exist.',
            support_email.body
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_with_mismatched_receiver_email(self, mock_postback):
        """
        Test that error is raised if receiver email doesn't match object's
        paypal_email. Warning mail sent to support.
        """
        mock_postback.return_value = b"VERIFIED"
        ev_type = mommy.make_recipe('booking.event_type_PC')

        user = mommy.make_recipe('booking.user')
        booking = mommy.make_recipe(
            'booking.booking_with_user', event__event_type=ev_type,
            event__name='pole level 1', user=user,
            event__paypal_email='test@test.com'
        )
        pptrans = helpers.create_booking_paypal_transaction(
            booking.user, booking
        )

        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking {}'.format(booking.id)),
                'invoice': b(pptrans.invoice_id),
                'txn_id': b'test_txn_id',
            }
        )
        self.assertIsNone(pptrans.transaction_id)
        self.paypal_post(params)
        self.assertEqual(PayPalIPN.objects.count(), 1)
        ppipn = PayPalIPN.objects.first()
        self.assertTrue(ppipn.flag)
        self.assertEqual(
            ppipn.flag_info,
            'Invalid business email ({})'.format(TEST_RECEIVER_EMAIL)
        )

        booking.refresh_from_db()
        self.assertFalse(booking.paid)

        # email to user, studio, and support email
        self.assertEqual(len(mail.outbox), 1)
        support_email = mail.outbox[0]
        self.assertEqual(support_email.to, [settings.SUPPORT_EMAIL])
        self.assertEqual(
            support_email.subject,
            '{} There was some problem processing payment for booking '
            'id {}'.format(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.id)
        )
        self.assertIn(
            'The exception raised was '
            '"Invalid business email ({})'.format(TEST_RECEIVER_EMAIL),
            support_email.body
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_with_pending_payment_status(self, mock_postback):
        """
        Test that error is raised and warning mail sent to support for a
        payment status that is not Completed or Refunded.
        """
        mock_postback.return_value = b"VERIFIED"
        ev_type = mommy.make_recipe('booking.event_type_PC')

        user = mommy.make_recipe('booking.user')
        booking = mommy.make_recipe(
            'booking.booking_with_user', event__event_type=ev_type,
            event__name='pole level 1', user=user,
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
        pptrans = helpers.create_booking_paypal_transaction(
            booking.user, booking
        )

        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking {}'.format(booking.id)),
                'invoice': b(pptrans.invoice_id),
                'txn_id': b'test_txn_id',
                'payment_status': 'Pending'
            }
        )
        self.assertIsNone(pptrans.transaction_id)
        self.paypal_post(params)
        self.assertEqual(PayPalIPN.objects.count(), 1)
        ppipn = PayPalIPN.objects.first()

        booking.refresh_from_db()
        self.assertFalse(booking.paid)

        # email to support email
        self.assertEqual(len(mail.outbox), 1)
        support_email = mail.outbox[0]
        self.assertEqual(support_email.to, [settings.SUPPORT_EMAIL])
        self.assertEqual(
            support_email.subject,
            '{} There was some problem processing payment for booking '
            'id {}'.format(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.id)
        )
        self.assertIn(
            'The exception raised was "PayPal payment returned with '
            'status PENDING for booking {}; '
            'ipn obj id {} (txn id {}).  This is usually due to an '
            'unrecognised or unverified paypal email address.'.format(
                booking.id, ppipn.id, ppipn.txn_id
            ),
            support_email.body
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_notify_with_unexpected_payment_status(self, mock_postback):
        """
        Test that error is raised and warning mail sent to support for a
        payment status that is not Completed or Refunded.
        """
        mock_postback.return_value = b"VERIFIED"
        ev_type = mommy.make_recipe('booking.event_type_PC')

        user = mommy.make_recipe('booking.user')
        booking = mommy.make_recipe(
            'booking.booking_with_user', event__event_type=ev_type,
            event__name='pole level 1', user=user,
            event__paypal_email=settings.DEFAULT_PAYPAL_EMAIL
        )
        pptrans = helpers.create_booking_paypal_transaction(
            booking.user, booking
        )

        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('booking {}'.format(booking.id)),
                'invoice': b(pptrans.invoice_id),
                'txn_id': b'test_txn_id',
                'payment_status': 'Voided'
            }
        )
        self.assertIsNone(pptrans.transaction_id)
        self.paypal_post(params)
        self.assertEqual(PayPalIPN.objects.count(), 1)
        ppipn = PayPalIPN.objects.first()

        booking.refresh_from_db()
        self.assertFalse(booking.paid)

        # email to support email
        self.assertEqual(len(mail.outbox), 1)
        support_email = mail.outbox[0]
        self.assertEqual(support_email.to, [settings.SUPPORT_EMAIL])
        self.assertEqual(
            support_email.subject,
            '{} There was some problem processing payment for booking '
            'id {}'.format(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.id)
        )
        self.assertIn(
            'The exception raised was "Unexpected payment status VOIDED for '
            'booking {}; ipn obj id {} (txn id {})'.format(
                booking.id, ppipn.id, ppipn.txn_id
            ),
            support_email.body
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_email_check(self, mock_postback):
        """
        Test that a paypal test payment is processed properly and
        email is sent to the user and to support.
        """
        mock_postback.return_value = b"VERIFIED"
        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('paypal_test 0 test_invoice_1 '
                            'test@test.com user@test.com'),
                'receiver_email': 'test@test.com'
            }
        )
        self.assertNotEqual(
            settings.DEFAULT_PAYPAL_EMAIL, params['receiver_email']
        )
        self.paypal_post(params)

        ipn = PayPalIPN.objects.first()
        self.assertEqual(ipn.payment_status, 'Completed')

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ['user@test.com', settings.SUPPORT_EMAIL])
        self.assertEqual(
            email.subject,
            '{} Payment processed for test payment to PayPal email '
            'test@test.com'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
            )
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_email_check_refunded_status(self, mock_postback):
        """
        Test that a refunded paypal test payment is processed properly
        and email is sent to the user and to support.
        """
        mock_postback.return_value = b"VERIFIED"
        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('paypal_test 0 test_invoice_1 '
                            'test@test.com user@test.com'),
                'receiver_email': 'test@test.com',
                'payment_status': 'Refunded'
            }
        )
        self.paypal_post(params)

        ipn = PayPalIPN.objects.first()
        self.assertEqual(ipn.payment_status, 'Refunded')

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ['user@test.com', settings.SUPPORT_EMAIL])
        self.assertEqual(
            email.subject,
            '{} Payment refund processed for test payment to PayPal email '
            'test@test.com'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
            )
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_email_check_pending_status(self, mock_postback):
        """
        Test that a paypal test payment with pending status is processed
        properly and email is sent to the user and to support.
        """
        mock_postback.return_value = b"VERIFIED"
        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('paypal_test 0 test_invoice_1 '
                            'test@test.com user@test.com'),
                'receiver_email': 'test@test.com',
                'payment_status': 'Pending',
            }
        )
        self.assertNotEqual(
            settings.DEFAULT_PAYPAL_EMAIL, params['receiver_email']
        )
        self.paypal_post(params)

        ipn = PayPalIPN.objects.first()
        self.assertEqual(ipn.payment_status, 'Pending')

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ['user@test.com', settings.SUPPORT_EMAIL])
        self.assertEqual(
            email.subject,
            '{} Payment status PENDING for test payment to PayPal email '
            'test@test.com'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
            )
        )

    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_email_check_unexpected_status(self, mock_postback):
        """
        Test that a paypal test payment with unexpected status is processed
        properly and email is sent to the user and to support.
        """
        mock_postback.return_value = b"VERIFIED"
        self.assertFalse(PayPalIPN.objects.exists())
        params = dict(IPN_POST_PARAMS)
        params.update(
            {
                'custom': b('paypal_test 0 test_invoice_1 '
                            'test@test.com user@test.com'),
                'receiver_email': 'test@test.com',
                'payment_status': 'Voided',
            }
        )
        self.assertNotEqual(
            settings.DEFAULT_PAYPAL_EMAIL, params['receiver_email']
        )
        self.paypal_post(params)

        ipn = PayPalIPN.objects.first()
        self.assertEqual(ipn.payment_status, 'Voided')

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ['user@test.com', settings.SUPPORT_EMAIL])

        self.assertEqual(
            email.subject,
            '{} Unexpected payment status VOIDED '
            'for test payment to PayPal email test@test.com'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
            ),
        )

    @patch('payments.models.send_processed_test_confirmation_emails')
    @patch('paypal.standard.ipn.models.PayPalIPN._postback')
    def test_paypal_email_check_unexpected_error(
            self, mock_postback, mock_send_confirmation
    ):
        """
        Test that a paypal test payment that fails in some unexpected way
        sends email to support.
        """
        mock_postback.return_value = b"VERIFIED"
        mock_send_confirmation.side_effect = Exception('Error')
        params = dict(IPN_POST_PARAMS)

        params.update(
            {
                'custom': b('paypal_test 0 test_invoice_1 '
                            'test@test.com user@test.com'),
                'receiver_email': 'test@test.com',
            }
        )
        self.paypal_post(params)

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [settings.SUPPORT_EMAIL])

        self.assertEqual(
            email.subject,
            '{} There was some problem processing payment for paypal_test '
            'payment to paypal email test@test.com'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
            )
        )
        self.assertIn('The exception raised was "Error"', email.body)
