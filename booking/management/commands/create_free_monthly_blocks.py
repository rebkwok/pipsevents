'''
Create free 5-class blocks for users in 'free_monthly_blocks' group
Will be run on 1st of each month as cron job
'''
import calendar
import datetime
import re

from django.contrib.auth.models import User, Group
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from booking.models import Block, BlockType, EventType

from activitylog.models import ActivityLog


class Command(BaseCommand):
    help = 'create free monthly blocks for selected users'

    def handle(self, *args, **options):
        event_type = EventType.objects.get(subtype='Pole level class')
        groups = Group.objects.filter(name__regex=r"free_\d+monthly_blocks")
        results = {}

        for group in groups:
            number_of_classes_match = re.findall(r"free_(\d+)monthly_blocks", group.name)
            number_of_classes = int(number_of_classes_match[0])
            free_blocktype, _ = BlockType.objects.get_or_create(
                identifier=f"Free - {number_of_classes} classes",
                active=False,
                cost=0,
                duration=1,
                size=number_of_classes,
                event_type=event_type
            )

            created_users = []
            already_active_users = []
            users = group.user_set.all()

            now = timezone.now()
            _, end_day = calendar.monthrange(now.year, now.month)
            start = datetime.datetime(now.year, now.month, 1, 0, 0, tzinfo=timezone.utc)
            end = datetime.datetime(now.year, now.month, end_day, tzinfo=timezone.utc)
            end = Block.get_end_of_day(end)
            for user in users:
                block, created = Block.objects.get_or_create(
                    block_type=free_blocktype, user=user, start_date=start, extended_expiry_date=end
                )
                if not created:
                    already_active_users.append(user)
                else:
                    created_users.append(user)

            results[group.name] = {"created": created_users, "already_active": already_active_users}

        message = ""
        for group_name, group_results in results.items():
            message += f"Group: {group_name}\n"
            if not any(group_results.values()):
                message += "No users in this group\n"

            if group_results["created"]:
                message += 'Free class blocks created for {}\n'.format(
                        ', '.join(
                            ['{} {}'.format(user.first_name, user.last_name)
                             for user in group_results["created"]]
                        )
                    )

            if group_results["already_active"]:
                message += 'Free block for this month already exists for {}\n'.format(
                        ', '.join(
                            ['{} {}'.format(user.first_name, user.last_name)
                             for user in group_results["already_active"]]
                        )
                    )

            message += "=====================\n\n"
            ActivityLog.objects.create(
                log=f"Free block creation: Group {group_name}; "
                    f"created {len(group_results['created'])}, "
                    f"already_exists {len(group_results['already_active'])}"
            )

        if not message:
            message = "No free monthly groups found"

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
