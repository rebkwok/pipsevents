import datetime

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.db.utils import IntegrityError

from accounts.models import DisclaimerContent, OnlineDisclaimer
from accounts.utils import has_active_disclaimer


class Command(BaseCommand):

    def handle(self, *args, **options):

        self.stdout.write("Create superuser...")
        user, created = User.objects.get_or_create(
            username="admin",
            defaults={
                'first_name': 'Admin',
                'last_name': 'User',
                'email': 'admin@admin.com',
                'password': 'test'
            }
        )
        user.is_superuser = True
        user.is_staff = True
        user.set_password("admin")
        user.save()
        if created:
            self.stdout.write('Superuser with username "admin" created')
        else:
            self.stdout.write('Superuser with username "admin" already exists')

        self.stdout.write("Creating 5 test users")
        for i in range(1, 6):
            username = "test_{}".format(i)
            first_name = "Test"
            last_name = "User{}".format(i)
            email = "test{}@test.com".format(i)
            user, _ = User.objects.get_or_create(
                username=username, email=email, first_name=first_name,
                last_name=last_name
            )
            if not has_active_disclaimer(user):
                OnlineDisclaimer.objects.create(
                    user=user,
                    name='{} {}'.format(user.first_name, user.last_name), 
                    dob=datetime.date(1990, 1, 1), 
                    address='1 test st',
                    postcode='TEST1',
                    home_phone='123445', 
                    mobile_phone='124566',
                    emergency_contact1_name='test1',
                    emergency_contact1_relationship='mother',
                    emergency_contact1_phone='4547',
                    emergency_contact2_name='test2',
                    emergency_contact2_relationship='father',
                    emergency_contact2_phone='34657',
                    medical_conditions=False,
                    joint_problems=False,
                    allergies=False,
                    medical_treatment_permission=True,
                    terms_accepted=True,
                    age_over_18_confirmed=True,
                    version=DisclaimerContent.current_version()
                )
                self.stdout.write(
                    "Disclaimer created for user {}".format(user.username)
                )
            else:
                self.stdout.write(
                    "Disclaimer exists for user {}".format(user.username)
                )