# -*- coding: utf-8 -*-

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.template.loader import get_template

from paypal.standard.models import ST_PP_COMPLETED, ST_PP_REFUNDED, \
    ST_PP_PENDING
from paypal.standard.ipn.models import PayPalIPN
from paypal.standard.ipn.signals import valid_ipn_received, invalid_ipn_received

from booking.models import Booking, Block, TicketBooking, BlockVoucher, \
    EventVoucher, UsedBlockVoucher, UsedEventVoucher, GiftVoucherType

from payments.models import PaypalBlockTransaction, PaypalBookingTransaction, \
    PaypalTicketBookingTransaction, PaypalGiftVoucherTransaction
from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


class PayPalTransactionError(Exception):
    pass


def get_paypal_email(obj, obj_type):
    if obj_type == 'booking':
        return obj.event.paypal_email
    elif obj_type == 'ticket_booking':
        return obj.ticketed_event.paypal_email
    elif obj_type == 'block':
        return obj.block_type.paypal_email
    else:  # gift vouchers always use the default
        return settings.DEFAULT_PAYPAL_EMAIL


def get_user_and_email(obj_type, obj_list):
    if obj_type != "gift_voucher":
        user = obj_list[0].user
        user_email = user.email
        user_name = " ".join([user.first_name, user.last_name])
    else:
        user_name = None
        user_email = obj_list[0].purchaser_email
    return user_name, user_email


def send_processed_payment_emails(obj_type, obj_ids, obj_list, paypal_trans_list):
    user_name, user_email = get_user_and_email(obj_type, obj_list)
    paypal_email = get_paypal_email(obj_list[0], obj_type)
    transaction_id = paypal_trans_list[0].transaction_id
    invoice_id = paypal_trans_list[0].invoice_id

    ctx = {
        'user': user_name,
        'user_email': user_email,
        'obj_type': obj_type.title().replace('_', ' '),
        'objs': obj_list,
        'invoice_id': invoice_id,
        'paypal_transaction_id': transaction_id,
        'paypal_email': paypal_email
    }

    # send email to studio
    if settings.SEND_ALL_STUDIO_EMAILS:
        send_mail(
            '{} Payment processed for {} id {}'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, obj_type, obj_ids),
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
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, obj_type, obj_ids),
        get_template(
            'payments/email/payment_processed_to_user.txt').render(ctx),
        settings.DEFAULT_FROM_EMAIL,
        [user_email],
        html_message=get_template(
            'payments/email/payment_processed_to_user.html').render(ctx),
        fail_silently=False)


def send_processed_refund_emails(obj_type, obj_ids, obj_list, paypal_trans_list):
    user_name, user_email = get_user_and_email(obj_type, obj_list)
    paypal_email = get_paypal_email(obj_list[0], obj_type)
    transaction_id = paypal_trans_list[0].transaction_id
    invoice_id = paypal_trans_list[0].invoice_id

    ctx = {
        'user': user_name,
        'user_email': user_email,
        'obj_type': obj_type.title().replace('_', ' '),
        'objs': obj_list,
        'invoice_id': invoice_id,
        'paypal_transaction_id': transaction_id,
        'paypal_email': paypal_email
    }
    # send email to studio only and to support for checking;
    # user will have received automated paypal payment
    send_mail(
        '{} Payment refund processed for {} id {}'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, obj_type, obj_ids),
        get_template(
            'payments/email/payment_refund_processed_to_studio.txt'
        ).render(ctx),
        settings.DEFAULT_FROM_EMAIL,
        [settings.DEFAULT_STUDIO_EMAIL, settings.SUPPORT_EMAIL],
        html_message=get_template(
            'payments/email/payment_refund_processed_to_studio.html'
        ).render(ctx),
        fail_silently=False)


