import csv
import os

from datetime import date, datetime, timedelta
from mock import Mock, patch
from model_mommy import mommy

from django.conf import settings
from django.core import management, mail
from django.test import TestCase, RequestFactory, Client, override_settings
from django.contrib.auth.models import User, Group
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.urlresolvers import reverse
from django.utils import timezone

from allauth.account.models import EmailAddress

from activitylog.models import ActivityLog
from accounts.forms import SignupForm, DisclaimerForm
from accounts.management.commands.import_disclaimer_data import logger as \
    import_disclaimer_data_logger
from accounts.management.commands.export_encrypted_disclaimers import EmailMessage
from accounts.models import PrintDisclaimer, OnlineDisclaimer, \
    DISCLAIMER_TERMS, MEDICAL_TREATMENT_TERMS, OVER_18_TERMS
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


class DisclaimerFormTests(TestSetupMixin, TestCase):

    def setUp(self):
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


class ProfileUpdateViewTests(TestSetupMixin, TestCase):

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
        cls.user_with_online_disclaimer = mommy.make_recipe('booking.user')
        mommy.make(OnlineDisclaimer, user=cls.user_with_online_disclaimer)
        cls.user_no_disclaimer = mommy.make_recipe('booking.user')

    def _get_response(self, user):
        url = reverse('profile:profile')
        request = self.factory.get(url)
        request.user = user
        return profile(request)

    def test_profile_view(self):
        resp = self._get_response(self.user)
        self.assertEquals(resp.status_code, 200)

    def test_profile_view_shows_disclaimer_info(self):
        resp = self._get_response(self.user)
        self.assertIn("Completed", str(resp.content))
        self.assertNotIn("Not completed", str(resp.content))
        self.assertNotIn("/accounts/disclaimer", str(resp.content))

        resp = self._get_response(self.user_with_online_disclaimer)
        self.assertIn("Completed", str(resp.content))
        self.assertNotIn("Not completed", str(resp.content))
        self.assertNotIn("/accounts/disclaimer", str(resp.content))

        resp = self._get_response(self.user_no_disclaimer)
        self.assertIn("Not completed", str(resp.content))
        self.assertIn("/accounts/disclaimer", str(resp.content))


class CustomLoginViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(CustomLoginViewTests, cls).setUpTestData()
        cls.user = User.objects.create(username='test_user', is_active=True)
        cls.user.set_password('password')
        cls.user.save()
        EmailAddress.objects.create(user=cls.user,
                                    email='test@gmail.com',
                                    primary=True,
                                    verified=True)

    def test_get_login_view(self):
        resp = self.client.get(reverse('login'))
        self.assertEqual(resp.status_code, 200)

    def test_post_login(self):
        resp = self.client.post(
            reverse('login'),
            {'login': self.user.username, 'password': 'password'}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('profile:profile'), resp.url)


class DisclaimerModelTests(TestCase):

    def test_online_disclaimer_str(self,):
        user = mommy.make_recipe('booking.user', username='testuser')
        field = OnlineDisclaimer._meta.get_field('date')
        mock_now = lambda: datetime(2015, 2, 10, 19, 0, tzinfo=timezone.utc)
        with patch.object(field, 'default', new=mock_now):
            disclaimer = mommy.make(OnlineDisclaimer, user=user)
            self.assertEqual(str(disclaimer), 'testuser - 10 Feb 2015, 19:00')

    def test_print_disclaimer_str(self):
        user = mommy.make_recipe('booking.user', username='testuser')
        field = PrintDisclaimer._meta.get_field('date')
        mock_now = lambda: datetime(2015, 2, 10, 19, 0, tzinfo=timezone.utc)
        with patch.object(field, 'default', new=mock_now):
            disclaimer = mommy.make(PrintDisclaimer, user=user)
            self.assertEqual(str(disclaimer), 'testuser - 10 Feb 2015, 19:00')

    def test_default_terms_set_on_new_online_disclaimer(self):
        disclaimer = mommy.make(
            OnlineDisclaimer, disclaimer_terms="foo", over_18_statement="bar",
            medical_treatment_terms="foobar"
        )
        self.assertEqual(disclaimer.disclaimer_terms, DISCLAIMER_TERMS)
        self.assertEqual(disclaimer.medical_treatment_terms, MEDICAL_TREATMENT_TERMS)
        self.assertEqual(disclaimer.over_18_statement, OVER_18_TERMS)

    def test_cannot_update_terms_after_first_save(self):
        disclaimer = mommy.make(OnlineDisclaimer)
        self.assertEqual(disclaimer.disclaimer_terms, DISCLAIMER_TERMS)
        self.assertEqual(disclaimer.medical_treatment_terms, MEDICAL_TREATMENT_TERMS)
        self.assertEqual(disclaimer.over_18_statement, OVER_18_TERMS)

        with self.assertRaises(ValueError):
            disclaimer.disclaimer_terms = 'foo'
            disclaimer.save()

        with self.assertRaises(ValueError):
            disclaimer.medical_treatment_terms = 'foo'
            disclaimer.save()

        with self.assertRaises(ValueError):
            disclaimer.over_18_statement = 'foo'
            disclaimer.save()


