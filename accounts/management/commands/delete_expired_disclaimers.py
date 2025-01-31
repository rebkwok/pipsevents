'''
Delete all disclaimers signed or updated > 6 yrs ago
ActivityLog it
'''
import logging

from django.utils import timezone
from django.core.management.base import BaseCommand
from django.db.models import Q

from dateutil.relativedelta import relativedelta

from accounts.models import ArchivedDisclaimer, NonRegisteredDisclaimer, OnlineDisclaimer
from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Delete any disclaimers over 6 years old"

    def handle(self, *args, **options):

        # get relevant users
        expire_date = timezone.now() - relativedelta(years=6)

        old_online_disclaimers_to_delete = OnlineDisclaimer.objects\
            .select_related('user').filter(
            Q(date__lt=expire_date) & (Q(date_updated__isnull=True) | Q(date_updated__lt=expire_date))
        )
        online_disclaimer_users = [
            '{} {}'.format(disc.user.first_name, disc.user.last_name)
            for disc in old_online_disclaimers_to_delete
            ]

        old_non_registered_disclaimers_to_delete = NonRegisteredDisclaimer.objects.filter(
            date__lt=expire_date
        )
        non_registered_disclaimer_users = [
            '{} {}'.format(disc.first_name, disc.last_name)
            for disc in old_non_registered_disclaimers_to_delete
            ]

        old_archieved_disclaimers_to_delete = ArchivedDisclaimer.objects.filter(
            Q(date__lt=expire_date) &
            (Q(date_updated__isnull=True) | Q(date_updated__lt=expire_date))
        )
        archive_disclaimer_users = [disc.name for disc in old_archieved_disclaimers_to_delete]

        old_online_disclaimers_to_delete.delete()
        old_non_registered_disclaimers_to_delete.delete()
        old_archieved_disclaimers_to_delete.delete()

        if online_disclaimer_users:
            ActivityLog.objects.create(
                log='Online disclaimers more than 6 yrs old deleted for '
                    'users: {}'.format(
                        ', '.join(online_disclaimer_users)
                    )
            )
        if non_registered_disclaimer_users:
            ActivityLog.objects.create(
                log='Non-registered disclaimers more than 6 yrs old deleted for '
                    'users: {}'.format(
                        ', '.join(non_registered_disclaimer_users)
                    )
            )
        if archive_disclaimer_users:
            ActivityLog.objects.create(
                log='Archived disclaimers more than 6 yrs old deleted for '
                    'users: {}'.format(
                        ', '.join(archive_disclaimer_users)
                    )
            )
        if not (online_disclaimer_users or non_registered_disclaimer_users or archive_disclaimer_users):
            self.stdout.write('No disclaimers to delete')
            ActivityLog.objects.create(
                log='Delete disclaimers job run; no expired disclaimers'
            )
