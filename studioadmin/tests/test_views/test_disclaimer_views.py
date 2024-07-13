import datetime
from datetime import timezone as dt_timezone

import pytest
from unittest.mock import patch

from model_bakery import baker

from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.test import TestCase

from accounts.models import DisclaimerContent, NonRegisteredDisclaimer, OnlineDisclaimer
from common.tests.helpers import format_content
from studioadmin.utils import int_str, chaffify
from studioadmin.tests.test_views.helpers import TestPermissionMixin


class UserDisclamersTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.user.set_password('password')
        self.user.save()
        self.disclaimer = baker.make(
            OnlineDisclaimer, user=self.user,
            medical_conditions=False, allergies=False, joint_problems=False,
            medical_treatment_permission=True, terms_accepted=True,
            age_over_18_confirmed=True, dob=datetime.date(1990, 1, 1),
            version=DisclaimerContent.current_version()
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
        self.client.force_login(self.staff_user)

    def _get_user_disclaimer(self, user, encoded_user_id):
        self.client.force_login(user)
        url = reverse('studioadmin:user_disclaimer', args=[encoded_user_id])
        return self.client.get(url)

    def test_only_staff_or_instructor_can_access_user_disclaimer(self):
        self.client.logout()
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

        # normal user with access to event disclaimers cannot view
        permission = Permission.objects.get(codename='view_nonregistereddisclaimer')
        self.user.user_permissions.add(permission)
        resp = self._get_user_disclaimer(self.user, encoded_user_id)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('booking:permission_denied'), resp.url) 
        self.user.user_permissions.remove(permission)

        # staff user
        resp = self._get_user_disclaimer(self.staff_user, encoded_user_id)
        self.assertEqual(resp.status_code, 200)

        # instructor user
        resp = self._get_user_disclaimer(self.instructor_user, encoded_user_id)
        self.assertEqual(resp.status_code, 200)

    def test_only_staff_or_instructor_can_access_update_user_disclaimer(self):
        # no logged in user
        self.client.logout()
        encoded_user_id = int_str(chaffify(self.user.id))
        url = reverse(
            'studioadmin:update_user_disclaimer', args=[encoded_user_id]
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('booking:permission_denied'), resp.url)

        # normal user
        self.client.login(username=self.user.username, password="test")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('booking:permission_denied'), resp.url)

        # instructor user
        self.client.login(username=self.instructor_user.username, password="test")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        # staff user
        self.client.login(username=self.staff_user.username, password="test")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_only_staff_can_access_delete_user_disclaimer(self):
        # no logged in user
        self.client.logout()
        encoded_user_id = int_str(chaffify(self.user.id))
        url = reverse(
            'studioadmin:delete_user_disclaimer', args=[encoded_user_id]
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('booking:permission_denied'), resp.url)

        # normal user
        self.client.login(username=self.user.username, password="test")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('booking:permission_denied'), resp.url)

        # instructor user
        self.client.login(username=self.instructor_user.username, password="test")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('booking:permission_denied'), resp.url)

        # staff user
        self.client.login(username=self.staff_user.username, password="test")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_delete_buttons_not_shown_for_instructors(self):
        encoded_user_id = int_str(chaffify(self.user.id))
        update_url = reverse(
            'studioadmin:update_user_disclaimer', args=[encoded_user_id]
        )
        delete_url = reverse(
            'studioadmin:delete_user_disclaimer', args=[encoded_user_id]
        )

        # instructor can see update but not delete
        resp = self._get_user_disclaimer(self.instructor_user, encoded_user_id)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Update', resp.rendered_content)
        self.assertIn(update_url, resp.rendered_content)
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
        resp = self.client.post(update_url, self.post_data)
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
        resp = self.client.post(update_url, self.post_data)
        self.disclaimer.refresh_from_db()
        self.assertIsNotNone(self.disclaimer.date_updated)

    def test_update_dislaimer(self):
        self.assertIsNone(self.disclaimer.home_phone)  # null by default
        encoded_user_id = int_str(chaffify(self.user.id))
        update_url = reverse(
            'studioadmin:update_user_disclaimer', args=[encoded_user_id]
        )
        resp = self.client.post(update_url, self.post_data)
        self.disclaimer.refresh_from_db()
        self.assertEqual(self.disclaimer.home_phone, '123445')

    def test_get_delete_disclaimer_view(self):
        encoded_user_id = int_str(chaffify(self.user.id))
        delete_url = reverse(
            'studioadmin:delete_user_disclaimer', args=[encoded_user_id]
        )
        resp = self.client.get(delete_url)
        self.assertEqual(resp.context_data['user'], self.user)

    def test_delete_disclaimer(self):
        self.assertEqual(OnlineDisclaimer.objects.count(), 1)
        encoded_user_id = int_str(chaffify(self.user.id))
        delete_url = reverse(
            'studioadmin:delete_user_disclaimer', args=[encoded_user_id]
        )
        resp = self.client.post(delete_url, self.post_data)
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

    def test_toggle_dislaimer_expiry(self):
        assert self.disclaimer.can_toggle_expiry()
        self.client.login(username=self.staff_user.username, password="test")
        encoded_user_id = int_str(chaffify(self.user.id))
        url = reverse(
            'studioadmin:expire_user_disclaimer', args=[encoded_user_id, self.disclaimer.id]
        )
        self.client.get(url)
        self.disclaimer.refresh_from_db()
        assert self.disclaimer.expired

        self.client.get(url)
        self.disclaimer.refresh_from_db()
        assert self.disclaimer.expired is False

        # can't toggle if already expired
        baker.make(DisclaimerContent, version=None)
        assert self.disclaimer.is_active is False
        assert self.disclaimer.expired is False
        assert self.disclaimer.can_toggle_expiry() is False
        self.client.get(url)
        self.disclaimer.refresh_from_db()
        assert self.disclaimer.expired is False


class NonRegisteredDisclamerViewsTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.disclaimer1 = baker.make(
            NonRegisteredDisclaimer, first_name='Test', last_name='AUser',
            event_date=datetime.date(2019, 3, 8), version=DisclaimerContent.current_version()
        )
        self.disclaimer2 =  baker.make(
            NonRegisteredDisclaimer, first_name='Test', last_name='AUser1',
            event_date=datetime.date(2019, 3, 7), version=DisclaimerContent.current_version()
        )
        self.disclaimer3 = baker.make(
            NonRegisteredDisclaimer, first_name='Test', last_name='BUser',
            event_date=datetime.date(2019, 3, 7), version=DisclaimerContent.current_version()
        )
        self.disclaimer4 = baker.make(
            NonRegisteredDisclaimer, first_name='Test', last_name='CUser',
            event_date=datetime.date(2019, 3, 6), version=DisclaimerContent.current_version()
        )
        self.url = reverse('studioadmin:event_disclaimers')

    def test_only_staff_or_instructor_can_access_event_disclaimer_list(self):
        # no logged in user
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('login'), resp.url)

        # normal user
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('booking:permission_denied'), resp.url)

        # normal user with access to event disclaimers can view
        cache.clear()
        permission = Permission.objects.get(codename='view_nonregistereddisclaimer')
        self.user.user_permissions.add(permission)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.user.user_permissions.remove(permission)

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
        self.assertEqual(resp.context_data['empty_search_message'], 'No disclaimers found.')

    @patch('studioadmin.views.disclaimers.timezone.now', return_value = datetime.datetime(2019, 3, 1, tzinfo=dt_timezone.utc))
    def test_all_disclaimers_shown_in_ascending_event_date_order(self, mock_now):
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.get(self.url)
        disclaimers = resp.context_data['disclaimers']

        self.assertEqual(
            [disclaimer.id for disclaimer in disclaimers],
            [self.disclaimer4.id, self.disclaimer2.id, self.disclaimer3.id, self.disclaimer1.id]
        )

    @patch('studioadmin.views.disclaimers.timezone.now', return_value = datetime.datetime(2019, 3, 1, tzinfo=dt_timezone.utc))
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
        self.assertEqual(
            resp.context_data['empty_search_message'],
            'No disclaimers found; you may want to try searching in past events.'
        )

        resp = self.client.post(self.url, {'search_submitted': '', 'search': 'AUser'})
        disclaimers = resp.context_data['disclaimers']
        self.assertEqual(
            [disclaimer.id for disclaimer in disclaimers],
            [self.disclaimer2.id, self.disclaimer1.id]
        )

    def test_disclaimer_date_search(self):
        # date search ignores the hide_past filter
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.post(self.url, {'search_submitted': '', 'search_date': '07-Mar-2019'})
        disclaimers = resp.context_data['disclaimers']
        self.assertEqual(
            [disclaimer.id for disclaimer in disclaimers],
            [self.disclaimer2.id, self.disclaimer3.id]
        )

    @patch('studioadmin.views.disclaimers.timezone.now', return_value = datetime.datetime(2019, 3, 1, tzinfo=dt_timezone.utc))
    def test_disclaimer_reset_search(self, mock_now):
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.post(self.url, {'reset': '', 'search_date': '07-Mar-2019', 'search': 'foo'})
        disclaimers = resp.context_data['disclaimers']
        self.assertEqual(
            [disclaimer.id for disclaimer in disclaimers],
            [self.disclaimer4.id, self.disclaimer2.id, self.disclaimer3.id, self.disclaimer1.id]
        )

    @patch('studioadmin.views.disclaimers.timezone.now', return_value = datetime.datetime(2019, 3, 1, tzinfo=dt_timezone.utc))
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

        # normal user with access to event disclaimers can view
        cache.clear()
        permission = Permission.objects.get(codename='view_nonregistereddisclaimer')
        self.user.user_permissions.add(permission)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.user.user_permissions.remove(permission)

        # staff user
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        # instructor user
        self.client.login(username=self.instructor_user.username, password='test')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)


class DisclamerContentListViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.list_url = reverse('studioadmin:disclaimer_content_list')
        self.client.login(username=self.staff_user.username, password='test')

    def test_only_staff_can_access_disclaimer_content(self):
        self.client.logout()

        # no logged in user
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('login'), resp.url)

        # normal user
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('booking:permission_denied'), resp.url)

        # instructor user
        self.client.login(username=self.instructor_user.username, password='test')
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, 302)

        # staff user
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, 200)

    def test_edit_button_only_shown_for_draft(self):
        content = baker.make(DisclaimerContent, version=None)
        assert content.status == 'published'

        resp = self.client.get(self.list_url)
        assert 'id="edit-button-' not in resp.rendered_content

        draft = baker.make(DisclaimerContent, is_draft=True, version=None)
        resp = self.client.get(self.list_url)
        assert f'id="edit-button-{draft.version}' in resp.rendered_content
        assert resp.context_data['current_version'] == content.version


class DisclamerContentViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super().setUp()
        content = baker.make(DisclaimerContent, version=None)
        self.url = reverse('studioadmin:disclaimer_content_view', args=(content.version,))
        self.client.login(username=self.staff_user.username, password='test')

    def test_only_staff_can_access_disclaimer_content(self):
        self.client.logout()

        # no logged in user
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('login'), resp.url)

        # normal user
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('booking:permission_denied'), resp.url)

        # instructor user
        self.client.login(username=self.instructor_user.username, password='test')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)

        # staff user
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)


class DisclamerContentCreateViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.url = reverse('studioadmin:disclaimer_content_new')
        self.client.login(username=self.staff_user.username, password='test')

    def form_data(self):
        return {
            'disclaimer_terms': 'test terms',
            'medical_treatment_terms': 'ok',
            'over_18_statement': 'Indeed I am',
            'version': '',
        }

    def test_only_staff_can_access_disclaimer_content(self):
        self.client.logout()

        # no logged in user
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('login'), resp.url)

        # normal user
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('booking:permission_denied'), resp.url)

        # instructor user
        self.client.login(username=self.instructor_user.username, password='test')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)

        # staff user
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_revert_button_not_shown(self):
        resp = self.client.get(self.url)
        assert 'id="reset_button"' not in resp.rendered_content

    def test_save_as_draft(self):
        data = self.form_data()
        data['save_draft'] = ''
        self.client.post(self.url, data)
        latest_content = DisclaimerContent.objects.latest('id')
        assert latest_content.disclaimer_terms == "test terms"
        assert latest_content.is_draft is True

    def test_publish(self):
        data = self.form_data()
        data['publish'] = ''
        self.client.post(self.url, data)
        latest_content = DisclaimerContent.objects.latest('id')
        assert latest_content.disclaimer_terms == "test terms"
        assert latest_content.is_draft is False

    def test_redirect_to_edit_latest_draft(self):
        draft = baker.make(DisclaimerContent, is_draft=True, version=None)
        resp = self.client.get(self.url)
        assert resp.status_code == 302
        assert resp.url == reverse('studioadmin:disclaimer_content_edit', args=(draft.version,))

    def test_unknown_action(self):
        data = self.form_data()
        with pytest.raises(ValidationError):
            self.client.post(self.url, data)


class DisclamerContentUpdateViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super().setUp()

        self.current = baker.make(
            DisclaimerContent,
            disclaimer_terms='current terms',
            medical_treatment_terms='current medical terms',
            over_18_statement='current statement',
            version=None
        )

        self.content = baker.make(
            DisclaimerContent,
            disclaimer_terms='draft terms',
            medical_treatment_terms='draft medical terms',
            over_18_statement='test',
            is_draft=True,
            issue_date=datetime.datetime(2020, 1, 1, tzinfo=dt_timezone.utc),
            version=None
        )
        self.url = reverse('studioadmin:disclaimer_content_edit', args=(self.content.version,))
        self.client.login(username=self.staff_user.username, password='test')

    def form_data(self):
        return {
            'disclaimer_terms': 'test terms',
            'medical_treatment_terms': 'ok',
            'over_18_statement': 'Indeed I am',
            'version': self.content.version,
        }

    def test_only_staff_can_access(self):
        self.client.logout()

        # no logged in user
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('login'), resp.url)

        # normal user
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('booking:permission_denied'), resp.url)

        # instructor user
        self.client.login(username=self.instructor_user.username, password='test')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)

        # staff user
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_save_as_draft(self):
        data = self.form_data()
        data['save_draft'] = ''
        pre_save_version = self.content.version
        self.client.post(self.url, data)
        self.content.refresh_from_db()
        assert self.content.disclaimer_terms == "test terms"
        assert self.content.is_draft is True
        assert self.content.version == pre_save_version

    def test_revert_button_shown_if_terms_differ_to_current_published(self):
        resp = self.client.get(self.url)
        assert 'id="reset_button"' in resp.rendered_content

    def test_revert_to_current_terms(self):
        data = self.form_data()
        data['version'] = self.content.version
        data['disclaimer_terms'] = 'terms that will be ignored'

        assert self.content.disclaimer_terms != self.current.disclaimer_terms
        assert self.content.medical_treatment_terms != self.current.medical_treatment_terms
        assert self.content.over_18_statement != self.current.over_18_statement
        data['reset'] = ''
        self.client.post(self.url, data)
        self.content.refresh_from_db()
        assert self.content.disclaimer_terms == self.current.disclaimer_terms
        assert self.content.medical_treatment_terms == self.current.medical_treatment_terms
        assert self.content.over_18_statement == self.current.over_18_statement
        assert self.content.version != self.current.version

        # Since the terms are now the same, the reset button is hidden
        resp = self.client.get(self.url)
        assert 'id="reset_button"' not in resp.rendered_content

    def test_publish(self):
        # version is draft = sets is_draft = False
        # issue_date is updated when changing draft to published
        data = {
            'disclaimer_terms': self.content.disclaimer_terms,
            'medical_treatment_terms': self.content.medical_treatment_terms,
            'over_18_statement': self.content.over_18_statement,
            'version': self.content.version,
            'publish': ''
        }
        issue_date_pre_publish = self.content.issue_date
        self.client.post(self.url, data)
        self.content.refresh_from_db()
        assert self.content.status == 'published'
        assert self.content.issue_date > issue_date_pre_publish

    def test_unknown_action(self):
        data = self.form_data()
        with pytest.raises(ValidationError):
            self.client.post(self.url, data)

