from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.db.utils import IntegrityError

class Command(BaseCommand):

    def handle(self, *args, **options):

        self.stdout.write("Trying to create superuser...")
        try:
            user, _ = User.objects.get_or_create(
                username="admin",
                first_name='Admin',
                last_name='User',
                email="admin@admin.com",
                password="admin"
            )
            user.is_superuser = True
            user.save()
            user.set_password("admin")
            self.stdout.write('Superuser with username "admin" created')
        except IntegrityError:
            self.stdout.write('Superuser with username "admin" already exists')

        self.stdout.write("Creating 5 test users")
        for i in range(1, 6):
            username = "test_{}".format(i)
            first_name = "Test"
            last_name = "User{}".format(i)
            email = "test{}@test.com".format(i)
            User.objects.get_or_create(
                username=username, email=email, first_name=first_name,
                last_name=last_name
            )