def send_processed_test_confirmation_emails(additional_data):
    invoice_id = additional_data['test_invoice']
    paypal_email = additional_data['test_paypal_email']
    user_email = additional_data['user_email']
    # send email to user email only and to support for checking;
    send_mail(
        '{} Payment processed for test payment to PayPal email {}'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, paypal_email
        ),
        'Test payment to PayPal email {paypal_email}, invoice # {invoice_id} '
        'completed and processed successfully by booking system.\n\n'
        '==========\n\n'
        'IMPORTANT:\n\n'
        '==========\n\n'
        'Please note that this is only confirmation that {paypal_email} '
        'is a valid PayPal email and the booking system was able to process '
        'payments to it. To complete the test process, please contact the '
        'recipient and verify that the test payment of £0.01 with invoice # '
        '{invoice_id} was received.\n\n'
        'Test payments are not automatically refunded; you '
        'will need to contact the recipient if you wish to arrange a '
        'refund.'.format(paypal_email=paypal_email, invoice_id=invoice_id),
        settings.DEFAULT_FROM_EMAIL, [user_email, settings.SUPPORT_EMAIL],
        fail_silently=False)


def send_processed_test_pending_emails(additional_data):
    invoice_id = additional_data['test_invoice']
    paypal_email = additional_data['test_paypal_email']
    user_email = additional_data['user_email']
    # send email to user email only and to support for checking;
    send_mail(
        '{} Payment status PENDING for test payment to PayPal email {}'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, paypal_email
        ),
        'Test payment to PayPal email {paypal_email}, invoice # {invoice_id} '
        'was returned with status PENDING.\n\n'
        'This usually happens when a payment attempt is made to a '
        'non-existent or unverified paypal email address.  Please check the '
        'email address was typed correctly and confirm with the recipient '
        'that their email is verified with PayPal.'.format(
            paypal_email=paypal_email, invoice_id=invoice_id
        ),
        settings.DEFAULT_FROM_EMAIL, [user_email, settings.SUPPORT_EMAIL],
        fail_silently=False)


def send_processed_test_refund_emails(additional_data):
    invoice_id = additional_data['test_invoice']
    paypal_email = additional_data['test_paypal_email']
    user_email = additional_data['user_email']
    # send email to user email only and to support for checking;
    # user will have received automated paypal payment
    send_mail(
        '{} Payment refund processed for test payment to PayPal email {}'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, paypal_email
        ),
        'Refund for test payment to email {}, invoice # {} received and '
        'processed by booking system'.format(paypal_email, invoice_id),
        settings.DEFAULT_FROM_EMAIL, [user_email, settings.SUPPORT_EMAIL],
        fail_silently=False)


def send_processed_test_unexpected_status_emails(additional_data, status):
    invoice_id = additional_data['test_invoice']
    paypal_email = additional_data['test_paypal_email']
    user_email = additional_data['user_email']
    # send email to user email only and to support for checking;
    send_mail(
        '{} Unexpected payment status {} for test payment to PayPal '
        'email {}'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, status.upper(), paypal_email
        ),
        'Test payment to PayPal email {paypal_email}, invoice # {invoice_id} '
        'was returned with unexpected status {payment_status}.\n\n'.format(
            paypal_email=paypal_email, invoice_id=invoice_id,
            payment_status=status.upper()
        ),
        settings.DEFAULT_FROM_EMAIL, [user_email, settings.SUPPORT_EMAIL],
        fail_silently=False)


def send_payment_for_cancelled_booking_email(obj, paypal_trans, ipn_obj, reopened):
    send_mail(
        f'WARNING! Payment processed for cancelled booking',
        f'Payment processed for cancelled booking:\n '
        f'- Booking: {obj} (id {obj.id})\n'
        f'- User: {obj.user}\n'
        f'- IPN: {ipn_obj.txn_id}\n'
        f'- Invoice ID: {paypal_trans.invoice_id}\n'
        f'Booking {"was REOPENED." if reopened else "is still CANCELLED (class is full or cancelled)."}',
        settings.DEFAULT_FROM_EMAIL, [settings.SUPPORT_EMAIL],
        fail_silently=False)


def send_gift_voucher_email(voucher):
    ctx = {"voucher": voucher}
    send_mail(
        f'{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Gift Voucher',
        get_template('payments/email/gift_voucher.txt').render(ctx),
        settings.DEFAULT_FROM_EMAIL,
        [voucher.purchaser_email],
        html_message=get_template('payments/email/gift_voucher.html').render(ctx),
        fail_silently=False
    )


