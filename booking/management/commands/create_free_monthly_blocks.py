'''
Create free 5-class blocks for users in 'free_monthly_blocks' group
Will be run on 1st of each month as cron job
'''
import calendar
import datetime
from datetime import timezone as dt_timezone

import re

from django.contrib.auth.models import Group
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.template.loader import get_template

from booking.models import Block, BlockType, EventType

from activitylog.models import ActivityLog


class Command(BaseCommand):
    help = 'create free monthly blocks for instructors'

    def handle(self, *args, **options):
        event_type = EventType.objects.get(subtype='Pole level class')
        created_users = []
        already_active_users = []
        try:
            instructors = Group.objects.get(name="instructors")
        except Group.DoesNotExist:
            message = "No instructor group found"
        else:
            free_blocktype, _ = BlockType.objects.get_or_create(
                identifier=f"Free - 5 classes",
                active=False,
                cost=0,
                duration=1,
                size=5,
                event_type=event_type
            )

            users = instructors.user_set.exclude(id__in=settings.FREE_BLOCK_USERS_IGNORE_LIST)
            now = timezone.now()
            _, end_day = calendar.monthrange(now.year, now.month)
            start = datetime.datetime(now.year, now.month, 1, 0, 0, tzinfo=dt_timezone.utc)
            end = datetime.datetime(now.year, now.month, end_day, tzinfo=dt_timezone.utc)
            end = Block.get_end_of_day(end)
            for user in users:
                _, created = Block.objects.get_or_create(
                    block_type=free_blocktype, user=user, start_date=start, extended_expiry_date=end
                )
                if not created:
                    already_active_users.append(user)
                else:
                    created_users.append(user)

            results = {"created": created_users, "already_active": already_active_users}

            message = f"Group: {instructors.name}\n"
            if not any(results.values()):
                message += "No users in this group\n"

            if results["created"]:
                message += 'Free class blocks created for {}\n'.format(
                        ', '.join(
                            ['{} {}'.format(user.first_name, user.last_name)
                                for user in results["created"]]
                        )
                    )

            if results["already_active"]:
                message += 'Free block for this month already exists for {}\n'.format(
                        ', '.join(
                            ['{} {}'.format(user.first_name, user.last_name)
                                for user in results["already_active"]]
                        )
                    )

            ActivityLog.objects.create(
                log=f"Free block creation: Group instructors; "
                    f"created {len(results['created'])}, "
                    f"already_exists {len(results['already_active'])}"
            )

        self.stdout.write(message)
        send_mail(
            '{} Free monthly blocks creation'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
            ),
            message,
            settings.DEFAULT_FROM_EMAIL,
            [settings.SUPPORT_EMAIL],
            fail_silently=False
        )
        for user in created_users:
            send_mail(
                f'{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Your free block',
                get_template('booking/email/free_instructor_block_created.txt').render(),
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False
            )

