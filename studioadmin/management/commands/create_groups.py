from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission


class Command(BaseCommand):

    def handle(self, *args, **options):

        groups = ['instructors']
        for group in groups:
            self.stdout.write("Creating group {}...".format(group))
            _, created = Group.objects.get_or_create(name=group)
            if created:
                self.stdout.write("created")
            else:
                self.stdout.write("already exists")

        instructors = Group.objects.get(name='instructors')
        perm = Permission.objects.get(codename="can_view_registers")
        instructors.permissions.add(perm)
