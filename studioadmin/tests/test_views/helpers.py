from unittest.mock import Mock, patch

from django.test import RequestFactory
from django.contrib.auth.models import Permission, Group, User

from accounts.models import DisclaimerContent
from common.tests.helpers import set_up_fb


class TestPermissionMixin(object):

    def setUp(self):
        set_up_fb()
        self.factory = RequestFactory()
        self.user =User.objects.create_user(
            username='testnonstaffuser', email='nonstaff@test.com',
            password='test'
        )
        self.staff_user = User.objects.create_user(
            username='testuser', email='test@test.com', password='test'
        )
        self.staff_user.is_staff = True
        self.staff_user.save()
        self.instructor_user = User.objects.create_user(
            username='testinstructoruser', email='instructor@test.com',
            password='test'
        )
        perm = Permission.objects.get(codename="can_view_registers")
        group, _ = Group.objects.get_or_create(name="instructors")
        group.permissions.add(perm)
        self.instructor_user.groups.add(group)

        # Make sure we have a current disclaimer content
        DisclaimerContent.objects.create(version=None)

        mockresponse = Mock()
        mockresponse.status_code = 200
        self.patcher = patch('requests.request', return_value = mockresponse)
        self.mock_request = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
