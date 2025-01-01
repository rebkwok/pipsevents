import csv
import os
from pathlib import Path
import subprocess

from dateutil.relativedelta import relativedelta

from django.conf import settings
from django.core import management
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.encoding import smart_str

from ...models import ActivityLog


class Command(BaseCommand):

    help = "Delete old ActivityLogs"

    def add_arguments(self, parser):
        parser.add_argument(
            '--age',
            default=1,
            type=int,
            help='Age (in years) of logs to delete.  Defaults to 1 yr, i.e. will delete all logs older than 1 year old'
        )

    def handle(self, *args, **options):
        age = options.get('age')
        now = timezone.now()
        # set cutoff to beginning of this day <age> years ago
        cutoff = (now-relativedelta(years=age)).replace(hour=0, minute=0, second=0, microsecond=0)
        filename = f"{settings.S3_LOG_BACKUP_ROOT_FILENAME}_{cutoff.strftime('%Y-%m-%d')}_{now.strftime('%Y%m%d%H%M%S')}.csv"
        local_filepath = Path(settings.LOG_FOLDER) / "activitylogs_backup" / filename
        local_filepath.parent.mkdir(exist_ok=True)
        s3_upload_path = os.path.join(settings.S3_LOG_BACKUP_PATH, filename)
        # Delete the empty logs first
        management.call_command('delete_empty_job_logs', cutoff.strftime('%Y%m%d'))

        old_logs = ActivityLog.objects.filter(timestamp__lt=cutoff)
        old_logs_count = old_logs.count()
        if old_logs_count > 0:
            with open(local_filepath, "w") as outfile:
                wr = csv.writer(outfile)
                wr.writerow([
                    smart_str(u"Timestamp"),
                    smart_str(u"Log")
                ])
                for activitylog in old_logs:
                    wr.writerow([
                        smart_str(activitylog.timestamp.isoformat()),
                        smart_str(activitylog.log)
                    ])

            subprocess.run(["aws", "s3", "cp", str(local_filepath), s3_upload_path], check=True)
            os.unlink(local_filepath)

            old_logs.delete()
            message = f"{old_logs_count} activitylogs older than {cutoff.strftime('%Y-%m-%d')} backed up to s3 and deleted"
            self.stdout.write(message)
            ActivityLog.objects.create(log=message)
