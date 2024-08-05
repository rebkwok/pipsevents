from django.conf import settings
from django.contrib.auth.models import User

from common.email import send_email


def _get_user_from_invoice(invoice):
    try:
        return User.objects.get(username=invoice.username)
    except User.DoesNotExist:
        return None
    

def _get_user_from_membership(event_object):
    user = User.objects.filter(userprofile__stripe_customer_id=event_object.customer).first()
    if event_object.object == "subscription":
        user_membership = user.memberships.get(subscription_id=event_object.id)
    else:
        user_membership = None
            
    if user is not None:
        return user, user_membership
    return None, None


def send_processed_payment_emails(invoice):
    user = _get_user_from_invoice(invoice)
    ctx = {
        'user': user,
        'invoice': invoice,
    }

    # send email to studio
    if settings.SEND_ALL_STUDIO_EMAILS:
        send_email(
            '{} Payment processed'.format(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX),
            txt_template='stripe_payments/email/payment_processed_to_studio.txt',
            html_template='stripe_payments/email/payment_processed_to_studio.html',
            to_email=[settings.DEFAULT_STUDIO_EMAIL],
            extra_ctx=ctx
        )

    # send email to user
    send_email(
        f'{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Your payment has been processed',
        txt_template='stripe_payments/email/payment_processed_to_user.txt',
        to_email=[user.email if user is not None else invoice.username],
        html_template='stripe_payments/email/payment_processed_to_user.html',
        extra_ctx=ctx,
    )


def send_processed_refund_emails(invoice, event_object):
    if invoice is None:
        user, user_membership = _get_user_from_membership(event_object)
    else:
        user = _get_user_from_invoice(invoice)
        user_membership = None
    ctx = {
        'user': user,
        'invoice': invoice,
        'user_membership': user_membership,
        'refund_id': event_object.id,
    }

    # send email to support only for checking;
    send_email(
        'WARNING: Payment refund processed',
        txt_template='stripe_payments/email/payment_refund_processed.txt',
        to_email=[settings.SUPPORT_EMAIL],
        extra_ctx=ctx,
    )


def send_failed_payment_emails(payment_intent=None, error=None, event_type=None, event_object=None):
    # send email to support only for checking;
    send_email(
        'WARNING: Something went wrong processing a stripe event!',
        txt_template='stripe_payments/email/payment_error.txt',
        to_email=[settings.SUPPORT_EMAIL],
        extra_ctx={"payment_intent": payment_intent, "error": error, "event_type": event_type, "event_object": event_object}
    )


def send_gift_voucher_email(voucher):
    send_email(
        f'{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Gift Voucher',
        txt_template='stripe_payments/email/gift_voucher.txt',
        html_template='stripe_payments/email/gift_voucher.html',
        to_email=[voucher.purchaser_email],
        extra_ctx= {"voucher": voucher}
    )


def send_updated_membership_email_to_support(user_membership, new_price_id, old_price_id):
    send_email(
        "Unexpected user membership price change",
        body=(
            f"User membership for user {user_membership.user} changed price on stripe\n"
            f"User membership id: {user_membership.id}\n"
            f"Old price id: {old_price_id}\n"
            f"New price id: {new_price_id}\n"
        ),
        to_email=[settings.SUPPORT_EMAIL],
    )


def _send_subscription_email(event_object, template_name, subject, user_membership=None):
    if user_membership is None:
        user, user_membership = _get_user_from_membership(event_object)
    else:
        user = user_membership.user

    ctx = {
        'user': user,
        'user_membership': user_membership,
    }

    send_email(
        f'{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} {subject}',
        txt_template=f'stripe_payments/email/{template_name}.txt',
        to_email=[user.email],
        html_template=f'stripe_payments/email/{template_name}.html',
        extra_ctx=ctx
    )

def send_payment_expiring_email(event_object):
    _send_subscription_email(event_object, "payment_expiring", "Action required - Update your membership payment method")


def send_subscription_past_due_email(event_object):
    _send_subscription_email(event_object, "subscription_past_due", "Action required - Complete your membership payment")


def send_subscription_renewal_upcoming_email(event_object):
    _send_subscription_email(event_object, "subscription_renewal_upcoming", "Your membership will renew soon")


def send_subscription_created_email(user_membership):
    _send_subscription_email(None, "subscription_created", "Your membership has been set up", user_membership=user_membership)