class DisclaimerCreateViewTests(TestSetupMixin, TestCase):

    def setUp(self):
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
        self.user_no_disclaimer.set_password('test_password')
        self.user_no_disclaimer.save()

        self.assertTrue(self.user_no_disclaimer.has_usable_password())
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


    def test_message_shown_if_no_usable_password(self):
        user = mommy.make_recipe('booking.user')
        user.set_unusable_password()
        user.save()

        resp = self._get_response(user)
        self.assertIn(
            "You need to set a password on your account in order to complete "
            "the disclaimer.",
            resp.rendered_content
        )

    def test_cannot_complete_disclaimer_without_usable_password(self):
        self.assertEqual(OnlineDisclaimer.objects.count(), 0)
        user = mommy.make_recipe('booking.user')
        user.set_unusable_password()
        user.save()

        resp = self._post_response(user, self.form_data)
        self.assertIn(
            "No password set on account.",
            str(resp.content)
        )
        self.assertEqual(OnlineDisclaimer.objects.count(), 0)

        user.set_password('password')
        user.save()
        self._post_response(user, self.form_data)
        self.assertEqual(OnlineDisclaimer.objects.count(), 1)


class DataProtectionViewTests(TestSetupMixin, TestCase):

    def test_get_data_protection_view(self):
        # no need to be a logged in user to access
        resp = self.client.get(reverse('data_protection'))
        self.assertEqual(resp.status_code, 200)


class DeleteExpiredDisclaimersTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user_online_only = mommy.make_recipe('booking.user')
        mommy.make(
            OnlineDisclaimer, user=cls.user_online_only,
            date=timezone.now()-timedelta(370)
        )
        cls.user_print_only = mommy.make_recipe('booking.user')
        mommy.make(
            PrintDisclaimer, user=cls.user_print_only,
            date=timezone.now()-timedelta(370)
        )
        cls.user_both = mommy.make_recipe('booking.user')
        mommy.make(
            OnlineDisclaimer, user=cls.user_both,
            date=timezone.now()-timedelta(370)
        )
        mommy.make(
            PrintDisclaimer, user=cls.user_both,
            date=timezone.now()-timedelta(370)
        )

    def test_disclaimers_deleted_if_no_bookings_in_past_year(self):
        self.assertEqual(OnlineDisclaimer.objects.count(), 2)
        self.assertEqual(PrintDisclaimer.objects.count(), 2)

        management.call_command('delete_expired_disclaimers')
        self.assertEqual(OnlineDisclaimer.objects.count(), 0)
        self.assertEqual(PrintDisclaimer.objects.count(), 0)

    def test_disclaimers_deleted_if_no_paid_booking_in_past_year(self):
        self.assertEqual(OnlineDisclaimer.objects.count(), 2)
        self.assertEqual(PrintDisclaimer.objects.count(), 2)

        # make one paid booking for self.user_online_only in past 365 days; this
        # user's disclaimer should not be deleted
        mommy.make_recipe(
            'booking.booking',
            user=self.user_online_only,
            event__date=timezone.now()-timedelta(360),
            paid=True
        )
        management.call_command('delete_expired_disclaimers')
        self.assertEqual(OnlineDisclaimer.objects.count(), 1)
        self.assertEqual(PrintDisclaimer.objects.count(), 0)
        self.assertEqual(
            OnlineDisclaimer.objects.first().user, self.user_online_only
        )

    def test_disclaimers_deleted_if_only_unpaid_booking_in_past_year(self):
        self.assertEqual(OnlineDisclaimer.objects.count(), 2)
        self.assertEqual(PrintDisclaimer.objects.count(), 2)

        # make one unpaid booking for self.user_online_only in past 365 days; this
        # user's disclaimer should still be deleted because unpaid
        mommy.make_recipe(
            'booking.booking',
            user=self.user_online_only,
            event__date=timezone.now()-timedelta(360),
            paid=False
        )
        management.call_command('delete_expired_disclaimers')
        self.assertEqual(OnlineDisclaimer.objects.count(), 0)
        self.assertEqual(PrintDisclaimer.objects.count(), 0)

    def test_both_print_and_online_disclaimers_deleted(self):
        self.assertEqual(OnlineDisclaimer.objects.count(), 2)
        self.assertEqual(PrintDisclaimer.objects.count(), 2)

        # make one paid booking for self.user_both in past 365 days; both other
        # disclaimers should be deleted because unpaid
        mommy.make_recipe(
            'booking.booking',
            user=self.user_both,
            event__date=timezone.now()-timedelta(360),
            paid=True
        )
        management.call_command('delete_expired_disclaimers')
        self.assertEqual(OnlineDisclaimer.objects.count(), 1)
        self.assertEqual(PrintDisclaimer.objects.count(), 1)

    def test_disclaimers_not_deleted_if_created_in_past_year(self):
        # make a user with a disclaimer created today
        user = mommy.make_recipe('booking.user')
        mommy.make(OnlineDisclaimer, user=user)

        self.assertEqual(OnlineDisclaimer.objects.count(), 3)
        self.assertEqual(PrintDisclaimer.objects.count(), 2)

        # user has no bookings in past 365 days, but disclaimer should not be
        # deleted because it was created < 365 days ago.  All others will be.
        management.call_command('delete_expired_disclaimers')
        self.assertEqual(OnlineDisclaimer.objects.count(), 1)
        self.assertEqual(PrintDisclaimer.objects.count(), 0)

    def test_disclaimers_not_deleted_if_updated_in_past_year(self):
        # make a user with a disclaimer created > yr ago but updated in past yr
        user = mommy.make_recipe('booking.user')
        mommy.make(
            OnlineDisclaimer, user=user, date=timezone.now() - timedelta(370),
            date_updated=timezone.now() - timedelta(360),
        )
        self.assertEqual(OnlineDisclaimer.objects.count(), 3)
        self.assertEqual(PrintDisclaimer.objects.count(), 2)

        # user has no bookings in past 365 days, but disclaimer should not be
        # deleted because it was created < 365 days ago.  The other 3 will be
        # deleted

        management.call_command('delete_expired_disclaimers')
        self.assertEqual(OnlineDisclaimer.objects.count(), 1)
        self.assertEqual(PrintDisclaimer.objects.count(), 0)

    def test_disclaimer_with_multiple_bookings(self):
        self.assertEqual(OnlineDisclaimer.objects.count(), 2)
        self.assertEqual(PrintDisclaimer.objects.count(), 2)

        # make paid and unpaid bookings for self.user_online_only in past 365
        # days and earlier; disclaimer not deleted
        mommy.make_recipe(
            'booking.booking',
            user=self.user_online_only,
            event__date=timezone.now()-timedelta(360),
            paid=True
        )
        mommy.make_recipe(
            'booking.booking',
            user=self.user_online_only,
            event__date=timezone.now()-timedelta(200),
            paid=False
        )
        mommy.make_recipe(
            'booking.booking',
            user=self.user_online_only,
            event__date=timezone.now()-timedelta(400),
            paid=True
        )
        mommy.make_recipe(
            'booking.booking',
            user=self.user_online_only,
            event__date=timezone.now()-timedelta(400),
            paid=False
        )

        management.call_command('delete_expired_disclaimers')
        # only disclaimer for self.user_online_only is not deleted
        self.assertEqual(OnlineDisclaimer.objects.count(), 1)
        self.assertEqual(PrintDisclaimer.objects.count(), 0)
        self.assertEqual(
            OnlineDisclaimer.objects.first().user, self.user_online_only
        )
        
    def test_email_sent_to_studio(self):
        self.assertEqual(OnlineDisclaimer.objects.count(), 2)
        self.assertEqual(PrintDisclaimer.objects.count(), 2)

        # make one paid booking for self.user_online_only in past 365 days; this
        # user's disclaimer should not be deleted
        mommy.make_recipe(
            'booking.booking',
            user=self.user_online_only,
            event__date=timezone.now()-timedelta(360),
            paid=True
        )
        management.call_command('delete_expired_disclaimers')
        self.assertEqual(len(mail.outbox), 1)

    @patch('accounts.management.commands.delete_expired_disclaimers.send_mail')
    def test_email_errors_sending_to_studio(self, mock_send_mail):
        mock_send_mail.side_effect = Exception('Error sending mail')
        management.call_command('delete_expired_disclaimers')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [settings.SUPPORT_EMAIL])

    @patch('accounts.management.commands.delete_expired_disclaimers.send_mail')
    @patch('booking.email_helpers.send_mail')
    def test_email_errors(self, mock_send_mail, mock_send_mail1):
        mock_send_mail.side_effect = Exception('Error sending mail')
        mock_send_mail1.side_effect = Exception('Error sending mail')
        self.assertEqual(OnlineDisclaimer.objects.count(), 2)
        self.assertEqual(PrintDisclaimer.objects.count(), 2)

        management.call_command('delete_expired_disclaimers')
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(OnlineDisclaimer.objects.count(), 0)
        self.assertEqual(PrintDisclaimer.objects.count(), 0)

    def test_email_not_sent_to_studio_if_nothing_deleted(self):
        self.assertEqual(OnlineDisclaimer.objects.count(), 2)
        self.assertEqual(PrintDisclaimer.objects.count(), 2)

        for user in User.objects.all():
            mommy.make_recipe(
            'booking.booking',
            user=user,
            event__date=timezone.now()-timedelta(10),
            paid=True
        )

        management.call_command('delete_expired_disclaimers')
        self.assertEqual(OnlineDisclaimer.objects.count(), 2)
        self.assertEqual(PrintDisclaimer.objects.count(), 2)
        self.assertEqual(len(mail.outbox), 0)


