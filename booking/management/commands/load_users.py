from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User


class Command(BaseCommand):

    def handle(self, *args, **options):

        self.stdout.write("Creating 5 test users and 1 staff user")
        for i in range(1, 6):
            username = "test_{}".format(i)
            email="test{}@test.com".format(i)
            User.objects.get_or_create(username=username,
                                       email=email,
                                       )

        staff, _ = User.objects.get_or_create(username='staff',
                                       email='staff@test.com',
                                       password='password123')
        staff.is_staff = True
        staff.save()