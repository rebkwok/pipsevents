# -*- coding: utf-8 -*-

import logging

from django.db import models

from booking.models import Booking, Block, TicketBooking, GiftVoucherType


logger = logging.getLogger(__name__)


class PaypalBookingTransaction(models.Model):
    invoice_id = models.CharField(max_length=255, null=True, blank=True)
    booking = models.ForeignKey(Booking, null=True, on_delete=models.SET_NULL)
    transaction_id = models.CharField(max_length=255, null=True, blank=True)
    voucher_code = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return '{} - booking {}'.format(
            self.invoice_id, self.booking.id if self.booking else None
        )


class PaypalBlockTransaction(models.Model):
    invoice_id = models.CharField(max_length=255, null=True, blank=True)
    block = models.ForeignKey(Block, null=True, on_delete=models.SET_NULL)
    transaction_id = models.CharField(max_length=255, null=True, blank=True)
    voucher_code = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return '{} - block {}'.format(
            self.invoice_id, self.block.id if self.block else None
        )


class PaypalTicketBookingTransaction(models.Model):
    invoice_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    ticket_booking = models.ForeignKey(TicketBooking, null=True, on_delete=models.SET_NULL)
    transaction_id = models.CharField(max_length=255, null=True, blank=True, unique=True)

    def __str__(self):
        return '{} - tkt booking {}'.format(
            self.invoice_id, self.ticket_booking.id if self.ticket_booking else None
        )


class PaypalGiftVoucherTransaction(models.Model):
    invoice_id = models.CharField(max_length=255, null=True, blank=True)
    voucher_type = models.ForeignKey(GiftVoucherType, null=True, on_delete=models.SET_NULL)
    voucher_code = models.CharField(max_length=255, null=True, blank=True)
    transaction_id = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return '{} - {}'.format(
            self.invoice_id, self.voucher_type, self.voucher_code
        )
