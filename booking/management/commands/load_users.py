from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.db.utils import IntegrityError

class Command(BaseCommand):

    def handle(self, *args, **options):

        self.stdout.write("Trying to create superuser...")
        try:
            user, _ = User.objects.get_or_create(
                username="admin",
                email="admin@admin.com",
                password="admin"
            )
            user.is_superuser = True
            user.save()
            self.stdout.write('Superuser with username "admin" created')
        except IntegrityError:
            self.stdout.write('Superuser with username "admin" already exists')

        self.stdout.write("Creating 5 test users")
        for i in range(1, 6):
            username = "test_{}".format(i)
            first_name = "Test"
            last_name = "User{}".format(i)
            email = "test{}@test.com".format(i)
            User.objects.get_or_create(username=username,
                                       email=email,
                                       )
