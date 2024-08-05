from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.template.loader import get_template


def send_email(subject, to_email, body=None, txt_template=None, from_email=settings.DEFAULT_FROM_EMAIL, html_template=None, extra_ctx=None):
    assert body or txt_template
    extra_ctx = extra_ctx or {}
    ctx = {
        'host': f"https://{Site.objects.get_current().domain}",
        "studio_email": settings.DEFAULT_STUDIO_EMAIL,
        **extra_ctx
    }
    body = body or get_template(txt_template).render(ctx)
    html_message = get_template(html_template).render(ctx) if html_template else None

    send_mail(
        subject,
        body,
        from_email,
        to_email,
        html_message=html_message,
        fail_silently=False
    )
