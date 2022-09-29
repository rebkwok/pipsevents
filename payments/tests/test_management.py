import sys

from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

from io import StringIO
from unittest.mock import patch
from model_bakery import baker

from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.conf import settings
from django.core import management
from django.core import mail
from django.db.models import Q
from django.contrib.auth.models import Group, User
from django.utils import timezone

from allauth.socialaccount.models import SocialApp

from paypal.standard.ipn.models import PayPalIPN
from paypal.standard.models import ST_PP_COMPLETED, ST_PP_FAILED

from accounts.models import OnlineDisclaimer
from activitylog.models import ActivityLog
from booking.models import Event, Block, Booking, EventType, BlockType, \
    TicketBooking, Ticket
from common.tests.helpers import _add_user_email_addresses, PatchRequestMixin
from payments.models import PaypalBlockTransaction, PaypalBookingTransaction
from timetable.models import Session


import pytest


pytestmark = pytest.mark.django_db


def test_check_paypal_pending_no_items():
    output = management.call_command('check_paypal_pending')
    assert output == "No booking or blocks to update"


def test_check_paypal_pending_with_paid_items():
    baker.make(Booking, paid=True)
    baker.make(Block, paid=True)

    output = management.call_command('check_paypal_pending')
    assert output == "No booking or blocks to update"


def test_check_paypal_pending_with_unpaid_items():
    baker.make(Booking, paid=False)
    baker.make(Block, paid=False)

    output = management.call_command('check_paypal_pending')
    assert output == "No booking or blocks to update"


def test_check_paypal_pending_with_unpaid_items_paypal_pending():
    baker.make(Booking, paid=False, paypal_pending=True)
    baker.make(Block, paid=False, paypal_pending=True)

    output = management.call_command('check_paypal_pending')
    assert output == "No booking or blocks to update"


def test_check_paypal_pending_with_unpaid_booking_txn_complete():
    booking = baker.make(Booking, paid=False, paypal_pending=True)
    baker.make(PaypalBookingTransaction, booking=booking, transaction_id="txn1")
    baker.make(PayPalIPN, txn_id="txn1", payment_status=ST_PP_COMPLETED)
    
    failed_block = baker.make(Block, paid=False, paypal_pending=True)
    baker.make(PaypalBlockTransaction, block=failed_block, transaction_id="txn3")
    baker.make(PayPalIPN, txn_id="txn3", payment_status=ST_PP_FAILED)
    
    output = management.call_command('check_paypal_pending')
    assert output == f"booking_ids: {booking.id}, block_ids: "

    assert len(mail.outbox) == 1
    email = mail.outbox[0]
    assert "Unpaid bookings" in email.body
    assert f"- id {booking.id}, transaction txn1" in email.body
    assert "Unpaid blocks" not in email.body

    for item in [booking, failed_block]:
        item.refresh_from_db()
    assert booking.paid
    assert booking.payment_confirmed
    assert booking.date_payment_confirmed is not None
    assert not failed_block.paid


def test_check_paypal_pending_with_unpaid_booking_items_complete():
    booking = baker.make(Booking, paid=False, paypal_pending=True)
    booking1 = baker.make(Booking, paid=False, paypal_pending=True)
    baker.make(PaypalBookingTransaction, booking=booking, transaction_id="txn1")
    baker.make(PayPalIPN, txn_id="txn1", payment_status=ST_PP_COMPLETED)
    baker.make(PaypalBookingTransaction, booking=booking1, transaction_id="txn2")
    baker.make(PayPalIPN, txn_id="txn2", payment_status=ST_PP_COMPLETED)
    
    failed_block = baker.make(Block, paid=False, paypal_pending=True)
    baker.make(PaypalBlockTransaction, block=failed_block, transaction_id="txn3")
    baker.make(PayPalIPN, txn_id="txn3", payment_status=ST_PP_FAILED)
    block = baker.make(Block, paid=False, paypal_pending=True)
    baker.make(PaypalBlockTransaction, block=block, transaction_id="txn4")
    baker.make(PayPalIPN, txn_id="txn4", payment_status=ST_PP_COMPLETED)
    
    output = management.call_command('check_paypal_pending')
    assert output == f"booking_ids: {booking.id},{booking1.id}, block_ids: {block.id}"

    assert len(mail.outbox) == 1
    email = mail.outbox[0]
    assert "Unpaid bookings" in email.body
    assert f"- id {booking.id}, transaction txn1" in email.body
    assert f"- id {booking1.id}, transaction txn2" in email.body
    assert "Unpaid blocks" in email.body
    assert f"- id {block.id}, transaction txn4" in email.body
    assert f"- id {failed_block.id}, transaction txn3" not in email.body

    for item in [booking, booking1, failed_block, block]:
        item.refresh_from_db()
    
    for bk in [booking, booking1]:
        assert bk.paid
        assert bk.payment_confirmed
        assert bk.date_payment_confirmed is not None
    assert not failed_block.paid
    assert block.paid
