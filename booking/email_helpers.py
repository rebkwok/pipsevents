from django.conf import settings
from django.core.mail import send_mail
from django.core.mail.message import EmailMessage, EmailMultiAlternatives
from django.template import Context
from django.template.loader import get_template

def send_support_email(e, module_name="", extra_subject=""):
    try:
        send_mail('{} An error occurred! ({})'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, extra_subject
            ),
            'An error occurred in {}\n\nThe exception '
            'raised was "{}"'.format(module_name, e),
            settings.DEFAULT_FROM_EMAIL,
            [settings.SUPPORT_EMAIL],
            fail_silently=True)
    except Exception as ex:
        ActivityLog.objects.create(
            log="Problem sending an email ({}: {})".format(
                module_name, ex
            )
        )


def send_waiting_list_email(
    event, users, host="http://booking.thewatermelonstudio.co.uk"
):
    ev_type = 'classes' if event.event_type.event_type == 'CL' else 'events'

    msg = EmailMultiAlternatives(
        '{} {}'.format(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, event),
        get_template('booking/email/waiting_list_email.txt').render(
            {'event': event, 'host': host, 'ev_type': ev_type}
        ),
        settings.DEFAULT_FROM_EMAIL,
        bcc=[user.email for user in users],
    )
    msg.attach_alternative(
        get_template(
            'booking/email/waiting_list_email.html').render(
            {'event': event, 'host': host, 'ev_type': ev_type}
        ),
        "text/html"
    )
    msg.send(fail_silently=False)
