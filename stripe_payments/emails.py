from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.template.loader import get_template



def _get_user_from_invoice(invoice):
    try:
        return User.objects.get(username=invoice.username)
    except User.DoesNotExist:
        return None
    

def _get_user_from_membership(event_object):
    user = User.objects.filter(memberships__customer_id=event_object.customer).first()
    if user is not None:
        return user, user.memberships.get(customer_id=event_object.customer)
    return None, None


def send_processed_payment_emails(invoice):
    user = _get_user_from_invoice(invoice)
    ctx = {
        'host': f"https://{Site.objects.get_current().domain}",
        'user': user,
        'invoice': invoice,
        'domain': settings.DOMAIN,
        "studio_email": settings.DEFAULT_STUDIO_EMAIL
    }

    # send email to studio
    if settings.SEND_ALL_STUDIO_EMAILS:
        send_mail(
            '{} Payment processed'.format(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX),
            get_template('stripe_payments/email/payment_processed_to_studio.txt').render(ctx),
            settings.DEFAULT_FROM_EMAIL,
            [settings.DEFAULT_STUDIO_EMAIL],
            html_message=get_template('stripe_payments/email/payment_processed_to_studio.html').render(ctx),
            fail_silently=False
        )

    # send email to user
    send_mail(
        f'{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Your payment has been processed',
        get_template('stripe_payments/email/payment_processed_to_user.txt').render(ctx),
        settings.DEFAULT_FROM_EMAIL,
        [user.email if user is not None else invoice.username],
        html_message=get_template('stripe_payments/email/payment_processed_to_user.html').render(ctx),
        fail_silently=False
    )


def send_processed_refund_emails(invoice, event_object):
    if invoice is None:
        user, user_membership = _get_user_from_membership(event_object)
    else:
        user = _get_user_from_invoice(invoice)
        user_membership = None
    ctx = {
        'host': f"https://{Site.objects.get_current().domain}",
        'user': user,
        'invoice': invoice,
        'user_membership': user_membership,
        'refund_id': event_object.id,
        'domain': settings.DOMAIN,
        "studio_email": settings.DEFAULT_STUDIO_EMAIL
    }

    # send email to support only for checking;
    send_mail(
        'WARNING: Payment refund processed',
        get_template('stripe_payments/email/payment_refund_processed.txt').render(ctx),
        settings.DEFAULT_FROM_EMAIL,
        [settings.SUPPORT_EMAIL],
        fail_silently=False
    )


def send_failed_payment_emails(payment_intent=None, error=None, event_type=None, event_object=None):
    # send email to support only for checking;
    send_mail(
        'WARNING: Something went wrong processing a stripe event!',
        get_template('stripe_payments/email/payment_error.txt').render(
            {"payment_intent": payment_intent, "error": error, "event_type": event_type, "event_object": event_object}
        ),
        settings.DEFAULT_FROM_EMAIL,
        [settings.SUPPORT_EMAIL],
        fail_silently=False
    )


def send_gift_voucher_email(voucher):
    ctx = {"voucher": voucher}
    send_mail(
        f'{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Gift Voucher',
        get_template('stripe_payments/email/gift_voucher.txt').render(ctx),
        settings.DEFAULT_FROM_EMAIL,
        [voucher.purchaser_email],
        html_message=get_template('stripe_payments/email/gift_voucher.html').render(ctx),
        fail_silently=False
    )


def send_updated_membership_email_to_support(user_membership, new_price_id, old_price_id):
    send_mail(
        "Unexpected user membership price change",
        (
            f"User membership for user {user_membership.user} changed price on stripe\n"
            f"User membership id: {user_membership.id}\n"
            f"Old price id: {old_price_id}\n"
            f"New price id: {new_price_id}\n"
        ),
        settings.DEFAULT_FROM_EMAIL,
        [settings.SUPPORT_EMAIL],
        fail_silently=False
    )


def _send_subscription_email(event_object, template_name, subject, user_membership=None):
    if user_membership is None:
        user, user_membership = _get_user_from_membership(event_object)
    else:
        user = user_membership.user

    ctx = {
        'host': f"https://{Site.objects.get_current().domain}",
        'user': user,
        'user_membership': user_membership,
        'domain': settings.DOMAIN,
    }

    send_mail(
        f'{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} {subject}',
        get_template(f'stripe_payments/email/{template_name}.txt').render(ctx),
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        html_message=get_template(f'stripe_payments/email/{template_name}.html').render(ctx),
        fail_silently=False
    )

def send_payment_expiring_email(event_object):
    _send_subscription_email(event_object, "payment_expiring", "Action required - Update your membership payment method")


def send_subscription_past_due_email(event_object):
    _send_subscription_email(event_object, "subscription_past_due", "Action required - Complete your membership payments")


def send_subscription_renewal_upcoming_email(event_object):
    _send_subscription_email(event_object, "subscription_renewal_upcoming", "Your membership will renew soon")


def send_subscription_created_email(user_membership):
    _send_subscription_email(None, "subscription_created", "Your membership has been set up", user_membership=user_membership)
