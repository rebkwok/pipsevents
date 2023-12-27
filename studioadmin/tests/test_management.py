from django.contrib.auth.models import Group, Permission
from django.core import management
from django.test import TestCase


from booking.models import AllowedGroup


class CreateGroupTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.expected_group_names = ['regular student', '_open to all', 'instructors']

    def test_create_groups(self):
        # created in migrations
        allowed_groups = AllowedGroup.objects.all()
        assert allowed_groups.count() == 2
        assert not Group.objects.exclude(id__in=allowed_groups).values_list("id", flat=True).exists()

        management.call_command('create_groups')
        self.assertEqual(Group.objects.count(), 3)

        group_names = Group.objects.values_list('name', flat=True)
        self.assertCountEqual(group_names, self.expected_group_names)

        instructors = Group.objects.get(name='instructors')
        perm = Permission.objects.get(codename='can_view_registers')
        self.assertIn(perm, instructors.permissions.all())

    def test_group_not_overwritten_if_already_exists(self):
        management.call_command('create_groups')
        self.assertEqual(Group.objects.count(), 3)

        group_names = Group.objects.values_list('name', flat=True)
        group_ids = Group.objects.values_list('id', flat=True)
        self.assertCountEqual(group_names, self.expected_group_names)

        management.call_command('create_groups')
        self.assertEqual(Group.objects.count(), 3)

        new_group_ids = Group.objects.values_list('id', flat=True)

        self.assertCountEqual(list(group_ids), list(new_group_ids))
