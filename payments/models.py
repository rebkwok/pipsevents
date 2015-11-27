import logging

from django.db import models
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.template.loader import get_template
from django.template import Context

from paypal.standard.models import ST_PP_COMPLETED, ST_PP_REFUNDED
from paypal.standard.ipn.signals import valid_ipn_received, invalid_ipn_received

from booking.models import Booking, Block, TicketBooking

from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


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


class PaypalTicketBookingTransaction(models.Model):
    invoice_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    ticket_booking = models.ForeignKey(TicketBooking, null=True)
    transaction_id = models.CharField(max_length=255, null=True, blank=True, unique=True)

    def __str__(self):
        return self.invoice_id


def send_processed_payment_emails(obj_type, obj_id, paypal_trans, user, obj):

    ctx = Context({
        'user': " ".join([user.first_name, user.last_name]),
        'obj_type': obj_type.title().replace('_', ' '),
        'obj': obj,
        'invoice_id': paypal_trans.invoice_id,
        'paypal_transaction_id': paypal_trans.transaction_id
    })
    # send email to studio
    send_mail(
        '{} Payment processed for {} id {}'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, obj_type, obj_id),
        get_template(
            'payments/email/payment_processed_to_studio.txt').render(ctx),
        settings.DEFAULT_FROM_EMAIL,
        [settings.DEFAULT_STUDIO_EMAIL],
        html_message=get_template(
            'payments/email/payment_processed_to_studio.html').render(ctx),
        fail_silently=False)

    # send email to user
    send_mail(
        '{} Payment processed for {} id {}'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, obj_type, obj_id),
        get_template(
            'payments/email/payment_processed_to_user.txt').render(ctx),
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        html_message=get_template(
            'payments/email/payment_processed_to_user.html').render(ctx),
        fail_silently=False)

    ActivityLog.objects.create(log='Payment-processed email for {} {} sent to '
        'studio and user {} ({})'.format(
            obj_type, obj_id, user.username, user.email
        )
    )


def send_processed_refund_emails(obj_type, obj_id, paypal_trans, user, obj):

    ctx = Context({
        'user': " ".join([user.first_name, user.last_name]),
        'obj_type': obj_type.title().replace('_', ' '),
        'obj': obj,
        'invoice_id': paypal_trans.invoice_id,
        'paypal_transaction_id': paypal_trans.transaction_id
    })
    # send email to studio only and to support for checking;
    # user will have received automated paypal payment
    send_mail(
        '{} Payment refund processed for {} id {}'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, obj_type, obj_id),
        get_template(
            'payments/email/payment_refund_processed_to_studio.txt'
        ).render(ctx),
        settings.DEFAULT_FROM_EMAIL,
        [settings.DEFAULT_STUDIO_EMAIL, settings.SUPPORT_EMAIL],
        html_message=get_template(
            'payments/email/payment_refund_processed_to_studio.html'
        ).render(ctx),
        fail_silently=False)


def get_obj(ipn_obj):
    from payments import helpers

    try:
        custom = ipn_obj.custom.split()
        obj_type = custom[0]
        obj_id = int(custom[-1])
    except IndexError:  # in case custom not included in paypal response
        raise PayPalTransactionError('Unknown object type for payment')

    if obj_type == 'booking':
        try:
            obj = Booking.objects.get(id=obj_id)
        except Booking.DoesNotExist:
            raise PayPalTransactionError(
                'Booking with id {} does not exist'.format(obj_id)
            )
        try:
            paypal_trans = PaypalBookingTransaction.objects.get(booking=obj)
        except PaypalBookingTransaction.DoesNotExist:
            paypal_trans = helpers.create_booking_paypal_transaction(
                user=obj.user, booking=obj
            )

    elif obj_type == 'block':
        try:
            obj = Block.objects.get(id=obj_id)
        except Block.DoesNotExist:
            raise PayPalTransactionError(
                'Block with id {} does not exist'.format(obj_id)
            )
        try:
            paypal_trans = PaypalBlockTransaction.objects.get(block=obj)
        except PaypalBlockTransaction.DoesNotExist:
            paypal_trans = helpers.create_block_paypal_transaction(
                user=obj.user, block=obj
            )
    elif obj_type == 'ticket_booking':
        try:
            obj = TicketBooking.objects.get(id=obj_id)
        except TicketBooking.DoesNotExist:
            raise PayPalTransactionError(
                'Ticket Booking with id {} does not exist'.format(obj_id)
            )
        try:
            paypal_trans = PaypalTicketBookingTransaction.objects.get(
                ticket_booking=obj
            )
        except PaypalTicketBookingTransaction.DoesNotExist:
            paypal_trans = helpers.create_ticket_booking_paypal_transaction(
                user=obj.user, ticket_booking=obj
            )
    else:
        raise PayPalTransactionError('Unknown object type for payment')

    return {
        'obj_type': obj_type,
        'obj': obj,
        'paypal_trans': paypal_trans
    }


