'''
Activate/deactivate blocktypes by identifier (to be used in cronjob to turn
certain blocktypes on/off
'''

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from booking.models import Event
from booking.email_helpers import send_support_email

from activitylog.models import ActivityLog


class Command(BaseCommand):
    help = 'turn sale class prices on/off'

    def add_arguments(self, parser):
        parser.add_argument('action', nargs=1, type=str)

    def handle(self, *args, **options):
        action = options['action'][0]
        prices = {
            'on': {'pc': 6.50, 'pp': 3},
            'off': {'pc': 7.50, 'pp': 4},
        }

        pole_classes = Event.objects.filter(
            date__gt=timezone.now(),
            event_type__subtype='Pole level class'
        )
        pole_practices = Event.objects.filter(
            date__gt=timezone.now(),
            event_type__subtype='Pole practice'
        )
        for pole_class in pole_classes:
            pole_class.cost = prices[action]['pc']
            if action == 'on':
                pole_class.booking_open = True
                pole_class.payment_open = True
            pole_class.save()

        for pole_practice in pole_practices:
            pole_practice.cost = prices[action]['pp']
            if action == 'on':
                pole_practice.booking_open = True
                pole_practice.payment_open = True
            pole_practice.save()

        if pole_classes:
            message = 'Pole classes have been updated with {} prices ' \
                      '(ids {})'.format(
                'sale' if action == 'on' else 'non-sale',
                ', '.join([str(pc.id) for pc in pole_classes])
                )
            ActivityLog.objects.create(log=message)
            self.stdout.write(message)

        if pole_classes:
            message = 'Pole practices have been updated with {} prices ' \
                      '(ids {})'.format(
                'sale' if action == 'on' else 'non-sale',
                ', '.join([str(pp.id) for pp in pole_practices])
            )
            ActivityLog.objects.create(log=message)
            self.stdout.write(message)

        if pole_classes or pole_practices:
            try:
                send_mail('{} Pole classes and/or practices sale {}'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                    'activated' if action == 'on' else 'deactivated'
                ),
                    'The following pole class ids have '
                    'been {actioned}:\n{pc_ids}\n'
                    'The following pole practice ids have '
                    'been {actioned}:\n{pp_ids}'.format(
                        pc_ids=', '.join([str(pc.id) for pc in pole_classes]),
                        pp_ids=', '.join([str(pp.id) for pp in pole_practices]),
                        actioned='activated' if action == 'on' else 'deactivated',
                    ),
                    settings.DEFAULT_FROM_EMAIL,
                    [settings.SUPPORT_EMAIL],
                    fail_silently=False)
            except Exception as e:
                # send mail to tech support with Exception
                send_support_email(
                    e, __name__, "Activate class/practice sale - support email"
                )
        else:
            self.stdout.write('No classes/practices to {}'.format(
                'activate' if action == 'on' else 'deactivate')
            )
