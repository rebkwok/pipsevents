'''
Delete all disclaimers signed or updated > 6 yrs ago
ActivityLog it
'''
import logging

from django.utils import timezone
from django.core.management.base import BaseCommand
from django.db.models import Q

from dateutil.relativedelta import relativedelta

from accounts.models import OnlineDisclaimer, PrintDisclaimer
from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Delete any disclaimers over 3 years old"

    def handle(self, *args, **options):

        # get relevant users
        expire_date = timezone.now() - relativedelta(years=6)

        old_print_disclaimers_to_delete = PrintDisclaimer.objects\
            .select_related('user').filter(date__lt=expire_date)
        print_disclaimer_users = [
            '{} {}'.format(disc.user.first_name, disc.user.last_name)
            for disc in old_print_disclaimers_to_delete
            ]

        old_online_disclaimers_to_delete = OnlineDisclaimer.objects\
            .select_related('user').filter(
            Q(date__lt=expire_date) &
            (Q(date_updated__isnull=True) | Q(date_updated__lt=expire_date))
        )
        online_disclaimer_users = [
            '{} {}'.format(disc.user.first_name, disc.user.last_name)
            for disc in old_online_disclaimers_to_delete
            ]
        old_print_disclaimers_to_delete.delete()
        old_online_disclaimers_to_delete.delete()

        if print_disclaimer_users:
            ActivityLog.objects.create(
                log='Print disclaimers more than 6 yrs old deleted for '
                    'users: {}'.format(
                    ', '.join(print_disclaimer_users)
                )
            )
        if online_disclaimer_users:
            ActivityLog.objects.create(
                log='Online disclaimers more than 6 yrs old deleted for '
                    'users: {}'.format(
                        ', '.join(online_disclaimer_users)
                    )
            )
        if not print_disclaimer_users or online_disclaimer_users:
            self.stdout.write('No disclaimers to delete')
            ActivityLog.objects.create(
                log='Delete disclaimers job run; no expired users'
            )
