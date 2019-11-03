from datetime import datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from activitylog.models import ActivityLog

class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument(
            'before',
            help='Date in format YYYYMMDD before which empty logs will be '
                 'deleted. Logs dated prior to 00:00 UTC on the specified '
                 'date will be deleted.  Enter "now" to delete all empty job '
                 'logs.'
        )
        parser.add_argument('--dry-run')

    def handle(self, *args, **options):
        before_date_raw = options.get('before')
        dry_run = options.get('dry_run')
        if before_date_raw == 'now':
            logs = ActivityLog.objects.filter(log__in=settings.EMPTY_JOB_TEXT)
            before_date = (timezone.now() + timedelta(1)).strftime('%Y%m%d')
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
                    log__in=settings.EMPTY_JOB_TEXT, timestamp__lt=before_date
                )
            except ValueError:
                self.stdout.write(
                    'Invalid date; enter in format YYYYMMDD'
                )
                return

        log_count = logs.count()
        if dry_run:
            self.stdout.write(
                f'{log_count} Logs for empty jobs before {before_date} will be deleted'
            )
        else:
            logs.delete()
            self.stdout.write(
                f'{log_count} Logs for empty jobs before {before_date} deleted'
            )