def get_obj(ipn_obj):
    if not ipn_obj.custom:
        raise PayPalTransactionError('Unknown object type for payment')
    if not ipn_obj.custom.startswith("obj="):
        return get_obj_legacy(ipn_obj)

    # custom is in format "k=v k=v"
    # possible keys:
    # obj (obj type) - always present; booking/block/ticket_booking/gift_voucher/paypal_test
    # ids (obj ids) - always present
    # usr (user email)
    # cde (voucher code - code used or gift voucher code if obj is gift_voucher)
    # apd (ids voucher applied to)
    # pp (paypal email for a paypal_test)
    # inv (invoice id, for a paypal_test)
    # occasionally paypal sends back the custom field with the space
    # replaced with '+'. i.e. "obj=booking+obj_ids=1" instead of "obj=booking obj_ids=1"
    custom = ipn_obj.custom.replace('+', ' ').split()
    try:
        custom_dict = {
            key: value for (key, value) in [custom_item.split("=") for custom_item in custom]
        }
    except ValueError:
        raise PayPalTransactionError(f"Invalid custom format: {ipn_obj.custom}")

    obj_type = custom_dict["obj"]
    obj_ids = [int(id) for id in custom_dict["ids"].split(',')]

    voucher_code = custom_dict.get("cde")
    voucher_applied_to = custom_dict.get("apd")
    if voucher_applied_to:
        voucher_applied_to = [int(applied_id) for applied_id in voucher_applied_to.split(',')]

    user_email = custom_dict.get("usr")

    if obj_type == 'paypal_test':
        # a test payment for paypal email
        additional_data = {
            "test_invoice": custom_dict["inv"],
            "test_paypal_email": custom_dict["pp"],
            "user_email": user_email
        }
        return {
            'obj_type': obj_type,
            'obj_list': [],
            'paypal_trans_list': [],
            'voucher_code': voucher_code,
            'voucher_applied_to': voucher_applied_to,
            'obj_user': user_email,
            'additional_data': additional_data
        }
    else:
        return build_obj_dict(ipn_obj, obj_type, obj_ids, voucher_code, voucher_applied_to)


def get_obj_legacy(ipn_obj):
    """
    Deal with legacy custom fields.  This should only happen for refunds of payments
    processed prior to the custom field refactor
    """
    additional_data = {}

    # custom format: 'obj_type obj_ids user_email voucher_code'
    # occasionally paypal sends back the custom field with the space
    # replaced with '+'. i.e. "booking+1" instead of "booking 1"
    custom = ipn_obj.custom.replace('+', ' ').split()
    obj_type = custom[0]
    ids = custom[1]
    obj_ids = [int(id) for id in ids.split(',')]
    voucher_code = None
    voucher_applied_to = None

    if obj_type == "gift_voucher":
        voucher_code = custom[3]
    elif obj_type != 'paypal_test':
        # Note voucher_applied_to was implemented at the same time as the custom format
        # refactor, so we will never get voucher_applied_to fields with legacy custom format
        voucher_code = custom[3] if len(custom) == 4 else None

    if obj_type == 'paypal_test':
        # a test payment for paypal email
        # custom in a test payment is in form
        # 'test 0 <invoice_id> <paypal email being tested> <user's email>'
        additional_data['test_invoice'] = custom[2]
        additional_data['test_paypal_email'] = custom[3]
        additional_data['user_email'] = custom[4]

        return {
            'obj_type': obj_type,
            'obj_list': [],
            'paypal_trans_list': [],
            'voucher_code': voucher_code,
            'voucher_applied_to': voucher_applied_to,
            'obj_user': custom[4],
            'additional_data': additional_data
        }
    else:
        return build_obj_dict(ipn_obj, obj_type, obj_ids, voucher_code, voucher_applied_to)


