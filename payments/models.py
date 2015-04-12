import random
from django.db import models
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.template.loader import get_template
from django.template import Context

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
        # we only process if payment status is completed
        # check for django-paypal flags (checks for valid payment status,
        # duplicate trans id, correct receiver email, valid secret (if using
        # encrypted), mc_gross, mc_currency, item_name and item_number are all
        # correct
        custom = ipn_obj.custom.split()
        obj_type = custom[0]
        obj_id = int(custom[-1])
        if obj_type == 'booking':
            obj = Booking.objects.get(id=obj_id)
            purchase = obj.event
        elif obj_type == 'block':
            obj = Block.objects.get(id=obj_id)
            purchase = obj.block_type
        else:
            raise PayPalTransactionError('unknown object type for payment')
        try:
            if ipn_obj.flag:
                # to studio and user
                send_mail(
                    '{} Problem with payment from {} for {}'.format(
                        settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                        obj.user.username,
                        obj_type
                    ),
                    get_template(
                        'payments/flagged_transaction_email.txt').render(
                        Context({
                            'ipn_obj': ipn_obj,
                            'user': obj.user,
                            'obj_type': obj_type,
                        })
                    ),
                    settings.DEFAULT_FROM_EMAIL,
                    [settings.DEFAULT_STUDIO_EMAIL, obj.user.email],
                    fail_silently=False)

            else:
                if obj_type == 'booking':
                    paypal_trans = PaypalBookingTransaction.objects.get(
                        booking=obj, invoice_id=ipn_obj.invoice
                    )
                else:
                    paypal_trans = PaypalBlockTransaction.objects.get(
                        block=obj, invoice_id=ipn_obj.invoice
                    )

                paypal_trans.transaction_id = ipn_obj.txn_id
                paypal_trans.save()

                if obj_type == 'booking':
                    obj.payment_confirmed = True
                    obj.date_payment_confirmed = timezone.now()
                obj.paid = True
                obj.save()
                send_processed_payment_emails(obj_type, obj_id, paypal_trans,
                                              obj.user, purchase)

        except:
            # if anything goes wrong, send a warning email
            send_mail(
                '{} WARNING! There was some problem processing payment for '
                '{} id {}'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, obj_type, obj_id
                ),
                'Please check your booking and paypal records for '
                'invoice # {}, paypal transaction id {}'.format(
                    ipn_obj.invoice, ipn_obj.txn_id
                ),
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
