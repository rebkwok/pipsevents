'''
Check for users who do not have a paid class or event booking within the past
year.
Delete both Print and Online disclaimers (there should only be one or the
other, but check for both just in case)
Email studio notification and note whether online or paper or both
ActivityLog it
'''
import logging
from datetime import timedelta

from django.utils import timezone
from django.contrib.auth.models import User
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import get_template
from django.template import Context
from django.core.management.base import BaseCommand
from django.core import management

from accounts.models import OnlineDisclaimer, PrintDisclaimer
from booking.email_helpers import send_support_email
from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Delete disclaimers for users who do not have a paid booking ' \
           'within the past year'

    def handle(self, *args, **options):

        # get relevant users

        expire_date = timezone.now() - timedelta(days=365)

        expired_users = []

        for user in User.objects.all():
            recent_bookings = [
                True for booking in user.bookings.all()
                if booking.event.date > expire_date and booking.paid
                ]
            if not recent_bookings:
                expired_users.append(user)

        print_dislaimer_users = PrintDisclaimer.objects.filter(user__in=expired_users)
        online_disclaimer_users = OnlineDisclaimer.objects.filter(user__in=expired_users)

        if expired_users:
            # email studio
            ctx = Context({
                'print_disclaimer_users': print_dislaimer_users,
                'online_disclaimer_users': online_disclaimer_users
            })

            # send mail to studio
            try:
                send_mail('{} Disclaimers deleted for expired users'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                ),
                    get_template(
                        'account/email/delete_disclaimers.txt'
                    ).render(ctx),
                    settings.DEFAULT_FROM_EMAIL,
                    [settings.DEFAULT_STUDIO_EMAIL],
                    html_message=get_template(
                        'account/email/delete_disclaimers.html'
                        ).render(ctx),
                    fail_silently=False)
            except Exception as e:
                # send mail to tech support with Exception
                send_support_email(
                    e, __name__, "Automatic disclaimer deletion - studio email"
                )

            ActivityLog.objects.create(
                log='Print diclaimers deleted for expired users: {}'.format(
                    ', '.format(
                        [user.username for user in print_dislaimer_users]
                    )
                )
            )
            ActivityLog.objects.create(
                log='Online diclaimers deleted for expired users: {}'.format(
                    ', '.format(
                        [user.username for user in online_disclaimer_users]
                    )
                )
            )
        else:
            self.stdout.write('No ticket bookings to cancel')
            ActivityLog.objects.create(
                log='Delete disclaimers job run; no expired users'
            )

