'''
Find no-shows
'''
from calendar import monthrange
from collections import Counter
from datetime import timedelta
from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from booking.models import Booking


class Command(BaseCommand):
    help = 'Find people with >2 no-shows'

    def add_arguments(self, parser):
        today = timezone.now().date()
        num_days = monthrange(today.year, today.month)[1]
        parser.add_argument('--days', '-d', type=int, default=num_days)

    def handle(self, *args, **options):
        days = options["days"]
        no_shows = Booking.objects.filter(
            event__date__gte=timezone.now() - timedelta(days=days),
            event__date__lt=timezone.now(), no_show=True
        )
        no_show_users = no_shows.values_list("user", flat=True)
        counter = Counter(no_show_users)

        header_message = f"==========Users with more than 2 no shows in past {days} days=========="
        email_message = [f"Date run: {timezone.now().strftime('%d %b %Y, %H:%M')} UTC"]
        self.stdout.write(header_message)
        repeat_no_shows = [
            (user_id, count) for (user_id, count) in counter.most_common() if count > 2
        ]
        if repeat_no_shows:
            email_message.append(header_message)
        else:
            email_message.append("No repeated no-shows found")

        for user_id, count in repeat_no_shows:
            user = User.objects.get(id=user_id)
            user_message = f"{count}: {user.first_name} {user.last_name} - (id {user_id})"
            self.stdout.write(user_message)
            email_message.append(user_message)
            bookings = no_shows.filter(user_id=user_id)
            for booking in bookings:
                booking_message = str(booking.event)
                self.stdout.write(booking_message)
                email_message.append(booking_message)
            self.stdout.write("===================")
            email_message.append("===================")

        send_mail(
            f'{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Repeated No-Shows',
            "\n".join(email_message),
            settings.DEFAULT_FROM_EMAIL,
            [settings.SUPPORT_EMAIL],
            fail_silently=False
        )
