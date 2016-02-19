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
from django.core.management.base import BaseCommand
from django.db.models import Q

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
            if not user.bookings.exists():
                expired_users.append(user)
            else:
                recent_bookings = [
                    True for booking in user.bookings.all()
                    if (booking.event.date > expire_date) and booking.paid
                    ]
                if not recent_bookings:
                    expired_users.append(user)

        old_print_disclaimers = PrintDisclaimer.objects.filter(
            date__lt=expire_date
        )
        old_online_disclaimers = OnlineDisclaimer.objects.filter(
            Q(date__lt=expire_date) &
            (Q(date_updated__isnull=True) | Q(date_updated__lt=expire_date))
        )
        print_disclaimer_users_to_delete = old_print_disclaimers.filter(
            user__in=expired_users
        )
        print_disclaimer_users = [
            '{} {}'.format(disc.user.first_name, disc.user.last_name)
            for disc in print_disclaimer_users_to_delete
            ]

        online_disclaimer_users_to_delete = old_online_disclaimers.filter(
            user__in=expired_users
        )
        online_disclaimer_users = [
            '{} {}'.format(disc.user.first_name, disc.user.last_name)
            for disc in online_disclaimer_users_to_delete
            ]

        print_disclaimer_users_to_delete.delete()
        online_disclaimer_users_to_delete.delete()

        if print_disclaimer_users or online_disclaimer_users:
            # email studio
            ctx = {
                'print_disclaimer_users': print_disclaimer_users,
                'online_disclaimer_users': online_disclaimer_users
            }

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
                log='Print disclaimers deleted for expired users: {}'.format(
                    ', '.format(print_disclaimer_users)
                )
            )
            ActivityLog.objects.create(
                log='Online disclaimers deleted for expired users: {}'.format(
                    ', '.format(online_disclaimer_users)
                )
            )
        else:
            self.stdout.write('No disclaimers to delete')
            ActivityLog.objects.create(
                log='Delete disclaimers job run; no expired users'
            )
