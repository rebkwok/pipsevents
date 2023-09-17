from django.contrib.auth.models import User
import pytest


@pytest.fixture
def staff_user():
    staff_user = User.objects.create_user(
        username='testuser', email='test@test.com', password='test'
    )
    staff_user.is_staff = True
    staff_user.save()
    yield staff_user
