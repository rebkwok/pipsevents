from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import Group, User

from booking.models import Booking


class Command(BaseCommand):

    def handle(self, *args, **options):
        group, _ = Group.objects.get_or_create(name='subscribed')
        users = User.objects.all()

        for user in users:
            user_class_bookings = Booking.objects.filter(
                status='OPEN', user=user, event__event_type='CL'
            ).exists()
            if user_class_bookings:
                group.user_set.add(user)

        self.stdout.write(
            '{} users added to subscribed group.'.format(users.count())
        )
