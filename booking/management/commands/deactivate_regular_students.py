"""
Remove students from regular_student group if they haven't booked classes in the past 8 months
"""
from dateutil.relativedelta import relativedelta

from django.conf import settings
from django.contrib.auth.models import Group, Permission, User
from django.utils import timezone
from django.core.management.base import BaseCommand

from activitylog.models import ActivityLog


class Command(BaseCommand):
    help = "deactivate regular student status for students who have not booked classes in past 8 months"

    def handle(self, *args, **options):
        cutoff_date = timezone.now() - relativedelta(months=8)
        regular_student_permission = Permission.objects.get(codename='is_regular_student')
        # never deactivate superuser or staff users
        regular_students = User.objects.filter(user_permissions=regular_student_permission, is_superuser=False, is_staff=False)\
            .exclude(id__in=settings.REGULAR_STUDENT_WHITELIST_IDS)
        for student in regular_students:
            class_bookings = student.bookings.filter(event__event_type__event_type="CL")\
                .exclude(event__event_type__subtype="Pole practice")
            last_class_booking_date = class_bookings.latest("date_booked").date_booked if class_bookings.exists() else None

            if last_class_booking_date is None or last_class_booking_date < cutoff_date:
                student.user_permissions.remove(regular_student_permission)
                ActivityLog.objects.create(log=f"Regular student status for user {student.username} has been removed due to inactivity")
