from datetime import date, datetime
from datetime import timezone as dt_timezone
from model_bakery import baker
import pytest

from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse

from accounts.admin import CookiePolicyAdminForm, DataPrivacyPolicyAdminForm
from accounts.forms import DataPrivacyAgreementForm, SignupForm, DisclaimerForm, NonRegisteredDisclaimerForm
from accounts.models import CookiePolicy, DataPrivacyPolicy, OnlineDisclaimer
from common.tests.helpers import assert_mailchimp_post_data, TestSetupMixin


class SignUpFormTests(TestSetupMixin, TestCase):

    def test_signup_form(self):
        form_data = {
            'first_name': 'Test',
            'last_name': 'User',
            'mailing_list': False,
            'data_privacy_confirmation' : True
        }
        form = SignupForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_signup_form_with_pronouns(self):
        form_data = {
            'first_name': 'Test',
            'last_name': 'User',
            'pronouns': "they/them",
            'mailing_list': False,
            'data_privacy_confirmation' : True
        }
        form = SignupForm(data=form_data)
        assert form.is_valid()

    def test_signup_form_with_invalid_data(self):
        # first_name must have 100 characters or fewer
        form_data = {
            'first_name': 'abcdefghijklmnopqrstuvwxyz12345' * 4,
             'last_name': 'User',
             'mailing_list': 'no',
             'data_privacy_confirmation': True
         }
        form = SignupForm(data=form_data)
        self.assertFalse(form.is_valid())

    def test_signup_mailing_list_response_required(self):
        form_data = {
            'first_name': 'Test',
            'last_name': 'User',
            'data_privacy_confirmation': True
        }
        form = SignupForm(data=form_data)
        self.assertFalse(form.is_valid())

    def test_signup_dataprotection_confirmation_required(self):
        form_data = {
            'first_name': 'Test',
            'last_name': 'User',
            'mailing_list': 'no',
            'data_privacy_confirmation': False
        }
        form = SignupForm(data=form_data)
        self.assertFalse(form.is_valid())

    def test_user_assigned_from_request(self):
        user = baker.make(User)
        url = reverse('account_signup')
        request = self.factory.get(url)
        request.user = user
        form_data = {
            'first_name': 'New',
            'last_name': 'Name',
            'mailing_list': 'no',
            'data_privacy_confirmation': True
        }
        form = SignupForm(data=form_data)
        self.assertTrue(form.is_valid())
        form.signup(request, user)
        self.assertEqual('New', user.first_name)
        self.assertEqual('Name', user.last_name)

    def test_signup_with_mailing_list(self):
        user = baker.make(User, email='test@mailinglist.com')
        url = reverse('account_signup')
        request = self.factory.get(url)
        request.user = user
        form_data = {
            'first_name': 'Test',
            'last_name': 'MailingListUser',
            'mailing_list': 'yes',
            'data_privacy_confirmation': True
        }
        form = SignupForm(data=form_data)
        self.assertTrue(form.is_valid())
        form.signup(request, user)
        assert_mailchimp_post_data(self.mock_request, user, 'subscribed')


