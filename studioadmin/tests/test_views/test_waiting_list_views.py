from model_mommy import mommy

from django.core.urlresolvers import reverse
from django.test import TestCase
from django.contrib.messages.storage.fallback import FallbackStorage

from common.tests.helpers import _create_session
from studioadmin.views import (
    event_waiting_list_view,
)

from studioadmin.tests.test_views.helpers import TestPermissionMixin


class WaitingListViewStudioAdminTests(TestPermissionMixin, TestCase):

    def _get_response(self, user, event):
        url = reverse(
            'studioadmin:event_waiting_list', kwargs={"event_id": event.id}
        )
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return event_waiting_list_view(request, event_id=event.id)

    def _post_response(self, user, event, form_data):
        url = reverse(
            'studioadmin:event_waiting_list', kwargs={"event_id": event.id}
        )
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return event_waiting_list_view(request, event_id=event.id)

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        event = mommy.make_recipe('booking.future_PC')
        url = reverse(
            'studioadmin:event_waiting_list', kwargs={'event_id':event.id}
        )
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        event = mommy.make_recipe('booking.future_PC')
        resp = self._get_response(self.user, event)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_if_instructor(self):
        """
        test that the page can be accessed by a non staff user if in the
        instructors group
        """
        event = mommy.make_recipe('booking.future_PC')
        resp = self._get_response(self.instructor_user, event)
        self.assertEquals(resp.status_code, 200)

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        event = mommy.make_recipe('booking.future_PC')
        resp = self._get_response(self.staff_user, event)
        self.assertEquals(resp.status_code, 200)

    def test_waiting_list_users_shown(self):
        """
        Only show users on the waiting list for the relevant event
        """
        event = mommy.make_recipe('booking.future_PC')
        event1 = mommy.make_recipe('booking.future_PC')

        event_wl = mommy.make_recipe(
            'booking.waiting_list_user', event=event, _quantity=3
        )
        mommy.make_recipe(
            'booking.waiting_list_user', event=event1, _quantity=3
        )
        resp = self._get_response(self.staff_user, event)

        waiting_list_users = resp.context_data['waiting_list_users']
        self.assertEqual(set(waiting_list_users), set(event_wl))

    def test_remove_waiting_list_users(self):
        """
        Only show users on the waiting list for the relevant event
        """
        event = mommy.make_recipe('booking.future_PC')

        event_wl = mommy.make_recipe(
            'booking.waiting_list_user', event=event, _quantity=3
        )
        resp = self._get_response(self.staff_user, event)

        waiting_list_users = resp.context_data['waiting_list_users']
        self.assertEqual(len(waiting_list_users), 3)

        resp = self._post_response(
            self.staff_user, event, {'remove_user': [event_wl[0].id]}
        )
        waiting_list_users = resp.context_data['waiting_list_users']
        self.assertEqual(len(waiting_list_users), 2)
