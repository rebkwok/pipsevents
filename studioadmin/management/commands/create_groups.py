from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission


class Command(BaseCommand):

    def handle(self, *args, **options):

        self.stdout.write("Creating group 'instructors'...")

        group, new = Group.objects.get_or_create(name="instructors")

        if new:
            self.stdout.write("Group 'instructors' created")
        else:
            self.stdout.write("Group 'instructors' already exists")

        perm = Permission.objects.get(codename="can_view_registers")
        group.permissions.add(perm)