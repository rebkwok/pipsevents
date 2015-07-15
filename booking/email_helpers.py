from django.conf import settings
from django.core.mail import send_mail
from django.template import Context

def send_support_email(e, module_name="", extra_subject=""):

    send_mail('{} An error occurred! ({})'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, extra_subject
        ),
        'An error occurred in {}\n\nThe exception '
        'raised was "{}"'.format(module_name, e),
        settings.DEFAULT_FROM_EMAIL,
        [settings.SUPPORT_EMAIL],
        fail_silently=True)
