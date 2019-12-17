import random
from django.core import management
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from booking.models import Event, Booking


class Command(BaseCommand):

    def handle(self, *args, **options):
        EVENTS = Event.objects.all()
        users = list(User.objects.all())
        if len(users) < 3:
            self.stdout.write('Not enough users in system yet.  Creating users.')
            management.call_command('load_users')
            users = list(User.objects.all())

        if not EVENTS:
            self.stdout.write('There are no test events set up yet.  '
                              'No bookings will be created.\nRun create_events '
                              'to set up test events.')
        else:
            self.stdout.write('Creating bookings')

            for event in EVENTS:
                sampled_users = random.sample(users, min(3, event.max_participants or 3))
                for user in sampled_users:
                    Booking.objects.get_or_create(
                        user=user,
                        event=event
                    )
