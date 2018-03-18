from datetime import date, datetime, timedelta
from model_mommy import mommy

from django.test import TestCase, override_settings
from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.utils import timezone

from accounts.forms import SignupForm, DisclaimerForm
from accounts.models import OnlineDisclaimer
from common.tests.helpers import TestSetupMixin


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

    def test_signup_form_with_invalid_data(self):
        # first_name must have 30 characters or fewer
        form_data = {
            'first_name': 'abcdefghijklmnopqrstuvwxyz12345',
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
        # first_name must have 30 characters or fewer
        form_data = {
            'first_name': 'Test',
            'last_name': 'User',
            'mailing_list': 'no',
            'data_privacy_confirmation': False
        }
        form = SignupForm(data=form_data)
        self.assertFalse(form.is_valid())

    def test_user_assigned_from_request(self):
        user = mommy.make(User)
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
        self.assertEquals('New', user.first_name)
        self.assertEquals('Name', user.last_name)


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
        disclaimer = mommy.make(
            OnlineDisclaimer, user=self.user, name='Donald Duck',
            dob=date(2000, 10, 5), address='1 Main St',
            postcode='AB1 2CD', terms_accepted=True,
            date=datetime(2015, 2, 10, 19, 0, tzinfo=timezone.utc)
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
