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

    auto_book_user = None
    already_booked_cancelled = False
    for email in settings.AUTO_BOOK_EMAILS:
        if email in user_emails.copy():
            auto_book_user = User.objects.get(email=email)
            already_booked = Booking.objects.filter(
                event=event, user=auto_book_user
            )
            if already_booked.exists():
                if already_booked[0].status == 'OPEN':
                    user_emails.remove(auto_book_user.email)
                    waiting_list_user = WaitingListUser.objects.filter(
                        user=auto_book_user, event=event
                    ).delete()
                    auto_book_user = None
                else:
                    already_booked_cancelled = True

            if auto_book_user:
                break

    if auto_book_user:
        # retrieve event from db again to refresh cached properties
        ev = Event.objects.get(id=event.id)

        if already_booked_cancelled:
            booking = Booking.objects.get(event=ev, user=auto_book_user)
            booking.status = 'OPEN'
            booking.save()
        else:
            booking = Booking.objects.create(event=ev, user=auto_book_user)

        ctx = {
            'event': event,
            'host': host,
            'ev_type': ev_type,
            'booking': booking
        }

        msg = EmailMultiAlternatives(
            '{} You have been booked into {}'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, event
            ),
            get_template('booking/email/autobook_email.txt').render(ctx),
            settings.DEFAULT_FROM_EMAIL,
            to=[auto_book_user.email],
        )
        msg.attach_alternative(
            get_template('booking/email/autobook_email.html').render(ctx),
            "text/html"
        )
        msg.send(fail_silently=False)


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

    elif user_emails:
        # only send the waiting list email if we didn't autobook
        # check user emails in case the autobook user was already booked and
        # was the only one on the waiting list
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
