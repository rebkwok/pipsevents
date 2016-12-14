from django.conf import settings
from django.core.mail import send_mail
from django.core.mail.message import EmailMultiAlternatives
from django.contrib.auth.models import User
from django.template.loader import get_template

from activitylog.models import ActivityLog
from .models import Booking, Event, WaitingListUser


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
    user_emails = [user.email for user in users]
    msg = EmailMultiAlternatives(
        '{} {}'.format(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, event),
        get_template('booking/email/waiting_list_email.txt').render(
            {'event': event, 'host': host, 'ev_type': ev_type}
        ),
        settings.DEFAULT_FROM_EMAIL,
        bcc=user_emails,
    )
    msg.attach_alternative(
        get_template(
            'booking/email/waiting_list_email.html').render(
            {'event': event, 'host': host, 'ev_type': ev_type}
        ),
        "text/html"
    )
    msg.send(fail_silently=False)

    auto_book_user = None
    for email in settings.AUTO_BOOK_EMAILS:
        if email in user_emails:
            auto_book_user = User.objects.get(email=email)
            break

    if auto_book_user:
        # retrieve event from db again to refresh cached properties
        ev = Event.objects.get(id=event.id)
        Booking.objects.create(event=ev, user=auto_book_user)
        send_mail(
            'Booking for {}'.format(event),
            'You have been booked into {}.  You still need to pay!'.format(
                event
            ),
            [settings.DEFAULT_FROM_EMAIL],
            [auto_book_user.email]
        )
        waiting_list_user = WaitingListUser.objects.get(
                user=auto_book_user, event=event
            )
        waiting_list_user.delete()
        ActivityLog.objects.create(
            log='Booking autocreated for User {}, {}'.format(
                auto_book_user.username, event
            )
        )
        ActivityLog.objects.create(
            log='User {} removed from waiting list '
            'for {}'.format(auto_book_user.username, event)
        )