@override_settings(LOG_FOLDER=os.path.dirname(__file__))
class ExportDisclaimersTests(TestCase):

    def setUp(self):
        mommy.make(OnlineDisclaimer, _quantity=10)

    def test_export_disclaimers_creates_default_bu_file(self):
        bu_file = os.path.join(settings.LOG_FOLDER, 'disclaimers_bu.csv')
        self.assertFalse(os.path.exists(bu_file))
        management.call_command('export_disclaimers')
        self.assertTrue(os.path.exists(bu_file))
        os.unlink(bu_file)

    def test_export_disclaimers_writes_correct_number_of_rows(self):
        bu_file = os.path.join(settings.LOG_FOLDER, 'disclaimers_bu.csv')
        management.call_command('export_disclaimers')

        with open(bu_file, 'r') as exported:
            reader = csv.reader(exported)
            rows = list(reader)
        self.assertEqual(len(rows), 11)  # 10 records plus header row
        os.unlink(bu_file)

    def test_export_disclaimers_with_filename_argument(self):
        bu_file = os.path.join(settings.LOG_FOLDER, 'test_file.csv')
        self.assertFalse(os.path.exists(bu_file))
        management.call_command('export_disclaimers', file=bu_file)
        self.assertTrue(os.path.exists(bu_file))
        os.unlink(bu_file)


