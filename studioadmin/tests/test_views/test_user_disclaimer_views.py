from model_mommy import mommy

from django.core.urlresolvers import reverse
from django.test import TestCase
from django.contrib.messages.storage.fallback import FallbackStorage

from accounts.models import OnlineDisclaimer
from booking.tests.helpers import _create_session
from studioadmin.utils import int_str, chaffify
from studioadmin.views import (
    user_disclaimer,
    DisclaimerDeleteView,
    DisclaimerUpdateView
)
from studioadmin.tests.test_views.helpers import TestPermissionMixin


class UserDisclamersTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(UserDisclamersTests, self).setUp()
        self.user.set_password('password')
        self.user.save()
        self.disclaimer = mommy.make(
            OnlineDisclaimer, user=self.user
        )
        self.post_data = {
            'id': self.disclaimer.id,
            'name': 'test',
            'dob': '01 Jan 1990', 'address': '1 test st',
            'postcode': 'TEST1', 'home_phone': '123445', 'mobile_phone': '124566',
            'emergency_contact1_name': 'test1',
            'emergency_contact1_relationship': 'mother',
            'emergency_contact1_phone': '4547',
            'emergency_contact2_name': 'test2',
            'emergency_contact2_relationship': 'father',
            'emergency_contact2_phone': '34657',
            'medical_conditions': False, 'medical_conditions_details': '',
            'joint_problems': False, 'joint_problems_details': '',
            'allergies': False, 'allergies_details': '',
            'medical_treatment_permission': True,
            'terms_accepted': True,
            'age_over_18_confirmed': True,
            'password': 'password'
        }

    def _get_user_disclaimer(self, user, encoded_user_id):
        url = reverse('studioadmin:user_disclaimer', args=[encoded_user_id])
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return user_disclaimer(request, encoded_user_id=encoded_user_id)

    def _get_response(self, url, view, user, encoded_user_id):
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        view = view.as_view()
        return view(request, encoded_user_id=encoded_user_id)

    def _post_response(self, url, view, user, encoded_user_id, form_data):
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        view = view.as_view()
        return view(request, encoded_user_id=encoded_user_id)

    def test_only_staff_or_instructor_can_access_user_disclaimer(self):
        # no logged in user
        encoded_user_id = int_str(chaffify(self.user.id))
        resp = self.client.get(
            reverse(
                'studioadmin:user_disclaimer',
                args=[encoded_user_id]
            )
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('login'), resp.url)

        # normal user
        resp = self._get_user_disclaimer(self.user, encoded_user_id)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('booking:permission_denied'), resp.url)

        # staff user
        resp = self._get_user_disclaimer(self.staff_user, encoded_user_id)
        self.assertEqual(resp.status_code, 200)

        # instructpr user
        resp = self._get_user_disclaimer(self.instructor_user, encoded_user_id)
        self.assertEqual(resp.status_code, 200)

    def test_only_staff_can_access_update_user_disclaimer(self):
        # no logged in user
        encoded_user_id = int_str(chaffify(self.user.id))
        url = reverse(
            'studioadmin:update_user_disclaimer', args=[encoded_user_id]
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('booking:permission_denied'), resp.url)

        # normal user
        resp = self._get_response(
            url, DisclaimerUpdateView, self.user, encoded_user_id
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('booking:permission_denied'), resp.url)

        # instructor user
        resp = self._get_response(
            url, DisclaimerUpdateView, self.instructor_user, encoded_user_id
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('booking:permission_denied'), resp.url)

        # staff user
        resp = self._get_response(
            url, DisclaimerUpdateView, self.staff_user, encoded_user_id
        )
        self.assertEqual(resp.status_code, 200)

    def test_only_staff_can_access_delete_user_disclaimer(self):
        # no logged in user
        encoded_user_id = int_str(chaffify(self.user.id))
        url = reverse(
            'studioadmin:delete_user_disclaimer', args=[encoded_user_id]
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('booking:permission_denied'), resp.url)

        # normal user
        resp = self._get_response(
            url, DisclaimerUpdateView, self.user, encoded_user_id
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('booking:permission_denied'), resp.url)

        # instructor user
        resp = self._get_response(
            url, DisclaimerUpdateView, self.instructor_user, encoded_user_id
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('booking:permission_denied'), resp.url)

        # staff user
        resp = self._get_response(
            url, DisclaimerUpdateView, self.staff_user, encoded_user_id
        )
        self.assertEqual(resp.status_code, 200)

    def test_update_and_delete_buttons_not_shown_for_instructors(self):
        encoded_user_id = int_str(chaffify(self.user.id))
        update_url = reverse(
            'studioadmin:update_user_disclaimer', args=[encoded_user_id]
        )
        delete_url = reverse(
            'studioadmin:delete_user_disclaimer', args=[encoded_user_id]
        )

        resp = self._get_user_disclaimer(self.instructor_user, encoded_user_id)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('Update', resp.rendered_content)
        self.assertNotIn(update_url, resp.rendered_content)
        self.assertNotIn('Delete', resp.rendered_content)
        self.assertNotIn(delete_url, resp.rendered_content)

        resp = self._get_user_disclaimer(self.staff_user, encoded_user_id)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Update', resp.rendered_content)
        self.assertIn(update_url, resp.rendered_content)
        self.assertIn('Delete', resp.rendered_content)
        self.assertIn(delete_url, resp.rendered_content)

    def test_user_password_required_to_update_disclaimer(self):
        self.assertNotEqual(self.disclaimer.address, '1 test st')
        encoded_user_id = int_str(chaffify(self.user.id))
        update_url = reverse(
            'studioadmin:update_user_disclaimer', args=[encoded_user_id]
        )
        resp = self._post_response(
            update_url, DisclaimerUpdateView, self.staff_user, encoded_user_id,
            self.post_data
        )
        self.disclaimer.refresh_from_db()
        self.assertEqual(self.disclaimer.address, '1 test st')

    def test_update_dislaimer_sets_date_updated(self):
        self.assertIsNone(self.disclaimer.date_updated)
        encoded_user_id = int_str(chaffify(self.user.id))
        update_url = reverse(
            'studioadmin:update_user_disclaimer', args=[encoded_user_id]
        )
        resp = self._post_response(
            update_url, DisclaimerUpdateView, self.staff_user, encoded_user_id,
            self.post_data
        )
        self.disclaimer.refresh_from_db()
        self.assertIsNotNone(self.disclaimer.date_updated)

    def test_update_dislaimer(self):
        self.assertIsNone(self.disclaimer.home_phone)  # null by default
        encoded_user_id = int_str(chaffify(self.user.id))
        update_url = reverse(
            'studioadmin:update_user_disclaimer', args=[encoded_user_id]
        )
        resp = self._post_response(
            update_url, DisclaimerUpdateView, self.staff_user, encoded_user_id,
            self.post_data
        )
        self.disclaimer.refresh_from_db()
        self.assertEqual(self.disclaimer.home_phone, '123445')

    def test_delete_disclaimer(self):
        self.assertEqual(OnlineDisclaimer.objects.count(), 1)
        encoded_user_id = int_str(chaffify(self.user.id))
        delete_url = reverse(
            'studioadmin:delete_user_disclaimer', args=[encoded_user_id]
        )
        resp = self._post_response(
            delete_url, DisclaimerDeleteView, self.staff_user, encoded_user_id,
            self.post_data
        )
        self.assertEqual(OnlineDisclaimer.objects.count(), 0)
