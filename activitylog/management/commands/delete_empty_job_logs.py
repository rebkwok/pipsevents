from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from activitylog.models import ActivityLog
from studioadmin.views.activity_log import EMPTY_JOB_TEXT

class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument(
            '--before',
            help='Date in format YYYYMMDD before which empty logs will be '
                 'deleted. Logs dated prior to 00:00 UTC on the specified '
                 'date will be deleted.  Enter "now" to delete all empty job '
                 'logs.'
        )

    def handle(self, *args, **options):
        before_date_raw = options.get('before')
        if before_date_raw == 'now':
            logs = ActivityLog.objects.filter(log__in=EMPTY_JOB_TEXT)
        else:
            try:
                # convert before date to datetime obj, with HH MM SS at 0
                before_date = datetime.strptime(before_date_raw, '%Y%m%d')\
                    .replace(tzinfo=timezone.utc)
                if before_date > timezone.now():
                    self.stdout.write(
                        'Invalid date {}; before date must be in the '
                        'past.'.format(before_date_raw)
                    )
                    return
                logs = ActivityLog.objects.filter(
                    log__in=EMPTY_JOB_TEXT, timestamp__lt=before_date
                )
            except ValueError:
                self.stdout.write(
                    'Invalid date; enter in format YYYYMMDD'
                )
                return

        if logs:
            log_count = logs.count()
            logs.delete()
            self.stdout.write(
                'Logs for empty jobs deleted ({})'.format(log_count)
            )
