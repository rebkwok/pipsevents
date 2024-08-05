from datetime import datetime
from datetime import timezone as dt_timezone
from decimal import Decimal
import re

from model_bakery import baker

from django.test import TestCase
from django.utils import timezone

from common.tests.helpers import PatchRequestMixin
from payments import helpers
from payments.models import PaypalBookingTransaction, PaypalBlockTransaction, \
    PaypalTicketBookingTransaction, PaypalGiftVoucherTransaction


class TestHelpers(PatchRequestMixin, TestCase):

    def test_create_booking_transaction(self):
        user = baker.make_recipe('booking.user', username="testuser")
        booking = baker.make_recipe(
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
        # str returns invoice id and booking id
        self.assertEqual(
            str(booking_txn),
            '{} - booking {}'.format(
                booking_txn.invoice_id, booking_txn.booking.id
            )
        )

    def test_create_multi_booking_transaction(self):
        # test that creating multibooking invoices with events with same names
        # but different dates generates different invoice ids
        user = baker.make_recipe('booking.user', username="testuser")
        booking = baker.make_recipe(
            'booking.booking', user=user, event__name='test event',
            event__date=datetime(2016, 1, 1, 17, 30, tzinfo=dt_timezone.utc)
        )
        booking1 = baker.make_recipe(
            'booking.booking', user=user, event__name='test event1',
            event__date=datetime(2016, 1, 2, 17, 30, tzinfo=dt_timezone.utc)
        )

        invoice1 = helpers.create_multibooking_paypal_transaction(
            user, [booking, booking1]
        )

        booking2 = baker.make_recipe(
            'booking.booking', user=user, event__name='test event',
            event__date=datetime(2016, 1, 3, 17, 30, tzinfo=dt_timezone.utc)
        )
        booking3 = baker.make_recipe(
            'booking.booking', user=user, event__name='test event1',
            event__date=datetime(2016, 1, 4, 17, 30, tzinfo=dt_timezone.utc)
        )

        invoice2 = helpers.create_multibooking_paypal_transaction(
            user, [booking2, booking3]
        )

        self.assertNotEqual(invoice1, invoice2)

    def test_create_existing_booking_transaction(self):
        user = baker.make_recipe('booking.user', username="testuser")
        booking = baker.make_recipe(
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
        user = baker.make_recipe('booking.user', username="testuser")
        booking = baker.make_recipe(
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
        user = baker.make_recipe('booking.user', username="testuser")
        block = baker.make_recipe(
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
        # str returns invoice id and block id
        self.assertEqual(
            str(block_txn),
            '{} - block {}'.format(
                block_txn.invoice_id, block_txn.block.id
            )
        )

    def test_create_existing_block_transaction(self):
        user = baker.make_recipe('booking.user', username="testuser")
        block = baker.make_recipe(
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
        user = baker.make_recipe('booking.user', username="testuser")
        tbooking = baker.make_recipe(
            'booking.ticket_booking', user=user
        )
        tbooking_txn = helpers.create_ticket_booking_paypal_transaction(
            user, tbooking)
        self.assertEqual(tbooking_txn.ticket_booking, tbooking)
        self.assertEqual(
            tbooking_txn.invoice_id, '{}001'.format(tbooking.booking_reference)
        )
        # str returns invoice id and ticket booking id
        self.assertEqual(
            str(tbooking_txn),
            '{} - tkt booking {}'.format(
                tbooking_txn.invoice_id, tbooking_txn.ticket_booking.id
            )
        )

    def test_create_existing_ticket_booking_transaction(self):
        user = baker.make_recipe('booking.user', username="testuser")
        tbooking = baker.make_recipe(
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
        user = baker.make_recipe('booking.user', username="testuser")
        booking = baker.make_recipe(
            'booking.booking', user=user, event__name='test event',
            event__date=datetime(2015, 2, 1, 10, 0, tzinfo=dt_timezone.utc)
        )
        booking1 = baker.make_recipe(
            'booking.booking', user=user, event__name='test event1',
            event__date=datetime(2015, 2, 1, 10, 0, tzinfo=dt_timezone.utc)
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
        user = baker.make_recipe('booking.user', username="testuser")
        block = baker.make_recipe(
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
        user = baker.make_recipe('booking.user', username="testuser")
        block = baker.make_recipe(
            'booking.block', user=user,
            block_type__event_type__subtype="Pole Level Class",
            block_type__size=10
        )
        block1 = baker.make_recipe(
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
        user = baker.make_recipe('booking.user', username="testuser")
        tbooking = baker.make_recipe('booking.ticket_booking', user=user)
        tbooking.booking_reference = "ref"
        tbooking.save()
        tbooking1 = baker.make_recipe('booking.ticket_booking', user=user)
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
        user = baker.make_recipe('booking.user', username="testuser")
        tbooking = baker.make_recipe(
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

    def test_create_gift_voucher_transaction_with_existing_no_txn_id(self):
        voucher_type = baker.make("booking.GiftVoucherType", block_type__cost=10)
        block_voucher = baker.make("booking.BlockVoucher", code="1234")
        block_voucher.block_types.add(voucher_type.block_type)

        transaction = baker.make(
            PaypalGiftVoucherTransaction, 
            invoice_id=f"gift-voucher-1234-inv#001",
            transaction_id=None,
            voucher_type=voucher_type,
            voucher_code="1234"
        )
        new_txn = helpers.create_gift_voucher_paypal_transaction(voucher_type, "1234")
        assert new_txn.id == transaction.id
        transaction.refresh_from_db()
        assert str(new_txn) == str(transaction)


    def test_create_gift_voucher_transaction_with_existing(self):
        voucher_type = baker.make("booking.GiftVoucherType", block_type__cost=10)
        block_voucher = baker.make("booking.BlockVoucher", code="1234")
        block_voucher.block_types.add(voucher_type.block_type)

        transaction = baker.make(
            PaypalGiftVoucherTransaction, 
            invoice_id=f"gift-voucher-1234-inv#124",
            transaction_id="txn1",
            voucher_type=voucher_type,
            voucher_code="1234"
        )
        new_txn = helpers.create_gift_voucher_paypal_transaction(voucher_type, "1234")
        assert new_txn.id != transaction.id
        assert new_txn.invoice_id == "gift-voucher-1234-inv#125"


    def test_create_gift_voucher_transaction_with_existing_invoice(self):
        voucher_type = baker.make("booking.GiftVoucherType", block_type__cost=10)
        block_voucher = baker.make("booking.BlockVoucher", code="1234")
        block_voucher.block_types.add(voucher_type.block_type)

        transaction = baker.make(
            PaypalGiftVoucherTransaction, 
            invoice_id=f"gift-voucher-1234-inv#001",
        )
        new_txn = helpers.create_gift_voucher_paypal_transaction(voucher_type, "1234")
        assert new_txn.id != transaction.id
        assert re.match("gift-voucher-1234-inv#\d{3}001", new_txn.invoice_id)
