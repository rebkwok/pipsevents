from django.contrib.auth.models import Group, User, Permission
from django.urls import reverse

import pytest

from model_bakery import baker

from notices.models import Notice
from booking.models import Banner

pytestmark = pytest.mark.django_db

@pytest.fixture(autouse=True)
def instructor_user(client):
    user = User.objects.create_user(username="instructor", password="test")
    group, _ = Group.objects.get_or_create(name="instructors")
    user.groups.add(group)
    client.force_login(user)
    yield user


def test_all_users_banner_get(client):
    url = reverse("studioadmin:all_users_banner")
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.context_data["form"].instance.id is None


def test_all_users_banner_get_with_existing_banner(client):
    banner = baker.make(Banner, banner_type="banner_all")
    baker.make(Banner, banner_type="banner_new")
    url = reverse("studioadmin:all_users_banner")
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.context_data["form"].instance.id == banner.id


def test_all_users_banner_post(client):
    assert not Banner.objects.exists()
    url = reverse("studioadmin:all_users_banner")
    data = {
        "content": "my banner content",
        "colour": "success",
        "banner_type": "banner_all",
        "start_datetime": "01 Jun 2023 10:00"
    }
    client.post(url, data)
    assert Banner.objects.exists()


def test_all_users_banner_post_with_existing_banner(client):
    banner = baker.make(Banner, banner_type="banner_all", content="Foo")
    url = reverse("studioadmin:all_users_banner")
    data = {
        "content": "my banner content",
        "colour": "success",
        "banner_type": "banner_new",
        "start_datetime": "01 Jun 2023 10:00"
    }
    client.post(url, data)
    banner.refresh_from_db()
    assert banner.content == "my banner content"


def test_new_users_banner_get(client):
    url = reverse("studioadmin:new_users_banner")
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.context_data["form"].instance.id is None


def test_new_users_banner_get_with_existing_banner(client):
    baker.make(Banner, banner_type="banner_all")
    new_banner = baker.make(Banner, banner_type="banner_new")
    url = reverse("studioadmin:new_users_banner")
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.context_data["form"].instance.id == new_banner.id


def test_new_users_banner_post(client):
    assert not Banner.objects.exists()
    url = reverse("studioadmin:new_users_banner")
    data = {
        "content": "my banner content",
        "colour": "success",
        "banner_type": "banner_new",
        "start_datetime": "01 Jun 2023 10:00"
    }
    client.post(url, data)
    assert Banner.objects.exists()


def test_new_users_banner_post_with_existing_banner(client):
    new_banner = baker.make(Banner, banner_type="banner_new", content="Foo")
    url = reverse("studioadmin:new_users_banner")
    data = {
        "content": "my banner content",
        "colour": "success",
        "banner_type": "banner_new",
        "start_datetime": "01 Jun 2023 10:00"
    }
    client.post(url, data)
    new_banner.refresh_from_db()
    assert new_banner.content == "my banner content"


def test_popup_notification_get(client):
    url = reverse("studioadmin:popup_notification")
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.context_data["form"].instance.id is None


def test_popup_notification_get_with_existing_notice(client):
    notice = baker.make(Notice, content="my notice")
    url = reverse("studioadmin:popup_notification")
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.context_data["form"].instance.id == notice.id


def test_popup_notification_post(client):
    assert not Notice.objects.exists()
    url = reverse("studioadmin:popup_notification")
    data = {
        "content": "my notice",
        "title": "New",
    }
    client.post(url, data)
    assert Notice.objects.exists()


def test_popup_notification_post_date_errors(client):
    assert not Notice.objects.exists()
    url = reverse("studioadmin:popup_notification")
    data = {
        "content": "my notice",
        "title": "New",
        "starts_at": "15 Jul 2023 10:00",
        "expires_at": "15 Jul 2023 08:00"
    }
    resp = client.post(url, data)
    form = resp.context_data["form"]
    assert not form.is_valid()
    assert "starts_at" in form.errors
    assert "expires_at" in form.errors
    assert not Notice.objects.exists()


def test_popup_notification_post_with_existing_notice(client):
    notice = baker.make(Notice, content="my notice")
    assert notice.version == 1
    url = reverse("studioadmin:popup_notification")
    data = {
        "content": "my notice content",
        "title": "New",
    }
    client.post(url, data)
    notice.refresh_from_db()
    assert notice.content == "my notice content"
    assert notice.version == 2


def test_popup_notification_post_with_existing_notice_no_changes(client):
    notice = baker.make(Notice, content="my notice", title="new")
    assert notice.version == 1
    url = reverse("studioadmin:popup_notification")
    data = {
        "content": "my notice",
        "title": "new",
    }
    client.post(url, data)
    notice.refresh_from_db()
    assert notice.version == 1
