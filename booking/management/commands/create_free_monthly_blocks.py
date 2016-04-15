'''
Create free 5-class blocks for users in 'free_monthly_blocks' group
Will be run on 1st of each month as cron job
'''
from django.contrib.auth.models import User, Group
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand

from booking.models import Block, BlockType, EventType

from activitylog.models import ActivityLog


class Command(BaseCommand):
    help = 'create free monthly blocks for selected users'

    def handle(self, *args, **options):
        event_type = EventType.objects.get(subtype='Pole level class')
        free_blocktype, _ = BlockType.objects.get_or_create(
            identifier='Free - 5 classes', active=False, cost=0, duration=1,
            size=5, event_type=event_type
        )

        users = []
        group = None
        try:
            group = Group.objects.get(name='free_monthly_blocks')
            users = group.user_set.all()
        except Group.DoesNotExist:
            error_msg = "Group named 'free_monthly_blocks' does not exist"
            self.stdout.write(error_msg)
            send_mail(
                '{} Free blocks creation failed'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
                ),
                'Error: {}'.format(error_msg),
                settings.DEFAULT_FROM_EMAIL,
                [settings.SUPPORT_EMAIL],
                fail_silently=False
            )

        if group:
            created_users = []
            already_active_users = []

            for user in users:
                active_free_blocks = [
                    block for block in
                    Block.objects.filter(block_type=free_blocktype, user=user)
                    if block.active_block()
                ]
                if active_free_blocks:
                    already_active_users.append(user)
                else:
                    Block.objects.create(
                        block_type=free_blocktype, user=user, paid=True
                    )
                    created_users.append(user)

            if created_users:
                message = 'Free 5 class blocks created for {}'.format(
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
                message = 'Free 5 class blocks not created for {} as active ' \
                          'free block already exists'.format(
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

            if not (already_active_users or created_users):
                self.stdout.write('No users in free_monthly_blocks group')
                send_mail(
                    '{} Free blocks creation failed'.format(
                        settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
                    ),
                    'No users in free_monthly_blocks group',
                    settings.DEFAULT_FROM_EMAIL,
                    [settings.SUPPORT_EMAIL],
                    fail_silently=False
                )
