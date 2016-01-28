from django.contrib.auth.models import Group, Permission
from django.core import management
from django.test import TestCase


class CreateGroupTests(TestCase):

    def test_create_groups(self):
        self.assertFalse(Group.objects.exists())
        management.call_command('create_groups')
        self.assertEqual(Group.objects.count(), 1)
        self.assertEqual(Group.objects.first().name, 'instructors')
        group = Group.objects.first()
        perm = Permission.objects.get(codename='can_view_registers')
        self.assertIn(perm, group.permissions.all())

    def test_group_not_overwritten_if_already_exists(self):
        management.call_command('create_groups')
        self.assertEqual(Group.objects.count(), 1)
        group = Group.objects.first()
        self.assertEqual(group.name, 'instructors')

        management.call_command('create_groups')
        self.assertEqual(Group.objects.count(), 1)
        group1 = Group.objects.first()
        self.assertEqual(group.name, 'instructors')
        self.assertEqual(group.id, group1.id)

