from accounts.models import DisclaimerContent
from common.tests.helpers import create_configured_user


class TestPermissionMixin(object):

    @classmethod
    def setUpTestData(cls):
        cls.user = create_configured_user("test", "user@example.com", "test")
        cls.instructor_user = create_configured_user("instructor", "instructor@example.com", "test", instructor=True)
        cls.staff_user = create_configured_user("staff", "staff@example.com", "test", staff=True)

        # Make sure we have a current disclaimer content
        DisclaimerContent.objects.create(version=None)
