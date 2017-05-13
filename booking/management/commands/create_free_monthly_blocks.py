'''
Create free 5-class blocks for users in 'free_monthly_blocks' group
Will be run on 1st of each month as cron job
'''
import datetime

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
        free_5_blocktype, _ = BlockType.objects.get_or_create(
            identifier='Free - 5 classes', active=False, cost=0, duration=1,
            size=5, event_type=event_type
        )
        free_7_blocktype, _ = BlockType.objects.get_or_create(
            identifier='Free - 7 classes', active=False, cost=0, duration=1,
            size=7, event_type=event_type
        )

        group5, _ = Group.objects.get_or_create(name='free_5monthly_blocks')
        group7, _ = Group.objects.get_or_create(name='free_7monthly_blocks')

        groupmap = {
            group5: {
                'blocktype': free_5_blocktype, 'users': group5.user_set.all()
            },
            group7: {
                'blocktype': free_7_blocktype, 'users': group7.user_set.all()
            }
        }

        created_users = []
        already_active_users = []

        for group in groupmap.keys():
            free_blocktype = groupmap[group]['blocktype']
            users = groupmap[group]['users']

            if not users:
                self.stdout.write('No users in {} group'.format(group.name))
                send_mail(
                    '{} Free blocks creation failed'.format(
                        settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
                    ),
                    'No users in {} group'.format(group.name),
                    settings.DEFAULT_FROM_EMAIL,
                    [settings.SUPPORT_EMAIL],
                    fail_silently=False
                )

            for user in users:
                active_free_blocks = [
                    block for block in
                    Block.objects.filter(block_type=free_blocktype, user=user)
                    if block.active_block()
                ]
                if active_free_blocks:
                    already_active_users.append(user)
                else:
                    # Block expiry is set to the end of the date it's created
                    # create new block with start date previous day, so when
                    # we run this command on 1st of the month, it
                    # expires on last day of that month, not 1st of next month
                    Block.objects.create(
                        block_type=free_blocktype, user=user, paid=True,
                        start_date=(timezone.now() - datetime.timedelta(1))
                        .replace(hour=23, minute=59, second=59)
                    )
                    created_users.append(user)

        if created_users:
            message = 'Free class blocks created for {}'.format(
                ', '.join(
                    ['{} {}'.format(user.first_name, user.last_name)
                     for user in created_users]
                )
            )
            ActivityLog.objects.create(log=message)
            self.stdout.write(message)
            send_mail(
                '{} Free blocks created'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
                ),
                message,
                settings.DEFAULT_FROM_EMAIL,
                [settings.SUPPORT_EMAIL],
                fail_silently=False
            )

        if already_active_users:
            message = 'Free monthly class blocks not created for {} as ' \
                      'active free block already exists'.format(
                ', '.join(
                    ['{} {}'.format(user.first_name, user.last_name)
                     for user in already_active_users]
                )
            )
            ActivityLog.objects.create(log=message)
            self.stdout.write(message)
            send_mail(
                '{} Free blocks not created'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
                ),
                message,
                settings.DEFAULT_FROM_EMAIL,
                [settings.SUPPORT_EMAIL],
                fail_silently=False
            )
