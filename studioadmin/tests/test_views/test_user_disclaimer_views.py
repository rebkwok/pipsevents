import datetime
from unittest.mock import patch

from model_mommy import mommy

from django.urls import reverse
from django.test import TestCase
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone

from accounts.models import NonRegisteredDisclaimer, OnlineDisclaimer
from common.tests.helpers import _create_session, format_content
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
            OnlineDisclaimer, user=self.user,
            medical_conditions=False, allergies=False, joint_problems=False,
            medical_treatment_permission=True, terms_accepted=True,
            age_over_18_confirmed=True, dob=datetime.date(1990, 1, 1)
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

    def test_user_password_incorrect(self):
        encoded_user_id = int_str(chaffify(self.user.id))
        update_url = reverse(
            'studioadmin:update_user_disclaimer', args=[encoded_user_id]
        )
        self.post_data['password'] = 'password1'

        self.assertTrue(
            self.client.login(username=self.staff_user.username, password='test')
        )
        resp = self.client.post(update_url, self.post_data, follow=True)
        self.assertIn(
            'Password is incorrect', format_content(resp.rendered_content)
        )

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

    def test_get_delete_disclaimer_view(self):
        encoded_user_id = int_str(chaffify(self.user.id))
        delete_url = reverse(
            'studioadmin:delete_user_disclaimer', args=[encoded_user_id]
        )
        resp = self._get_response(
            delete_url, DisclaimerDeleteView, self.staff_user, encoded_user_id,
        )
        self.assertEqual(resp.context_data['user'], self.user)

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

    def test_no_changes_made(self):
        post_data = {
            'id': self.disclaimer.id,
            'name': self.disclaimer.name,
            'dob': self.disclaimer.dob.strftime('%d %b %Y'),
            'address': self.disclaimer.address,
            'postcode': self.disclaimer.postcode,
            'mobile_phone': self.disclaimer.mobile_phone,
            'emergency_contact1_name': self.disclaimer.emergency_contact1_name,
            'emergency_contact1_relationship': self.disclaimer.emergency_contact1_relationship,
            'emergency_contact1_phone': self.disclaimer.emergency_contact1_phone,
            'emergency_contact2_name': self.disclaimer.emergency_contact2_name,
            'emergency_contact2_relationship': self.disclaimer.emergency_contact2_relationship,
            'emergency_contact2_phone': self.disclaimer.emergency_contact2_phone,
            'medical_conditions': False,
            'medical_conditions_details': '',
            'joint_problems': False,
            'joint_problems_details': '',
            'allergies': False, 'allergies_details': '',
            'medical_treatment_permission': True,
            'terms_accepted': True,
            'age_over_18_confirmed': True,
            'password': 'password'
        }

        encoded_user_id = int_str(chaffify(self.user.id))
        update_url = reverse(
            'studioadmin:update_user_disclaimer', args=[encoded_user_id]
        )

        self.assertTrue(
            self.client.login(username=self.staff_user.username, password='test')
        )
        resp = self.client.post(update_url, post_data, follow=True)
        self.assertIn(
            'No changes made', format_content(resp.rendered_content)
        )


class NonRegisteredDisclamerViewsTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.disclaimer1 = mommy.make(
            NonRegisteredDisclaimer, first_name='Test', last_name='AUser',
            event_date=datetime.date(2019, 3, 6)
        )
        self.disclaimer2 =  mommy.make(
            NonRegisteredDisclaimer, first_name='Test', last_name='AUser1',
            event_date=datetime.date(2019, 3, 7)
        )
        self.disclaimer3 = mommy.make(
            NonRegisteredDisclaimer, first_name='Test', last_name='BUser',
            event_date=datetime.date(2019, 3, 7)
        )
        self.disclaimer4 = mommy.make(
            NonRegisteredDisclaimer, first_name='Test', last_name='CUser',
            event_date=datetime.date(2019, 3, 8)
        )
        self.url = reverse('studioadmin:event_disclaimers')

    def test_only_staff_or_instructor_can_access_user_disclaimer(self):
        # no logged in user
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('login'), resp.url)

        # normal user
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('booking:permission_denied'), resp.url)

        # staff user
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

        # instructor user
        self.client.login(username=self.instructor_user.username, password='test')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_only_future_event_dates_shown_by_default(self):
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.get(self.url)
        disclaimers = resp.context_data['disclaimers']
        self.assertEqual([disclaimer.id for disclaimer in disclaimers], [])

    @patch('studioadmin.views.disclaimers.timezone.now', return_value = datetime.datetime(2019, 3, 1, tzinfo=timezone.utc))
    def test_all_disclaimers_shown_in_reverse_event_date_order(self, mock_now):
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.get(self.url)
        disclaimers = resp.context_data['disclaimers']

        self.assertEqual(
            [disclaimer.id for disclaimer in disclaimers],
            [self.disclaimer4.id, self.disclaimer2.id, self.disclaimer3.id, self.disclaimer1.id]
        )

    @patch('studioadmin.views.disclaimers.timezone.now', return_value = datetime.datetime(2019, 3, 1, tzinfo=timezone.utc))
    def test_disclaimer_name_search(self, mock_now):
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.post(self.url, {'search_submitted': '', 'search': 'AUser'})
        disclaimers = resp.context_data['disclaimers']
        self.assertEqual(
            [disclaimer.id for disclaimer in disclaimers],
            [self.disclaimer2.id, self.disclaimer1.id]
        )

    def test_disclaimer_name_search_including_past_events(self):
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.post(self.url, {'search_submitted': '', 'search': 'AUser', 'hide_past': True})
        disclaimers = resp.context_data['disclaimers']
        self.assertEqual([disclaimer.id for disclaimer in disclaimers], [])

        resp = self.client.post(self.url, {'search_submitted': '', 'search': 'AUser'})
        disclaimers = resp.context_data['disclaimers']
        self.assertEqual(
            [disclaimer.id for disclaimer in disclaimers],
            [self.disclaimer2.id, self.disclaimer1.id]
        )

    @patch('studioadmin.views.disclaimers.timezone.now', return_value = datetime.datetime(2019, 3, 1, tzinfo=timezone.utc))
    def test_disclaimer_date_search(self, mock_now):
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.post(self.url, {'search_submitted': '', 'search_date': '07-Mar-2019'})
        disclaimers = resp.context_data['disclaimers']
        self.assertEqual(
            [disclaimer.id for disclaimer in disclaimers],
            [self.disclaimer2.id, self.disclaimer3.id]
        )

    @patch('studioadmin.views.disclaimers.timezone.now', return_value = datetime.datetime(2019, 3, 1, tzinfo=timezone.utc))
    def test_disclaimer_reset_search(self, mock_now):
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.post(self.url, {'reset': '', 'search_date': '07-Mar-2019', 'search': 'foo'})
        disclaimers = resp.context_data['disclaimers']
        self.assertEqual(
            [disclaimer.id for disclaimer in disclaimers],
            [self.disclaimer4.id, self.disclaimer2.id, self.disclaimer3.id, self.disclaimer1.id]
        )

    @patch('studioadmin.views.disclaimers.timezone.now', return_value = datetime.datetime(2019, 3, 1, tzinfo=timezone.utc))
    def test_disclaimer_search_submitted_no_search_terms(self, mock_now):
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.post(self.url, {'search_submitted': '', 'search_date': '', 'search': ''})
        disclaimers = resp.context_data['disclaimers']
        self.assertEqual(
            [disclaimer.id for disclaimer in disclaimers],
            [self.disclaimer4.id, self.disclaimer2.id, self.disclaimer3.id, self.disclaimer1.id]
        )

    def test_get_event_disclaimer_requires_login(self):
        url = reverse('studioadmin:event_disclaimer', args=[self.disclaimer1.user_uuid])
        # no logged in user
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('login'), resp.url)

        # normal user
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('booking:permission_denied'), resp.url)

        # staff user
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        # instructor user
        self.client.login(username=self.instructor_user.username, password='test')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
