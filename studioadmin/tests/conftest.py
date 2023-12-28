from django.contrib.auth.models import Group, User
import pytest


@pytest.fixture
def staff_user():
    staff_user = User.objects.create_user(
        username='testuser', email='test@test.com', password='test'
    )
    staff_user.is_staff = True
    staff_user.save()
    yield staff_user


@pytest.fixture(autouse=True)
def instructor_user(client):
    user = User.objects.create_user(username="instructor", password="test")
    group, _ = Group.objects.get_or_create(name="instructors")
    user.groups.add(group)
    yield user
