"""
Remove specific event type permissions from students if they haven't booked any
classes in the past 8 months

ALSO
Add permissions for students who have booked and attended at least 10 classes
"""
from dateutil.relativedelta import relativedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.management.base import BaseCommand

from activitylog.models import ActivityLog
from booking.models import AllowedGroup, Booking
from common.management import write_command_name


class Command(BaseCommand):
    help = "deactivate permissions for students who have not booked classes in past 8 months"

    def handle(self, *args, **options):
        write_command_name(self, __file__)
        cutoff_date = timezone.now() - relativedelta(months=8)
        allowed_groups = AllowedGroup.objects.all()
        
        # check all users that are not superusers, staff users or in the ignore list
        users_to_check = User.objects.filter(
            is_superuser=False, is_staff=False,
        ).exclude(id__in=settings.ALLOWED_GROUPS_IGNORE_LIST)
        
        # users who have attended at least one relevant class within the cutoff period (8 months)
        # OR are in the ignore list
        valid_users = list(
            Booking.objects.filter(
                status="OPEN", attended=True, event__event_type__event_type="CL",
                event__date__gt=cutoff_date
            ).distinct("user").values_list("user_id", flat=True)
        )
        valid_users.extend(settings.ALLOWED_GROUPS_IGNORE_LIST)


        # Deactivate old students
        for allowed_group in allowed_groups:
            # never deactivate superuser or staff users or specific ignored students
            users_to_deactivate = allowed_group.group.user_set.filter(
                is_superuser=False, is_staff=False
            ).exclude(id__in=valid_users)
            for student in users_to_deactivate:
                allowed_group.remove_user(student)
                ActivityLog.objects.create(log=f"User {student.username} has been removed from allowed group {allowed_group} due to inactivity")

        # Activate students with at least 10 classes
        for user in users_to_check:
            user_booking_count = None
            for group_name in ["experienced", "regular student"]:
                if user_booking_count is not None and user_booking_count < 10:
                    continue
                allowed_group = AllowedGroup.objects.get(group__name=group_name)
                if not allowed_group.has_permission(user):
                    if user_booking_count is None:
                        user_booking_count = user.bookings.filter(status="OPEN", attended=True, event__date__gt=cutoff_date).count()
                        
                    if user_booking_count >= 10:
                        allowed_group.add_user(user)
                        ActivityLog.objects.create(
                            log=f"User {user.username} has been auto-added to allowed group {allowed_group}."
                        )
