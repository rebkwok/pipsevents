'''
Activate/deactivate blocktypes by identifier (to be used in cronjob to turn
certain blocktypes on/off
'''

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand

from booking.models import BlockType
from booking.email_helpers import send_support_email

from activitylog.models import ActivityLog


class Command(BaseCommand):
    help = 'activate/deactivate blocktypes with by identifier'

    def add_arguments(self, parser):
        parser.add_argument('identifiers', nargs='+', type=str)
        parser.add_argument('action', nargs=1, type=str)

    def handle(self, *args, **options):
        identifiers = options['identifiers']
        action = options['action'][0]
        actions = {
            'on': True,
            'off': False
        }
        blocktypes = BlockType.objects.filter(identifier__in=identifiers)
        for blocktype in blocktypes:
            blocktype.active = actions[action]
            blocktype.save()

        if blocktypes:
            message = 'Blocktypes with the identifier(s) "{}" have been {} ' \
                      '(ids {})'.format(
                ', '.join(identifiers),
                'activated' if action == 'on' else 'deactivated',
                ', '.join([str(bt.id) for bt in blocktypes])
                )
            ActivityLog.objects.create(log=message)
            self.stdout.write(message)

            try:
                send_mail('{} Block types {}'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                    'activated' if action == 'on' else 'deactivated'
                ),
                    'The following blocktype ids with the identifier(s) "{}" have '
                    'been {}:\n{}'.format(
                        ', '.join(identifiers),
                        'activated' if action == 'on' else 'deactivated',
                        ', '.join([str(bt.id) for bt in blocktypes])
                    ),
                    settings.DEFAULT_FROM_EMAIL,
                    [settings.SUPPORT_EMAIL],
                    fail_silently=False)
            except Exception as e:
                # send mail to tech support with Exception
                send_support_email(
                    e, __name__, "Activate blocktypes - support email"
                )
        else:
            self.stdout.write('No blocktypes matching identifiers')
            try:
                send_mail('{} Block types {} attempt failed'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                    'activation' if action == 'on' else 'deactivation'
                ),
                    'Blocktype {} command run but no blocktypes matched the '
                    'identifier(s) "{}"'.format(
                        'activation' if action == 'on' else 'deactivation',
                        ', '.join(identifiers),
                    ),
                    settings.DEFAULT_FROM_EMAIL,
                    [settings.SUPPORT_EMAIL],
                    fail_silently=False)
            except Exception as e:
                # send mail to tech support with Exception
                send_support_email(
                    e, __name__, "Activate blocktypes - support email"
                )
