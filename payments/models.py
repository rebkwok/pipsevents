import random
from django.db import models
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from paypal.standard.models import ST_PP_COMPLETED, ST_PP_REFUNDED
from paypal.standard.ipn.signals import valid_ipn_received, invalid_ipn_received

from booking.models import Booking, Block


class PayPalTransactionError(Exception):
    pass


class PaypalBookingTransaction(models.Model):
    invoice_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    booking = models.ForeignKey(Booking, null=True)
    transaction_id = models.CharField(max_length=255, null=True, blank=True, unique=True)

    def __str__(self):
        return self.invoice_id


class PaypalBlockTransaction(models.Model):
    invoice_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    block = models.ForeignKey(Block, null=True)
    transaction_id = models.CharField(max_length=255, null=True, blank=True, unique=True)

    def __str__(self):
        return self.invoice_id


def create_booking_paypal_transaction(user, booking):
    id_string = "-".join([user.username] +
                         ["".join([word[0] for word in
                                   booking.event.name.split()])] +
                         [booking.event.date.strftime("%d%m%y%H%M")] + ['inv#'])
    existing = PaypalBookingTransaction.objects.filter(
        invoice_id__contains=id_string, booking=booking).order_by('-invoice_id')

    if existing:
        # PaypalBookingTransaction is created when the view is called, not when
        # payment is made.  If there is no transaction id stored against it,
        # we shouldn't need to make a new one
        for transaction in existing:
            if not transaction.transaction_id:
                return transaction
        existing_counter = existing[0].invoice_id[-5:]
        counter = str(int(existing_counter) + 1).zfill(len(existing_counter))
    else:
        counter = '001'
    return PaypalBookingTransaction.objects.create(
        invoice_id=id_string+counter, booking=booking
    )


def create_block_paypal_transaction(user, block):

    id_string = "-".join([user.username] +
                         ["".join([word[0] for word in
                          block.block_type.event_type.subtype.split()])] +
                         [str(block.block_type.size)] +
                         [block.start_date.strftime("%d%m%y%H%M")] + ['inv#'])

    existing = PaypalBlockTransaction.objects.filter(
        invoice_id__contains=id_string, block=block).order_by('-invoice_id')

    if existing:
        # PaypalBlockTransaction is created when the view is called, not when
        # payment is made.  If there is no transaction id stored against it,
        # we shouldn't need to make a new one
        for transaction in existing:
            if not transaction.transaction_id:
                return transaction
        existing_counter = existing[0].invoice_id[-2:]
        counter = str(int(existing_counter) + 1).zfill(len(existing_counter))
    else:
        counter = '01'
    return PaypalBlockTransaction.objects.create(
        invoice_id=id_string+counter, block=block
    )


def build_checks_dict(ipn_obj, obj_type, existing_trans, cost):
    checks = {}
    if existing_trans:
                checks['trans_id'] = 'Transaction id already exists on a processed ' \
                                     'PaypalTransaction.  This invoice has probably' \
                                     'already been paid; please check for duplicate ' \
                                     'payments.'
    if ipn_obj.receiver_email != settings.PAYPAL_RECEIVER_EMAIL:
        checks['receiver_email'] = 'Receiver email on transaction does not match ' \
                             'expected email {}.  This payment is ' \
                             'suspicious; please check and confirm it ' \
                             'manually.'.format(settings.DEFAULT_RECEIVER_EMAIL)
    if ipn_obj.mc_gross != cost:
        checks['cost'] = 'Amount on transaction does not match event cost' \
                         'for the {}; please check.'.format(obj_type)
    return checks


def send_processed_payment_emails(obj_type, obj_id, paypal_trans, user, purchase):

    # send email to studio
    send_mail(
                '{} Payment processed for {} id {}'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, obj_type, obj_id),
                'User: {} {}\n'
                'Purchased: {}\n'
                'Invoice number: {}\n'
                'Paypal Transaction id: {}\n'.format(
                    user.first_name, user.last_name,
                    purchase,
                    paypal_trans.invoice_id,
                    paypal_trans.transaction_id
                ),
                settings.DEFAULT_FROM_EMAIL, [settings.DEFAULT_STUDIO_EMAIL],
                fail_silently=False)
    # TODO send email to user


def payment_received(sender, **kwargs):
    ipn_obj = sender
    if ipn_obj.payment_status == ST_PP_REFUNDED:
        pass

    if ipn_obj.payment_status == ST_PP_COMPLETED:
        # check if transaction_id already exists on a processed PT so we don't process twice
        # check receiver email matches settings
        # confirm item price is correct
        custom = ipn_obj.custom.split()
        obj_type = custom[0]
        obj_id = int(custom[-1])
        if obj_type == 'booking':
            booking = Booking.objects.get(id=obj_id)
            existing_trans = PaypalBookingTransaction.objects.filter(transaction_id=ipn_obj.txn_id)
            cost = booking.event.cost
        elif obj_type == 'block':
            block = Block.objects.get(id=obj_id)
            existing_trans = PaypalBlockTransaction.objects.filter(transaction_id=ipn_obj.txn_id)
            cost = block.block_type.cost
        else:
            raise PayPalTransactionError('unknown object type for payment')
        try:
            checks = build_checks_dict(ipn_obj, obj_type, existing_trans, cost)
            if checks:
                # TODO email studio
                send_mail(
                    '{} Problem with payment transaction for {} id {}'.format(
                        settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, obj_type, obj_id),
                    '{}\n{}\n{}'.format(checks['trans_id'], checks['receiver_email'], checks['cost']),
                    settings.DEFAULT_FROM_EMAIL, [settings.DEFAULT_STUDIO_EMAIL],
                    fail_silently=False)
            else:
                if obj_type == 'booking':
                    paypal_trans = PaypalBookingTransaction.objects.get(
                        booking=booking, invoice_id=ipn_obj.invoice
                    )
                else:
                    paypal_trans = PaypalBlockTransaction.objects.get(
                        block=block, invoice_id=ipn_obj.invoice
                    )

                paypal_trans.transaction_id = ipn_obj.txn_id
                paypal_trans.save()

                if obj_type == 'booking':
                    booking.paid = True
                    booking.payment_confirmed = True
                    booking.date_payment_confirmed = timezone.now()
                    booking.save()

                    send_processed_payment_emails(obj_type, obj_id, paypal_trans,
                                                  booking.user, booking.event)
                else:
                    block.paid = True
                    block.save()

                    send_processed_payment_emails(obj_type, obj_id, paypal_trans,
                                                  block.user, block.block_type)

        except:
            # if anything goes wrong, send a warning email
            send_mail(
                    '{} WARNING! There was some problem processing payment for '
                    '{} id {}'.format(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, obj_type, obj_id),
                    'Please check your booking and paypal records for invoice # {}, '
                    'paypal transaction id {}'.format(ipn_obj.invoice, ipn_obj.txn_id),
                    settings.DEFAULT_FROM_EMAIL, [settings.DEFAULT_STUDIO_EMAIL],
                    fail_silently=False)


def payment_not_received(sender, **kwargs):
    ipn_obj = sender

    booking = Booking.objects.filter(id=int(ipn_obj.custom))
    send_mail(
            'WARNING! Invalid Payment Notification received from PayPal',
            'PayPal sent an invalid transaction notification while '
            'attempting to process payment for booking id {}'.format(booking.id),
            settings.DEFAULT_FROM_EMAIL, [settings.DEFAULT_STUDIO_EMAIL],
            fail_silently=False)
valid_ipn_received.connect(payment_received)
invalid_ipn_received.connect(payment_not_received)