def payment_received(sender, **kwargs):
    ipn_obj = sender
    try:
        obj_dict = get_obj(ipn_obj)
    except PayPalTransactionError as e:
        send_mail(
        'WARNING! Error processing PayPal IPN',
        'Valid Payment Notification received from PayPal but an error '
        'occurred during processing.\n\nTransaction id {}\n\nThe flag info '
        'was "{}"\n\nError raised: {}'.format(
            ipn_obj.txn_id, ipn_obj.flag_info, e
        ),
        settings.DEFAULT_FROM_EMAIL, [settings.SUPPORT_EMAIL],
        fail_silently=False)
        logger.error(
            'PaypalTransactionError: unknown object type for payment '
            '(ipn_obj transaction_id: {}, error: {})'.format(
                ipn_obj.txn_id, e
            )
        )
        return

    obj = obj_dict['obj']
    obj_type = obj_dict['obj_type']
    paypal_trans = obj_dict['paypal_trans']

    try:
        if ipn_obj.payment_status == ST_PP_REFUNDED:
            if obj_type == 'booking':
                obj.payment_confirmed = False
            obj.paid = False
            obj.save()

            ActivityLog.objects.create(
                log='{} id {} for user {} has been refunded from paypal; '
                    'paypal transaction id {}, invoice id {}'.format(
                    obj_type.title(), obj.id, obj.user.username,
                    ipn_obj.txn_id, paypal_trans.invoice_id
                    )
            )

            send_processed_refund_emails(obj_type, obj.id, paypal_trans,
                                          obj.user, obj)

        if ipn_obj.payment_status == ST_PP_COMPLETED:
            # we only process if payment status is completed
            # check for django-paypal flags (checks for valid payment status,
            # duplicate trans id, correct receiver email, valid secret (if using
            # encrypted), mc_gross, mc_currency, item_name and item_number are all
            # correct
            paypal_trans.transaction_id = ipn_obj.txn_id
            paypal_trans.save()

            if obj_type == 'booking':
                obj.payment_confirmed = True
                obj.date_payment_confirmed = timezone.now()
            obj.paid = True
            obj.save()

            ActivityLog.objects.create(
                log='{} id {} for user {} has been paid by PayPal; paypal '
                    '{} id {}'.format(
                    obj_type.title(), obj.id, obj.user.username, obj_type,
                    paypal_trans.id
                    )
            )

            send_processed_payment_emails(obj_type, obj.id, paypal_trans,
                                          obj.user, obj)

            if not ipn_obj.invoice:
                # sometimes paypal doesn't send back the invoice id -
                # everything should be ok but email to check
                ipn_obj.invoice = paypal_trans.invoice_id
                ipn_obj.save()
                send_mail(
                    '{} No invoice number on paypal ipn for '
                    '{} id {}'.format(
                        settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, obj_type,
                        obj.id
                    ),
                    'Please check booking and paypal records for '
                    'paypal transaction id {}.  No invoice number on paypal'
                    ' IPN.  Invoice number has been set to {}.'.format(
                        ipn_obj.txn_id, paypal_trans.invoice_id
                    ),
                    settings.DEFAULT_FROM_EMAIL,
                    [settings.SUPPORT_EMAIL],
                    fail_silently=False
                )

    except Exception as e:
        # if anything else goes wrong, send a warning email
        logger.warning(
            'Problem processing payment for {} {}; invoice_id {}, transaction '
            'id: {}.  Exception: {}'.format(
                obj_type.title(), obj.id, ipn_obj.invoice, ipn_obj.txn_id, e
                )
        )
        send_mail(
            '{} There was some problem processing payment for '
            '{} id {}'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, obj_type, obj.id
            ),
            'Please check your booking and paypal records for '
            'invoice # {}, paypal transaction id {}.\n\nThe exception '
            'raised was "{}"'.format(
                ipn_obj.invoice, ipn_obj.txn_id, e
            ),
            settings.DEFAULT_FROM_EMAIL,
            [settings.SUPPORT_EMAIL],
            fail_silently=False)


def payment_not_received(sender, **kwargs):
    ipn_obj = sender
    try:
        obj_dict = get_obj(ipn_obj)
    except PayPalTransactionError as e:
        send_mail(
            'WARNING! Error processing Invalid Payment Notification from PayPal',
            'PayPal sent an invalid transaction notification while '
            'attempting to process payment;.\n\nThe flag '
            'info was "{}"\n\nAn additional error was raised: {}'.format(
                ipn_obj.flag_info, e
            ),
            settings.DEFAULT_FROM_EMAIL, [settings.SUPPORT_EMAIL],
            fail_silently=False)
        logger.error(
            'PaypalTransactionError: unknown object type for payment ('
            'transaction_id: {}, error: {})'.format(ipn_obj.txn_id, e)
        )
        return

    try:
        obj = obj_dict['obj']
        obj_type = obj_dict['obj_type']

        if obj:
            logger.warning('Invalid Payment Notification received from PayPal '
                           'for {} id {}'.format(
                obj_type.title(), obj.id)
            )
            send_mail(
                'WARNING! Invalid Payment Notification received from PayPal',
                'PayPal sent an invalid transaction notification while '
                'attempting to process payment for {} id {}.\n\nThe flag '
                'info was "{}"'.format(
                    obj_type.title(), obj.id, ipn_obj.flag_info),
                settings.DEFAULT_FROM_EMAIL, [settings.SUPPORT_EMAIL],
                fail_silently=False)

    except Exception as e:
            # if anything else goes wrong, send a warning email
            logger.warning(
                'Problem processing payment_not_received for {} {}; invoice_'
                'id {}, transaction id: {}. Exception: {}'.format(
                    obj_type.title(), obj.id, ipn_obj.invoice,
                    ipn_obj.txn_id, e
                    )
            )
            send_mail(
                '{} There was some problem processing payment_not_received for '
                '{} id {}'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, obj_type, obj.id
                ),
                'Please check your booking and paypal records for '
                'invoice # {}, paypal transaction id {}.\n\nThe exception '
                'raised was "{}".\n\nNOTE: this error occurred during '
                'processing of the payment_not_received signal'.format(
                    ipn_obj.invoice, ipn_obj.txn_id, e
                ),
                settings.DEFAULT_FROM_EMAIL,
                [settings.SUPPORT_EMAIL],
                fail_silently=False)

valid_ipn_received.connect(payment_received)
invalid_ipn_received.connect(payment_not_received)
