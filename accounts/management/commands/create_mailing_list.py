from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, User

from booking.models import Booking


class Command(BaseCommand):

    def handle(self, *args, **options):
        group, created = Group.objects.get_or_create(name='subscribed')
        if created:  # only do this if it's the first time creating the group
            users = User.objects.all()
            added_users = 0
            for user in users:
                user_class_bookings = Booking.objects.filter(
                    status='OPEN', user=user,
                    event__event_type__event_type='CL'
                ).exists()
                if user_class_bookings:
                    group.user_set.add(user)
                    added_users += 1

            self.stdout.write(
                'Subscription group created; {} users added to group.'.format(
                    added_users
                )
            )
        else:
            self.stdout.write(
                'Subscription group already exists; mailing list has not '
                'been recreated'
            )