@override_settings(LOG_FOLDER=os.path.dirname(__file__))
class ExportEncryptedDisclaimersTests(TestCase):

    def setUp(self):
        mommy.make(OnlineDisclaimer, _quantity=10)

    def test_export_disclaimers_creates_default_bu_file(self):
        bu_file = os.path.join(settings.LOG_FOLDER, 'disclaimers.bu')
        self.assertFalse(os.path.exists(bu_file))
        management.call_command('export_encrypted_disclaimers')
        self.assertTrue(os.path.exists(bu_file))
        os.unlink(bu_file)

    def test_export_disclaimers_sends_email(self):
        bu_file = os.path.join(settings.LOG_FOLDER, 'disclaimers.bu')
        management.call_command('export_encrypted_disclaimers')

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [settings.SUPPORT_EMAIL])

        os.unlink(bu_file)

    @patch.object(EmailMessage, 'send')
    def test_email_errors(self, mock_send):
        mock_send.side_effect = Exception('Error sending mail')
        bu_file = os.path.join(settings.LOG_FOLDER, 'disclaimers.bu')

        self.assertFalse(os.path.exists(bu_file))
        management.call_command('export_encrypted_disclaimers')
        # mail not sent, but back up still created
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(os.path.exists(bu_file))
        os.unlink(bu_file)

    def test_export_disclaimers_with_filename_argument(self):
        bu_file = os.path.join(settings.LOG_FOLDER, 'test_file.txt')
        self.assertFalse(os.path.exists(bu_file))
        management.call_command('export_encrypted_disclaimers', file=bu_file)
        self.assertTrue(os.path.exists(bu_file))
        os.unlink(bu_file)


class ImportDisclaimersTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.bu_file = os.path.join(
            os.path.dirname(__file__), 'test_data/test_disclaimers_backup.csv'
        )

    def test_import_disclaimers_no_matching_users(self):
        import_disclaimer_data_logger.warning = Mock()
        self.assertFalse(OnlineDisclaimer.objects.exists())
        management.call_command('import_disclaimer_data', file=self.bu_file)
        self.assertEqual(OnlineDisclaimer.objects.count(), 0)

        self.assertEqual(import_disclaimer_data_logger.warning.call_count, 3)
        self.assertIn(
            "Unknown user test_1 in backup data; data on row 1 not imported",
            str(import_disclaimer_data_logger.warning.call_args_list[0])
        )
        self.assertIn(
            "Unknown user test_2 in backup data; data on row 2 not imported",
            str(import_disclaimer_data_logger.warning.call_args_list[1])
        )
        self.assertIn(
            "Unknown user test_3 in backup data; data on row 3 not imported",
            str(import_disclaimer_data_logger.warning.call_args_list[2])
        )

    def test_import_disclaimers(self):
        for username in ['test_1', 'test_2', 'test_3']:
            mommy.make_recipe('booking.user', username=username)
        self.assertFalse(OnlineDisclaimer.objects.exists())
        management.call_command('import_disclaimer_data', file=self.bu_file)
        self.assertEqual(OnlineDisclaimer.objects.count(), 3)

    def test_import_disclaimers_existing_data(self):
        import_disclaimer_data_logger.warning = Mock()
        import_disclaimer_data_logger.info = Mock()

        # if disclaimer already exists for a user, it isn't imported
        for username in ['test_1', 'test_2']:
            mommy.make_recipe('booking.user', username=username)
        test_3 = mommy.make_recipe('booking.user', username='test_3')
        mommy.make(
            OnlineDisclaimer, user=test_3, name='Donald Duck')

        self.assertEqual(OnlineDisclaimer.objects.count(), 1)
        management.call_command('import_disclaimer_data', file=self.bu_file)
        self.assertEqual(OnlineDisclaimer.objects.count(), 3)

        # data has not been overwritten
        disclaimer = OnlineDisclaimer.objects.get(user=test_3)
        self.assertEqual(disclaimer.name, 'Donald Duck')

        self.assertEqual(import_disclaimer_data_logger.warning.call_count, 1)
        self.assertEqual(import_disclaimer_data_logger.info.call_count, 2)

        self.assertIn(
            "Disclaimer for test_1 imported from backup.",
            str(import_disclaimer_data_logger.info.call_args_list[0])
        )
        self.assertIn(
            "Disclaimer for test_2 imported from backup.",
            str(import_disclaimer_data_logger.info.call_args_list[1])
        )
        self.assertIn(
            "Disclaimer for test_3 already exists and has not been "
            "overwritten with backup data. Dates in db and back up DO NOT "
            "match",
            str(import_disclaimer_data_logger.warning.call_args_list[0])
        )

    def test_import_disclaimers_existing_data_matching_dates(self):
        import_disclaimer_data_logger.warning = Mock()
        import_disclaimer_data_logger.info = Mock()

        test_1 = mommy.make_recipe('booking.user', username='test_1')
        test_2 = mommy.make_recipe('booking.user', username='test_2')
        test_3 = mommy.make_recipe('booking.user', username='test_3')
        mommy.make(
            OnlineDisclaimer, user=test_2,
            date=datetime(2015, 1, 15, 15, 43, 19, 747445, tzinfo=timezone.utc),
            date_updated=datetime(
                2016, 1, 6, 15, 9, 16, 920219, tzinfo=timezone.utc
            )
        ),
        mommy.make(
            OnlineDisclaimer, user=test_3,
            date=datetime(2016, 2, 18, 16, 9, 16, 920219, tzinfo=timezone.utc),
        )

        self.assertEqual(OnlineDisclaimer.objects.count(), 2)
        management.call_command('import_disclaimer_data', file=self.bu_file)
        self.assertEqual(OnlineDisclaimer.objects.count(), 3)

        self.assertEqual(import_disclaimer_data_logger.warning.call_count, 2)
        self.assertEqual(import_disclaimer_data_logger.info.call_count, 1)

        self.assertIn(
            "Disclaimer for test_1 imported from backup.",
            str(import_disclaimer_data_logger.info.call_args_list[0])
        )
        self.assertIn(
            "Disclaimer for test_2 already exists and has not been "
            "overwritten with backup data. Dates in db and back up "
            "match",
            str(import_disclaimer_data_logger.warning.call_args_list[0])
        )
        self.assertIn(
            "Disclaimer for test_3 already exists and has not been "
            "overwritten with backup data. Dates in db and back up "
            "match",
            str(import_disclaimer_data_logger.warning.call_args_list[1])
        )

    def test_imported_data_is_correct(self):
        test_1 = mommy.make_recipe('booking.user', username='test_1')
        management.call_command('import_disclaimer_data', file=self.bu_file)
        test_1_disclaimer = OnlineDisclaimer.objects.get(user=test_1)

        self.assertEqual(test_1_disclaimer.name, 'Test User1')
        self.assertEqual(
            test_1_disclaimer.date,
            datetime(2015, 12, 18, 15, 32, 7, 191781, tzinfo=timezone.utc)
        )
        self.assertEqual(test_1_disclaimer.dob, date(1991, 11, 21))
        self.assertEqual(test_1_disclaimer.address, '11 Test Road')
        self.assertEqual(test_1_disclaimer.postcode, 'TS6 8JT')
        self.assertEqual(test_1_disclaimer.home_phone, '12345667')
        self.assertEqual(test_1_disclaimer.mobile_phone, '2423223423')
        self.assertEqual(test_1_disclaimer.emergency_contact1_name, 'Test1 Contact1')
        self.assertEqual(
            test_1_disclaimer.emergency_contact1_relationship, 'Partner'
        )
        self.assertEqual(
            test_1_disclaimer.emergency_contact1_phone, '8782347239'
        )
        self.assertEqual(test_1_disclaimer.emergency_contact2_name, 'Test2 Contact1')
        self.assertEqual(
            test_1_disclaimer.emergency_contact2_relationship, 'Father'
        )
        self.assertEqual(
            test_1_disclaimer.emergency_contact2_phone, '71684362378'
        )
        self.assertFalse(test_1_disclaimer.medical_conditions)
        self.assertEqual(test_1_disclaimer.medical_conditions_details, '')
        self.assertTrue(test_1_disclaimer.joint_problems)
        self.assertEqual(test_1_disclaimer.joint_problems_details, 'knee problems')
        self.assertFalse(test_1_disclaimer.allergies)
        self.assertEqual(test_1_disclaimer.allergies_details, '')
        self.assertIsNotNone(test_1_disclaimer.medical_treatment_terms)
        self.assertTrue(test_1_disclaimer.medical_treatment_permission)
        self.assertIsNotNone(test_1_disclaimer.disclaimer_terms)
        self.assertTrue(test_1_disclaimer.terms_accepted)
        self.assertIsNotNone(test_1_disclaimer.over_18_statement)
        self.assertTrue(test_1_disclaimer.age_over_18_confirmed)
