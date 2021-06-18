'''
Find no-shows
'''
from collections import Counter
from datetime import timedelta
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from booking.models import Booking


class Command(BaseCommand):
    help = 'Find people with >1 no-show'

    def add_arguments(self, parser):
        parser.add_argument('--days', '-d', type=int, default=28)

    def handle(self, *args, **options):
        days = options["days"]
        no_shows = Booking.objects.filter(
            event__date__gte=timezone.now() - timedelta(days=days),
            event__date__lt=timezone.now(), no_show=True
        )
        no_show_users = no_shows.values_list("user", flat=True)
        counter = Counter(no_show_users)

        self.stdout.write(f"==========Users with more than 1 no show in past {days} days==========")
        for user_id, count in counter.most_common():
            if count > 1:
                user = User.objects.get(id=user_id)
                self.stdout.write(f"{count}: {user.first_name} {user.last_name} - (id {user_id})")
                bookings = no_shows.filter(user_id=user_id)
                for booking in bookings:
                    self.stdout.write(str(booking.event))
                self.stdout.write("===================")
