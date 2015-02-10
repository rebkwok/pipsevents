import random
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from booking.models import Event, Booking

EVENTS = Event.objects.all()
USERS = list(User.objects.all())

class Command(BaseCommand):

    def handle(self, *args, **options):

        self.stdout.write('Creating bookings')

        for event in EVENTS:
            users = random.sample(USERS, 3)
            Booking.objects.get_or_create(
                user=users[0],
                event=event
            )
            Booking.objects.get_or_create(
                user=users[1],
                event=event
            )
            Booking.objects.get_or_create(
                user=users[2],
                event=event
            )