def build_obj_dict(ipn_obj, obj_type, obj_ids, voucher_code, voucher_applied_to):
    from payments import helpers
    obj_list = []
    paypal_trans_list = []
    invalid_ids = []
    obj_user = None

    if obj_type == 'booking':
        for id in obj_ids:
            try:
                obj = Booking.objects.get(id=id)
            except Booking.DoesNotExist:
                invalid_ids.append(id)
                continue

            paypal_trans = PaypalBookingTransaction.objects.filter(booking=obj)
            if not paypal_trans:
                paypal_trans = helpers.create_booking_paypal_transaction(
                    user=obj.user, booking=obj
                )
            elif paypal_trans.count() > 1:
                # we may have two ppb transactions created if user changed their
                # username between booking and paying (invoice_id is created and
                # retrieved using username)
                if ipn_obj.invoice:
                    paypal_trans = PaypalBookingTransaction.objects.get(
                        booking=obj, invoice_id=ipn_obj.invoice
                    )
                else:
                    paypal_trans = paypal_trans.latest('id')
            else:  # we got one paypaltrans, as we should have
                paypal_trans = paypal_trans[0]

            obj_list.append(obj)
            paypal_trans_list.append(paypal_trans)
    elif obj_type == 'block':
        for id in obj_ids:
            try:
                obj = Block.objects.get(id=id)
            except Block.DoesNotExist:
                invalid_ids.append(id)
                continue

            paypal_trans = PaypalBlockTransaction.objects.filter(block=obj)
            if not paypal_trans:
                paypal_trans = helpers.create_block_paypal_transaction(
                    user=obj.user, block=obj
                )
            elif paypal_trans.count() > 1:
                # we may have two ppb transactions created if user changed their
                # username between booking block and paying (invoice_id is created and
                # retrieved using username)
                if ipn_obj.invoice:
                    paypal_trans = PaypalBlockTransaction.objects.get(
                        block=obj, invoice_id=ipn_obj.invoice
                    )
                else:
                    paypal_trans = paypal_trans.latest('id')
            else:  # we got one paypaltrans, as we should have
                paypal_trans = paypal_trans[0]

            obj_list.append(obj)
            paypal_trans_list.append(paypal_trans)
    elif obj_type == 'ticket_booking':
        try:
            obj = TicketBooking.objects.get(id=obj_ids[0])
        except TicketBooking.DoesNotExist:
            raise PayPalTransactionError(
                'Ticket Booking with id {} does not exist'.format(obj_ids[0])
            )

        paypal_trans = PaypalTicketBookingTransaction.objects.filter(
            ticket_booking=obj
        )
        if not paypal_trans:
            paypal_trans = helpers.create_ticket_booking_paypal_transaction(
                user=obj.user, ticket_booking=obj
            )
        elif paypal_trans.count() > 1:
            # we may have two ppb transactions created if user changed their
            # username between booking and paying (invoice_id is created and
            # retrieved using username)
            if ipn_obj.invoice:
                paypal_trans = PaypalTicketBookingTransaction.objects.get(
                    ticket_booking=obj, invoice_id=ipn_obj.invoice
                )
            else:
                paypal_trans = paypal_trans.latest('id')
        else:  # we got one paypaltrans, as we should have
            paypal_trans = paypal_trans[0]

        obj_list.append(obj)
        paypal_trans_list.append(paypal_trans)
    elif obj_type == "gift_voucher":
        try:
            obj = BlockVoucher.objects.get(id=obj_ids[0], code=voucher_code)
            voucher_type = GiftVoucherType.objects.get(block_type=obj.block_types.first())
        except BlockVoucher.DoesNotExist:
            try:
                obj = EventVoucher.objects.get(id=obj_ids[0], code=voucher_code)
                voucher_type = GiftVoucherType.objects.get(event_type=obj.event_types.first())
            except EventVoucher.DoesNotExist:
                raise PayPalTransactionError(
                    'Voucher code with id {} (code {}) does not exist'.format(obj_ids[0], voucher_code)
                )

        paypal_trans = PaypalGiftVoucherTransaction.objects.filter(voucher_code=obj.code, voucher_type=voucher_type)
        if not paypal_trans:
            paypal_trans = helpers.create_gift_voucher_paypal_transaction(
                voucher_code=voucher_code, voucher_type=voucher_type
            )
        else:
            paypal_trans = paypal_trans[0]

        obj_list.append(obj)
        paypal_trans_list.append(paypal_trans)
    else:
        raise PayPalTransactionError('Unknown object type for payment')

    if invalid_ids:
        raise PayPalTransactionError(
            '{}(s) with id(s) {} does not exist'.format(
                obj_type.title(), ', '.join([str(id) for id in invalid_ids])
            )
        )
    if obj_list:
        obj_user = obj_list[0].purchaser_email if obj_type == "gift_voucher" else \
        obj_list[0].user.username

    return {
        'obj_type': obj_type,
        'obj_list': obj_list,
        'paypal_trans_list': paypal_trans_list,
        'voucher_code': voucher_code,
        'voucher_applied_to': voucher_applied_to,
        'obj_user': obj_user,
        'additional_data': {}
    }


