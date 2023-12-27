"""
Remove specific event type permissions from students if they haven't booked any classes in the past 8 months
"""
from dateutil.relativedelta import relativedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.management.base import BaseCommand

from activitylog.models import ActivityLog
from booking.models import AllowedGroup

class Command(BaseCommand):
    help = "deactivate permissions for students who have not booked classes in past 8 months"

    def handle(self, *args, **options):
        cutoff_date = timezone.now() - relativedelta(months=8)
        allowed_groups = AllowedGroup.objects.all()

        # never deactivate superuser or staff users or specific allowed students
        users = User.objects.filter(is_superuser=False, is_staff=False).exclude(id__in=[int(user_id) for user_id in settings.REGULAR_STUDENT_WHITELIST_IDS])

        for allowed_group in allowed_groups:
            # never deactivate superuser or staff users
            for student in users:
                class_bookings = student.bookings.filter(event__event_type__event_type="CL")
                last_class_booking_date = class_bookings.latest("date_booked").date_booked if class_bookings.exists() else None

                if last_class_booking_date is None or last_class_booking_date < cutoff_date:
                    allowed_group.remove_user(student)
                    ActivityLog.objects.create(log=f"User {student.username} has been removed from allowed group {allowed_group} due to inactivity")
