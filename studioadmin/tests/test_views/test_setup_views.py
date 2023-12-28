from django.contrib.auth.models import Group, User, Permission
from django.urls import reverse

import pytest

from model_bakery import baker

from notices.models import Notice
from booking.models import AllowedGroup

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def cleanup_groups():
    AllowedGroup.objects.all().delete()
    yield
    AllowedGroup.objects.all().delete()
    

def test_event_types_list_staff_only(client, staff_user, instructor_user):
    url = reverse("studioadmin:setup_event_types")

    client.force_login(instructor_user)
    resp = client.get(url)
    assert resp.status_code == 302

    client.force_login(staff_user)
    resp = client.get(url)
    assert resp.status_code == 200


def test_event_types_list(client, staff_user):
    url = reverse("studioadmin:setup_event_types")

    baker.make_recipe("booking.event_type_PC")
    baker.make_recipe("booking.event_type_PP")

    client.force_login(staff_user)
    resp = client.get(url)
    assert resp.context_data["sidenav_selection"] == "event_types"

    # PP has Regular Student group, PC has default group
    assert "Open To All" in resp.rendered_content
    assert "Regular Student" in resp.rendered_content


def test_allowed_groups_list_staff_only(client, staff_user, instructor_user):
    url = reverse("studioadmin:setup_allowed_groups")

    client.force_login(instructor_user)
    resp = client.get(url)
    assert resp.status_code == 302

    client.force_login(staff_user)
    resp = client.get(url)
    assert resp.status_code == 200


def test_allowed_groups_list(client, staff_user):
    url = reverse("studioadmin:setup_allowed_groups")

    baker.make_recipe("booking.event_type_PC")
    baker.make_recipe("booking.event_type_WS")
    baker.make_recipe("booking.event_type_PP")

    client.force_login(staff_user)
    resp = client.get(url)
    assert resp.context_data["sidenav_selection"] == "allowed_groups"
    assert len(resp.context_data["allowed_groups"]) == 2