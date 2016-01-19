from model_mommy import mommy

from django.test import RequestFactory
from django.test.client import Client
from django.contrib.auth.models import Permission, Group, User

from booking.tests.helpers import set_up_fb


class TestPermissionMixin(object):

    def setUp(self):
        set_up_fb()
        self.client = Client()
        self.factory = RequestFactory()
        self.user = mommy.make_recipe('booking.user')
        self.staff_user = User.objects.create_user(
            username='testuser', email='test@test.com', password='test'
        )
        self.staff_user.is_staff = True
        self.staff_user.save()
        self.instructor_user = mommy.make_recipe('booking.user')
        perm = Permission.objects.get(codename="can_view_registers")
        group, _ = Group.objects.get_or_create(name="instructors")
        group.permissions.add(perm)
        self.instructor_user.groups.add(group)

