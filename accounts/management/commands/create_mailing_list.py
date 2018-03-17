from django.conf import settings
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, User

from mailchimp3 import MailChimp


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument(
            '--recreate', action='store_true',
            help='Force recreation of mailing list from Mailchimp'
        )

    def handle(self, *args, **options):
        if options.get('recreate'):
            Group.objects.filter(name='subscribed').delete()

        group, created = Group.objects.get_or_create(name='subscribed')

        if created:
            client = MailChimp(
                settings.MAILCHIMP_USER, settings.MAILCHIMP_SECRET, timeout=20
            )
            mailchimp_members = client.lists.members.all(
                settings.MAILCHIMP_LIST_ID,
                fields="members.email_address,members.status"
            )
            subscribed = []
            for member in mailchimp_members['members']:
                if member['status'] == 'subscribed':
                    subscribed.append(member['email_address'])

            users = User.objects.filter(email__in=subscribed)
            for user in users:
                group.user_set.add(user)

            self.stdout.write(
                'Subscription group created; {} users added from Mailchimp '
                'data'.format(len(users))
            )

        else:
            self.stdout.write(
                'Subscription group already exists; mailing list has not '
                'been recreated'
            )
