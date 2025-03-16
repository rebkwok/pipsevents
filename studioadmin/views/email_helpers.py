from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail.message import EmailMultiAlternatives
from django.contrib import messages
from django.template.loader import get_template

from booking.models import UserMembership


def send_new_classes_email_to_members(request, new_classes):

    members = list(User.objects.filter(id__in=UserMembership.active_member_ids()).values_list("email", flat=True))

    ctx = {
        "new_classes": new_classes,
        "host": f'http://{request.get_host()}'
    }

    msg = EmailMultiAlternatives(
        f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX}: New classes have been added",
        get_template(
            'studioadmin/email/new_classes_uploaded.txt').render(
                ctx
            ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        bcc=[*members, settings.SUPPORT_EMAIL],
    )
    msg.attach_alternative(
        get_template(
            'studioadmin/email/new_classes_uploaded.html').render(
                ctx
            ),
        "text/html"
    )
    msg.send(fail_silently=False)
    if members:
        messages.success(request, f"{len(members)} member(s) have been notified by email")
