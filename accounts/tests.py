from django.test import TestCase, RequestFactory, Client
from django.contrib.auth.models import User, Group
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.urlresolvers import reverse

from accounts.forms import SignupForm, DisclaimerForm
from accounts.models import PrintDisclaimer, OnlineDisclaimer
from accounts.views import ProfileUpdateView, profile, DisclaimerCreateView
from booking.tests.helpers import set_up_fb, _create_session, TestSetupMixin

from model_mommy import mommy


class SignUpFormTests(TestSetupMixin, TestCase):

    def test_signup_form(self):
        form_data = {'first_name': 'Test',
                     'last_name': 'User'}
        form = SignupForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_signup_form_with_invalid_data(self):
        # first_name must have 30 characters or fewer
        form_data = {'first_name': 'abcdefghijklmnopqrstuvwxyz12345',
                     'last_name': 'User'}
        form = SignupForm(data=form_data)
        self.assertFalse(form.is_valid())

    def test_user_assigned_from_request(self):
        user = mommy.make(User)
        url = reverse('account_signup')
        request = self.factory.get(url)
        request.user = user
        form_data = {'first_name': 'New',
                     'last_name': 'Name'}
        form = SignupForm(data=form_data)
        self.assertTrue(form.is_valid())
        form.signup(request, user)
        self.assertEquals('New', user.first_name)
        self.assertEquals('Name', user.last_name)


class DisclaimerFormTests(TestCase):

    def setUp(self):
        set_up_fb()
        self.factory = RequestFactory()

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
        form = DisclaimerForm(data=self.form_data)
        self.assertTrue(form.is_valid())

    def test_form_invalid(self):
        self.form_data['terms_accepted'] = False
        form = DisclaimerForm(data=self.form_data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'terms_accepted': [
                'You must confirm that you accept the disclaimer terms'
            ]}
        )

    def test_under_18(self):
        self.form_data['dob'] = '01 Jan 2015'
        form = DisclaimerForm(data=self.form_data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'dob': [
                'You must be over 18 years in order to register'
            ]}
        )

class ProfileUpdateViewTests(TestSetupMixin, TestCase):

    def test_invalid_date_format(self):
        self.form_data['dob'] = '32 Jan 2015'
        form = DisclaimerForm(data=self.form_data)
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
        form = DisclaimerForm(data=self.form_data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'medical_conditions_details': [
                'Please provide details of medical conditions'
            ]}
        )

    def test_joint_problems_without_details(self):
        self.form_data['joint_problems'] = True
        form = DisclaimerForm(data=self.form_data)
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
        form = DisclaimerForm(data=self.form_data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'allergies_details': [
                'Please provide details of allergies'
            ]}
        )

    def test_updating_user_data(self):
        """
        Test custom view to allow users to update their details
        """
        user = mommy.make(User, username="test_user",
                          first_name="Test",
                          last_name="User",
                          )
        url = reverse('profile:update_profile')
        request = self.factory.post(
            url, {'username': user.username,
                  'first_name': 'Fred', 'last_name': user.last_name}
        )
        request.user = user
        view = ProfileUpdateView.as_view()
        resp = view(request)
        updated_user = User.objects.get(username="test_user")
        self.assertEquals(updated_user.first_name, "Fred")


class ProfileTest(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(ProfileTest, cls).setUpTestData()
        Group.objects.get_or_create(name='instructors')

    def test_profile_view(self):
        user = mommy.make(User)
        url = reverse('profile:profile')
        request = self.factory.get(url)
        request.user = user
        resp = profile(request)

        self.assertEquals(resp.status_code, 200)


class DisclaimerCreateViewTests(TestCase):

    def setUp(self):
        set_up_fb()
        self.client = Client()
        self.factory = RequestFactory()
        self.user = mommy.make_recipe('booking.user')
        mommy.make(PrintDisclaimer, user=self.user)
        self.user_no_disclaimer = mommy.make_recipe('booking.user')

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

    def _get_response(self, user):
        url = reverse('disclaimer_form')
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        view = DisclaimerCreateView.as_view()
        return view(request)

    def _post_response(self, user, form_data):
        url = reverse('disclaimer_form')
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        view = DisclaimerCreateView.as_view()
        return view(request)

    def test_login_required(self):
        url = reverse('disclaimer_form')
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)

        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_shows_msg_if_already_has_disclaimer(self):
        resp = self._get_response(self.user)
        self.assertEqual(resp.status_code, 200)

        self.assertIn(
            "You have already completed a disclaimer.",
            str(resp.rendered_content)
        )
        self.assertNotIn("Submit", str(resp.rendered_content))

        resp = self._get_response(self.user_no_disclaimer)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(
            "You have already completed a disclaimer.",
            str(resp.rendered_content)
        )
        self.assertIn("Submit", str(resp.rendered_content))


    def test_submitting_form_without_valid_password(self):
        self.assertEqual(OnlineDisclaimer.objects.count(), 0)
        resp = self._post_response(self.user_no_disclaimer, self.form_data)
        self.assertIn(
            "Password is incorrect",
            str(resp.content)
        )

    def test_submitting_form_creates_disclaimer(self):
        self.assertEqual(OnlineDisclaimer.objects.count(), 0)
        self.user_no_disclaimer.set_password('password')
        self._post_response(self.user_no_disclaimer, self.form_data)
        self.assertEqual(OnlineDisclaimer.objects.count(), 1)

        # user now has disclaimer and can't re-access
        resp = self._get_response(self.user_no_disclaimer)
        self.assertEqual(resp.status_code, 200)

        self.assertIn(
            "You have already completed a disclaimer.",
            str(resp.rendered_content)
        )
        self.assertNotIn("Submit", str(resp.rendered_content))

        # posting same data again redirects to form
        resp = self._post_response(self.user_no_disclaimer, self.form_data)
        self.assertEqual(resp.status_code, 302)
        # no new disclaimer created
        self.assertEqual(OnlineDisclaimer.objects.count(), 1)
