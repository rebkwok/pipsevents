from urllib.parse import urlsplit, parse_qs

from model_bakery import baker

from django.urls import reverse
from django.test import TestCase
from django.contrib.messages.storage.fallback import FallbackStorage

from common.tests.helpers import create_configured_user
from studioadmin.views import (
    event_waiting_list_view,
)

from studioadmin.tests.test_views.helpers import TestPermissionMixin


class WaitingListViewStudioAdminTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = create_configured_user("test", "user@example.com", "test")
        cls.instructor_user = create_configured_user("instructor", "instructor@example.com", "test", instructor=True)
        cls.staff_user = create_configured_user("staff", "staff@example.com", "test", staff=True)

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        event = baker.make_recipe('booking.future_PC')
        url = reverse(
            'studioadmin:event_waiting_list', kwargs={'event_id':event.id}
        )
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        assert resp.status_code == 302
        assert resp.url in redirected_url

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        event = baker.make_recipe('booking.future_PC')
        self.client.force_login(self.user)
        url = reverse(
            'studioadmin:event_waiting_list', kwargs={'event_id':event.id}
        )
        resp = self.client.get(url)
        assert resp.status_code == 302
        assert resp.url == reverse('booking:permission_denied')

    def test_can_access_if_instructor(self):
        """
        test that the page can be accessed by a non staff user if in the
        instructors group
        """
        self.client.force_login(self.instructor_user)
        event = baker.make_recipe('booking.future_PC')
        url = reverse(
            'studioadmin:event_waiting_list', kwargs={'event_id':event.id}
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        self.client.force_login(self.staff_user)
        event = baker.make_recipe('booking.future_PC')
        url = reverse(
            'studioadmin:event_waiting_list', kwargs={'event_id':event.id}
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_waiting_list_users_shown(self):
        """
        Only show users on the waiting list for the relevant event
        """
        self.client.force_login(self.staff_user)
        event = baker.make_recipe('booking.future_PC')
        event1 = baker.make_recipe('booking.future_PC')

        event_wl = baker.make_recipe(
            'booking.waiting_list_user', event=event, _quantity=3
        )
        baker.make_recipe(
            'booking.waiting_list_user', event=event1, _quantity=3
        )
        url = reverse(
            'studioadmin:event_waiting_list', kwargs={'event_id':event.id}
        )
        resp = self.client.get(url)
        waiting_list_users = resp.context_data['waiting_list_users']
        self.assertEqual(set(waiting_list_users), set(event_wl))

    def test_remove_waiting_list_users(self):
        """
        Only show users on the waiting list for the relevant event
        """
        self.client.force_login(self.staff_user)
        event = baker.make_recipe('booking.future_PC')

        event_wl = baker.make_recipe(
            'booking.waiting_list_user', event=event, _quantity=3
        )
        url = reverse(
            'studioadmin:event_waiting_list', kwargs={'event_id':event.id}
        )
        resp = self.client.get(url)

        waiting_list_users = resp.context_data['waiting_list_users']
        self.assertEqual(len(waiting_list_users), 3)

        resp = self.client.post(
            url, {'remove_user': [event_wl[0].id]}
        )
        waiting_list_users = resp.context_data['waiting_list_users']
        self.assertEqual(len(waiting_list_users), 2)

    def test_email_waiting_list(self):
        self.client.force_login(self.staff_user)
        lesson = baker.make_recipe('booking.future_PC')
        event = baker.make_recipe('booking.future_EV')

        lesson_wl_user = baker.make_recipe(
            'booking.waiting_list_user', event=lesson, user__email="test@example.com"
        )
        event_wl_user = baker.make_recipe(
            'booking.waiting_list_user', event=event, user__email="test@example.com"
        )
        event_wl_user1 = baker.make_recipe(
            'booking.waiting_list_user', event=event, user__email="test1@example.com"
        )

        url = reverse(
            'studioadmin:email_waiting_list', kwargs={'event_id':event.id}
        )
        resp = self.client.get(url)
        assert resp.status_code == 302
        assert set(self.client.session['users_to_email']) == {event_wl_user.user.id, event_wl_user1.user.id}
        assert resp.url
        
        qs_dict = parse_qs(urlsplit(resp.url).query)
        assert qs_dict["events"] == [f"[{event.id}]"]
        assert qs_dict["lessons"] == ["[]"]

        url = reverse(
            'studioadmin:email_waiting_list', kwargs={'event_id':lesson.id}
        )
        resp = self.client.get(url)
        assert resp.status_code == 302
        assert set(self.client.session['users_to_email']) == {lesson_wl_user.user.id}
        qs_dict = parse_qs(urlsplit(resp.url).query)
        assert qs_dict["events"] == ["[]"]
        assert qs_dict["lessons"] == [f"[{lesson.id}]"]


class TicketedEventWaitingListViewStudioAdminTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = create_configured_user("test", "user@example.com", "test")
        cls.instructor_user = create_configured_user("instructor", "instructor@example.com", "test", instructor=True)
        cls.staff_user = create_configured_user("staff", "staff@example.com", "test", staff=True)
        cls.ticketed_event = baker.make_recipe('booking.ticketed_event_max10')
        cls.ticketed_event1 = baker.make_recipe('booking.ticketed_event_max10')
        cls.url = reverse(
            'studioadmin:ticketed_event_waiting_list_view', args=(cls.ticketed_event.slug,)
        )
        cls.email_ticketed_event_waiting_list_url = reverse(
            'studioadmin:email_ticketed_event_waiting_list', args=(cls.ticketed_event.id,)
        )

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        resp = self.client.get(self.url)
        redirected_url = reverse('account_login') + "?next={}".format(self.url)
        assert resp.status_code == 302
        assert resp.url in redirected_url

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        assert resp.status_code == 302
        assert resp.url == reverse('booking:permission_denied')

    def test_can_access_if_instructor(self):
        """
        test that the page can be accessed by a non staff user if in the
        instructors group
        """
        self.client.force_login(self.instructor_user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        self.client.force_login(self.staff_user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_waiting_list_users_shown(self):
        """
        Only show users on the waiting list for the relevant event
        """
        self.client.force_login(self.staff_user)
        event_wl = baker.make(
            'booking.TicketedEventWaitingListUser', ticketed_event=self.ticketed_event, _quantity=3
        )
        baker.make(
            'booking.TicketedEventWaitingListUser', ticketed_event=self.ticketed_event1, _quantity=3
        )
        resp = self.client.get(self.url)
        waiting_list_users = resp.context_data['waiting_list_users']
        assert set(waiting_list_users) == set(event_wl)

    def test_email_waiting_list(self):
        self.client.force_login(self.staff_user)
        event_wl_user = baker.make(
            'booking.TicketedEventWaitingListUser', ticketed_event=self.ticketed_event, user__email="test@example.com"
        )
        event_wl_user1 = baker.make(
            'booking.TicketedEventWaitingListUser', ticketed_event=self.ticketed_event, user__email="test1@example.com"
        )
        resp = self.client.get(self.email_ticketed_event_waiting_list_url)
        assert resp.status_code == 302
        assert set(self.client.session['users_to_email']) == {event_wl_user.user.id, event_wl_user1.user.id}