def process_completed_payment(obj_list, paypal_trans_list, ipn_obj, obj_type, voucher_code, voucher_applied_to):
    voucher_error = None
    for obj, paypal_trans in zip(obj_list, paypal_trans_list):
        if obj_type == 'booking':
            obj.payment_confirmed = True
            obj.date_payment_confirmed = timezone.now()
            if obj.status == "CANCELLED" or obj.no_show:
                # Paying for a cancelled booking (or a no-show booking, which would be a late cancellation);
                # something's not right here
                # Reopen it if there's still space in the class.  Email a warning so we can check this is correct.
                reopened = False
                if obj.event.spaces_left and not obj.event.cancelled:
                    obj.status = "OPEN"
                    obj.autocancelled = False
                    obj.no_show = False
                    reopened = True
                send_payment_for_cancelled_booking_email(obj, paypal_trans, ipn_obj, reopened)
        if obj_type in ['booking', 'block']:
            obj.paypal_pending = False
        if obj_type == "gift_voucher":
            obj.activated = True
        else:
            obj.paid = True
        obj.save()

        # do this AFTER saving the booking as paid; in the edge case that a
        # user re-requests the page with the paypal button on it in between
        # booking and the paypal transaction being saved, this prevents a
        # second invoice number being generated
        # SCENARIO 1 (how we did it before): paypal trans id saved first;
        # user requests page when booking still marked as unpaid -->
        # renders paypal button and generates new invoice # because
        # retrieved paypal trans already has a txn_id stored against it.
        # Paypal will allow the booking to be paid twice because the
        # invoice number is different
        # SCENARIO: booking saved first; user requests page when paypal
        # trans not updated yet --> booking is marked as paid so doesn't
        # render the paypal button at all
        paypal_trans.transaction_id = ipn_obj.txn_id
        paypal_trans.save()

        if voucher_code and obj_type != 'gift_voucher':
            try:
                if obj.id in voucher_applied_to:
                    if obj_type == 'booking':
                        voucher = EventVoucher.objects.get(code=voucher_code)
                        UsedEventVoucher.objects.create(
                            voucher=voucher, user=obj.user, booking_id=obj.id
                        )
                    elif obj_type == 'block':
                        voucher = BlockVoucher.objects.get(code=voucher_code)
                        UsedBlockVoucher.objects.create(
                            voucher=voucher, user=obj.user, block_id=obj.id
                        )
                    paypal_trans.voucher_code = voucher_code
                    paypal_trans.save()

            except (
                    EventVoucher.DoesNotExist, BlockVoucher.DoesNotExist
            ) as e:
                voucher_error = e

        if not ipn_obj.invoice:
            # sometimes paypal doesn't send back the invoice id -
            # everything should be ok but email to check
            ipn_obj.invoice = paypal_trans.invoice_id
            ipn_obj.save()
            send_mail(
                f'WARNING! No invoice number on paypal ipn for {obj_type} id {obj.id}',
                'Please check booking and paypal records for '
                'paypal transaction id {}.  No invoice number on paypal'
                ' IPN.  Invoice number has been set to {}.'.format(
                    ipn_obj.txn_id, paypal_trans.invoice_id
                ),
                settings.DEFAULT_FROM_EMAIL,
                [settings.SUPPORT_EMAIL],
                fail_silently=False
            )

    return voucher_error


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
            'Error: (ipn_obj transaction_id: {}, error: {})'.format(
                ipn_obj.txn_id, e
            )
        )
        return

    # obj and paypal_trans is a list for bookings
    obj_list = obj_dict['obj_list']
    obj_type = obj_dict['obj_type']
    paypal_trans_list = obj_dict['paypal_trans_list']
    voucher_code = obj_dict.get('voucher_code')
    voucher_applied_to = obj_dict.get('voucher_applied_to')
    additional_data = obj_dict.get('additional_data')
    obj_ids = ', '.join([str(obj.id) for obj in obj_list])
    obj_user = obj_dict["obj_user"]  # username or email address
    try:
        if obj_type != 'paypal_test':
            for obj in obj_list:
                if get_paypal_email(obj, obj_type) != ipn_obj.business:
                    ipn_obj.set_flag(
                        "Invalid business email (%s)" % ipn_obj.business
                    )
                    ipn_obj.save()
                    raise PayPalTransactionError(ipn_obj.flag_info)

        if ipn_obj.payment_status == ST_PP_REFUNDED:
            if obj_type == 'paypal_test':
                ActivityLog.objects.create(
                    log='Test payment (invoice {} for paypal email {} has '
                        'been refunded from paypal; paypal transaction '
                        'id {}'.format(
                            additional_data['test_invoice'],
                            additional_data['test_paypal_email'],
                            ipn_obj.txn_id
                        )
                )
                send_processed_test_refund_emails(additional_data)

            else:
                voucher_refunded = False
                try:
                    original_transaction = PayPalIPN.objects.get(invoice=ipn_obj.invoice, payment_status=ST_PP_COMPLETED)
                    full_refund = original_transaction.mc_gross == ipn_obj.mc_gross
                except PayPalIPN.DoesNotExist:
                    full_refund = False
                for obj, paypal_trans in zip(obj_list, paypal_trans_list):
                    if hasattr(paypal_trans, "voucher_code"):
                        # check for voucher on paypal trans object; delete first
                        # UsedEventVoucher/UsedBlockVoucher if applicable
                        used_voucher = None
                        if obj_type == 'block':
                            used_voucher = UsedBlockVoucher.objects.filter(
                                voucher__code=paypal_trans.voucher_code,
                                user=obj.user
                            ).first()
                        elif obj_type == 'booking' and obj.status == "CANCELLED":
                            used_voucher = UsedEventVoucher.objects.filter(
                                voucher__code=paypal_trans.voucher_code,
                                user=obj.user
                            ).first()
                        elif obj_type == "gift_voucher":
                            # if this is a refunded gift voucher, deactivate it
                            obj.activated = False
                            obj.save()
                        if used_voucher:
                            voucher_refunded = True
                            used_voucher.delete()
                    if (obj_type == 'booking' and obj.status == "CANCELLED") or full_refund:
                        # only set cancelled bookings or objs in fully refunded transactions to unpaid;
                        # refund could apply to more than one booking
                        if hasattr(obj, "payment_confirmed"):
                            obj.payment_confirmed = False
                        obj.paid = False
                        obj.save()

                ActivityLog.objects.create(
                    log='Transaction for {} id(s) {} for user {} has been {} from paypal; '
                        'paypal transaction id {}, invoice id {}.{}'.format(
                            obj_type.title(), obj_ids,
                            obj_user,
                            "refunded" if full_refund else "part refunded",
                            ipn_obj.txn_id, paypal_trans_list[0].invoice_id,
                            f' Used voucher deleted (code {paypal_trans.voucher_code}).' if voucher_refunded else ''
                        )
                )
                if settings.SEND_ALL_STUDIO_EMAILS:
                    send_processed_refund_emails(obj_type, obj_ids, obj_list, paypal_trans_list)

        elif ipn_obj.payment_status == ST_PP_PENDING:
            if obj_type == 'paypal_test':
                ActivityLog.objects.create(
                    log='Test payment (invoice {} for paypal email {} has '
                        '"pending" status; email address may not be '
                        'verified. PayPal transaction id {}'.format(
                            additional_data['test_invoice'],
                            additional_data['test_paypal_email'],
                            ipn_obj.txn_id
                        )
                )
                send_processed_test_pending_emails(additional_data)
            else:
                ActivityLog.objects.create(
                    log='PayPal payment returned with status PENDING for {} {}; '
                        'ipn obj id {} (txn id {})'.format(
                         obj_type, obj_ids, ipn_obj.id, ipn_obj.txn_id
                        )
                )
                raise PayPalTransactionError(
                    'PayPal payment returned with status PENDING for {} {}; '
                    'ipn obj id {} (txn id {}).  This is usually due to an '
                    'unrecognised or unverified paypal email address.'.format(
                        obj_type, obj_ids, ipn_obj.id, ipn_obj.txn_id
                    )
                )

        elif ipn_obj.payment_status == ST_PP_COMPLETED:
            # we only process if payment status is completed
            # check for django-paypal flags (checks for valid payment status,
            # duplicate trans id, correct receiver email, valid secret (if using
            # encrypted), mc_gross, mc_currency, item_name and item_number are all
            # correct
            if obj_type == 'paypal_test':
                ActivityLog.objects.create(
                    log='Test payment (invoice {} for paypal email {} has '
                        'been paid and completed by PayPal; PayPal '
                        'transaction id {}'.format(
                            additional_data['test_invoice'],
                            additional_data['test_paypal_email'],
                            ipn_obj.txn_id
                        )
                )
                send_processed_test_confirmation_emails(additional_data)
            else:
                voucher_error = process_completed_payment(obj_list, paypal_trans_list, ipn_obj, obj_type, voucher_code, voucher_applied_to)

                ActivityLog.objects.create(
                    log='{} id(s) {} for user {} paid by PayPal; paypal {} ids {}'.format(
                        obj_type.title(),
                        obj_ids,
                        obj_user,
                        obj_type,
                        ', '.join([str(pp.id) for pp in paypal_trans_list]),
                    )
                )

                send_processed_payment_emails(obj_type, obj_ids, obj_list, paypal_trans_list)
                if obj_type == "gift_voucher":
                    send_gift_voucher_email(obj_list[0])

                if voucher_error:
                    # raise error from invalid voucher here so emails for
                    # payments are still sent
                    raise voucher_error
                elif voucher_code:
                    ActivityLog.objects.create(
                        log='Voucher code {} used for paypal txn {} ({} id(s) '
                            '{}) by user {}'.format(
                            voucher_code,
                            ipn_obj.txn_id,
                            obj_type,
                            obj_ids,
                            obj_user,
                        )
                    )

        else:  # any other status
            if obj_type == 'paypal_test':
                ActivityLog.objects.create(
                    log='Test payment (invoice {} for paypal email {} '
                        'processed with unexpected payment status {}; PayPal '
                        'transaction id {}'.format(
                            additional_data['test_invoice'],
                            additional_data['test_paypal_email'],
                            ipn_obj.payment_status,
                            ipn_obj.txn_id
                        )
                )
                send_processed_test_unexpected_status_emails(
                    additional_data, ipn_obj.payment_status
                )

            else:
                ActivityLog.objects.create(
                    log='Unexpected payment status {} for {} {}; '
                        'ipn obj id {} (txn id {})'.format(
                         obj_type, obj_ids,
                         ipn_obj.payment_status.upper(), ipn_obj.id, ipn_obj.txn_id
                        )
                )
                raise PayPalTransactionError(
                    'Unexpected payment status {} for {} {}; ipn obj id {} '
                    '(txn id {})'.format(
                        ipn_obj.payment_status.upper(), obj_type, obj_ids,
                        ipn_obj.id, ipn_obj.txn_id
                    )
                )

    except Exception as e:
        # if anything else goes wrong, send a warning email
        if obj_type == 'paypal_test':
            logger.warning(
                'Problem processing payment for paypal email test to {}; '
                'invoice_id {}, transaction  id: {}.  Exception: {}'.format(
                    additional_data['test_paypal_email'],
                    additional_data['test_invoice'],
                    ipn_obj.txn_id, e
                )
            )
        else:
            logger.warning(
                'Problem processing payment for {} {}; invoice_id {}, transaction '
                'id: {}.  Exception: {}'.format(
                    obj_type.title(), obj_ids, ipn_obj.invoice, ipn_obj.txn_id, e
                    )
            )

        send_mail(
            '{} There was some problem processing payment for '
            '{} {}'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, obj_type,
                'payment to paypal email {}'.format(
                    additional_data['test_paypal_email']
                ) if obj_type == 'paypal_test' else
                'id {}'.format(obj_ids)
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
        obj_list = obj_dict['obj_list']
        obj_type = obj_dict['obj_type']
        paypal_trans_list = obj_dict['paypal_trans_list']
        voucher_code = obj_dict.get('voucher_code')
        voucher_applied_to = obj_dict.get("voucher_applied_to")
        additional_data = obj_dict.get('additional_data')
        obj_ids = ', '.join([str(obj.id) for obj in obj_list])
        obj_user = obj_dict["obj_user"]

        if obj_list:
            # check if the status is completed; mark booking as paid but send warning email too
            # Don't mark as paid if the flag is duplicate transaction id
            if ipn_obj.payment_status == ST_PP_COMPLETED and 'duplicate txn_id' not in ipn_obj.flag_info.lower():
                voucher_error = process_completed_payment(obj_list, paypal_trans_list, ipn_obj, obj_type, voucher_code, voucher_applied_to)

                ActivityLog.objects.create(
                    log='{} id(s) {} for user {} paid by PayPal; paypal '
                        '{} ids {}'.format(
                        obj_type.title(),
                        obj_ids,
                        obj_user,
                        obj_type,
                        ', '.join([str(pp.id) for pp in paypal_trans_list]),
                    )
                )

                # Don't send payment emails to user, so we get the warning email and can check the payment first
                if voucher_error:
                    raise voucher_error
                elif voucher_code:
                    ActivityLog.objects.create(
                        log='Voucher code {} used for paypal txn {} ({} id(s) '
                            '{}) by user {}'.format(
                            voucher_code,
                            ipn_obj.txn_id,
                            obj_type,
                            obj_ids,
                            obj_user,
                        )
                    )

            logger.warning('Invalid Payment Notification received from PayPal for {} {} (status {})'.format(
                obj_type.title(),
                'payment to paypal email {}'.format(
                    additional_data['test_paypal_email']
                    ) if obj_type == 'paypal_test' else
                    'id {}'.format(obj_ids),
                ipn_obj.payment_status
                ),
            )
            send_mail(
                'WARNING! Invalid Payment Notification received from PayPal',
                'PayPal sent an invalid transaction notification while '
                'attempting to process payment for {} {}.\n\nThe flag '
                'info was "{}"\n\nPayment status is {}'.format(
                    obj_type.title(),
                    'payment to paypal email {}'.format(
                        additional_data['test_paypal_email']
                    ) if obj_type == 'paypal_test' else 'id {}'.format(obj_ids),
                    ipn_obj.flag_info,
                    ipn_obj.payment_status
                ),
                settings.DEFAULT_FROM_EMAIL, [settings.SUPPORT_EMAIL],
                fail_silently=False)

    except Exception as e:
        # if anything else goes wrong, send a warning email
        logger.warning(
            'Problem processing payment_not_received for {} {}; invoice_'
            'id {}, transaction id: {}. Exception: {}'.format(
                obj_type.title(),
                'payment to paypal email {}'.format(
                    additional_data['test_paypal_email']
                ) if obj_type == 'paypal_test' else
                'id {}'.format(obj_ids),
                ipn_obj.invoice,
                ipn_obj.txn_id, e
                )
        )
        send_mail(
            '{} There was some problem processing payment_not_received for '
            '{} {}'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, obj_type,
                'payment to paypal email {}'.format(
                    additional_data['test_paypal_email']
                ) if obj_type == 'paypal_test' else
                'id {}'.format(obj_ids)
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