class DisclaimerFormTests(TestSetupMixin, TestCase):

    def setUp(self):
        super(DisclaimerFormTests, self).setUp()
        self.form_data = {
            'name': 'test', 'dob': '01 Jan 1990', 'address': '1 test st',
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

    def test_disclaimer_form(self):
        form = DisclaimerForm(data=self.form_data, user=self.user)
        self.assertTrue(form.is_valid())

    def test_custom_validators(self):
        self.form_data['terms_accepted'] = False
        form = DisclaimerForm(data=self.form_data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'terms_accepted': [
                'You must confirm that you accept the disclaimer terms'
            ]}
        )

        self.form_data['terms_accepted'] = True
        self.form_data['age_over_18_confirmed'] = False

        form = DisclaimerForm(data=self.form_data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'age_over_18_confirmed': [
                'You must confirm that you are over 18'
            ]}
        )

        self.form_data['age_over_18_confirmed'] = True
        self.form_data['medical_treatment_permission'] = False
        form = DisclaimerForm(data=self.form_data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'medical_treatment_permission': [
                'You must confirm that you give permission for medical '
                'treatment in the event of an accident'
            ]}
        )

    def test_under_18(self):
        self.form_data['dob'] = '01 Jan 2015'
        form = DisclaimerForm(data=self.form_data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'dob': [
                'You must be over 18 years in order to register'
            ]}
        )

    def test_invalid_date_format(self):
        self.form_data['dob'] = '32 Jan 2015'
        form = DisclaimerForm(data=self.form_data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'dob': [
                'Invalid date format.  Select from the date picker or enter '
                'date in the format e.g. 08 Jun 1990'
            ]}
        )

    def test_medical_conditions_without_details(self):
        self.form_data['medical_conditions'] = True
        form = DisclaimerForm(data=self.form_data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'medical_conditions_details': [
                'Please provide details of medical conditions'
            ]}
        )

    def test_joint_problems_without_details(self):
        self.form_data['joint_problems'] = True
        form = DisclaimerForm(data=self.form_data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'joint_problems_details': [
                'Please provide details of knee/back/shoulder/ankle/hip/neck '
                'problems'
            ]}
        )

    def test_allergies_without_details(self):
        self.form_data['allergies'] = True
        form = DisclaimerForm(data=self.form_data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'allergies_details': [
                'Please provide details of allergies'
            ]}
        )

    def test_with_expired_disclaimer(self):
        disclaimer = baker.make(
            OnlineDisclaimer, user=self.user, name='Donald Duck',
            dob=date(2000, 10, 5), address='1 Main St',
            postcode='AB1 2CD', terms_accepted=True,
            date=datetime(2015, 2, 10, 19, 0, tzinfo=dt_timezone.utc)
        )
        self.assertFalse(disclaimer.is_active)

        form = DisclaimerForm(user=self.user)
        # initial fields set to expired disclaimer
        self.assertEqual(
            form.fields['name'].initial, 'Donald Duck'
        )
        self.assertEqual(
            form.fields['address'].initial, '1 Main St'
        )
        self.assertEqual(
            form.fields['postcode'].initial, 'AB1 2CD'
        )
        self.assertEqual(
            form.fields['dob'].initial, '05 Oct 2000'
        )

        # terms accepted NOT set to expired
        self.assertIsNone(form.fields['terms_accepted'].initial)


class NonRegisteredDisclaimerFormTests(TestSetupMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.form_data = {
            'first_name': 'test',
            'last_name': 'user',
            'email': 'test@test.com',
            'event_date': '01 Mar 2019',
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
            'confirm_name': 'test user'
        }

    def test_no_password_field(self):
        form = NonRegisteredDisclaimerForm()
        self.assertNotIn('password', form.fields)

    def test_disclaimer_form(self):
        form = NonRegisteredDisclaimerForm(data=self.form_data)
        self.assertTrue(form.is_valid())

    def test_custom_validators(self):
        self.form_data['terms_accepted'] = False
        form = NonRegisteredDisclaimerForm(data=self.form_data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'terms_accepted': [
                'You must confirm that you accept the disclaimer terms'
            ]}
        )

        self.form_data['terms_accepted'] = True
        self.form_data['age_over_18_confirmed'] = False

        form = NonRegisteredDisclaimerForm(data=self.form_data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'age_over_18_confirmed': [
                'You must confirm that you are over 18'
            ]}
        )

        self.form_data['age_over_18_confirmed'] = True
        self.form_data['medical_treatment_permission'] = False
        form = NonRegisteredDisclaimerForm(data=self.form_data,)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'medical_treatment_permission': [
                'You must confirm that you give permission for medical '
                'treatment in the event of an accident'
            ]}
        )

    def test_under_18(self):
        self.form_data['dob'] = '01 Jan 2015'
        form = NonRegisteredDisclaimerForm(data=self.form_data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'dob': [
                'You must be over 18 years in order to register'
            ]}
        )

    def test_invalid_dob_date_format(self):
        self.form_data['dob'] = '32 Jan 2015'
        form = NonRegisteredDisclaimerForm(data=self.form_data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'dob': [
                'Invalid date format.  Select from the date picker or enter '
                'date in the format e.g. 08 Jun 1990'
            ]}
        )

    def test_invalid_event_date_format(self):
        self.form_data['event_date'] = '30 January 2015'
        form = NonRegisteredDisclaimerForm(data=self.form_data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'event_date': [
                'Invalid date format.  Select from the date picker or enter '
                'date in the format e.g. 08 Jun 1990'
            ]}
        )

    def test_medical_conditions_without_details(self):
        self.form_data['medical_conditions'] = True
        form = NonRegisteredDisclaimerForm(data=self.form_data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'medical_conditions_details': [
                'Please provide details of medical conditions'
            ]}
        )

    def test_joint_problems_without_details(self):
        self.form_data['joint_problems'] = True
        form = NonRegisteredDisclaimerForm(data=self.form_data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'joint_problems_details': [
                'Please provide details of knee/back/shoulder/ankle/hip/neck '
                'problems'
            ]}
        )

    def test_allergies_without_details(self):
        self.form_data['allergies'] = True
        form = NonRegisteredDisclaimerForm(data=self.form_data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'allergies_details': [
                'Please provide details of allergies'
            ]}
        )

    def test_mismatched_confirm_name(self):
        # name must match exactly, including case
        self.form_data['confirm_name'] = 'Test user'
        form = NonRegisteredDisclaimerForm(data=self.form_data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {
                'confirm_name':
                    ['Please enter your first and last name exactly as on the form (case sensitive) to confirm.']
            }
        )

        # surrounding whitespace is ignored
        self.form_data['confirm_name'] = ' test user '
        form = NonRegisteredDisclaimerForm(data=self.form_data)
        self.assertTrue(form.is_valid())


class DataPrivacyAgreementFormTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make(User)
        baker.make(DataPrivacyPolicy)

    def test_confirm_required(self):
        form = DataPrivacyAgreementForm(
            next_url='/', data={'mailing_list': False}
        )
        self.assertFalse(form.is_valid())

        form = DataPrivacyAgreementForm(
            next_url='/', data={'confirm': True, 'mailing_list': False}
        )
        self.assertTrue(form.is_valid())


class CookiePolicyAdminFormTests(TestCase):

    def test_create_cookie_policy_version_help(self):
        form = CookiePolicyAdminForm()
        # version initial set to 1.0 for first policy
        self.assertEqual(form.fields['version'].help_text, '')
        self.assertEqual(form.fields['version'].initial, 1.0)

        baker.make(CookiePolicy, version=1.0)
        # help text added if updating
        form = CookiePolicyAdminForm()
        self.assertEqual(
            form.fields['version'].help_text,
            'Current version is 1.0.  Leave blank for next major version'
        )
        self.assertIsNone(form.fields['version'].initial)

    def test_validation_error_if_no_changes(self):
        policy = baker.make(CookiePolicy, version=1.0, content='Foo')
        form = CookiePolicyAdminForm(
            data={
                'content': 'Foo',
                'version': 1.5,
                'issue_date': policy.issue_date
            }
        )
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.non_field_errors(),
            [
                'No changes made from previous version; new version must '
                'update policy content'
            ]
        )


class DataPrivacyPolicyAdminFormTests(TestCase):

    def test_create_data_privacy_policy_version_help(self):
        form = DataPrivacyPolicyAdminForm()
        # version initial set to 1.0 for first policy
        self.assertEqual(form.fields['version'].help_text, '')
        self.assertEqual(form.fields['version'].initial, 1.0)

        baker.make(DataPrivacyPolicy, version=1.0)
        # help text added if updating
        form = DataPrivacyPolicyAdminForm()
        self.assertEqual(
            form.fields['version'].help_text,
            'Current version is 1.0.  Leave blank for next major version'
        )
        self.assertIsNone(form.fields['version'].initial)

    def test_validation_error_if_no_changes(self):
        policy = baker.make(DataPrivacyPolicy, version=1.0, content='Foo')
        form = DataPrivacyPolicyAdminForm(
            data={
                'content': 'Foo',
                'version': 1.5,
                'issue_date': policy.issue_date
            }
        )
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.non_field_errors(),
            [
                'No changes made from previous version; new version must '
                'update policy content'
            ]
        )
