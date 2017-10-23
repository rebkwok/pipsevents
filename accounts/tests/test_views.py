import logging
from model_mommy import mommy
from requests.auth import HTTPBasicAuth
from requests.exceptions import HTTPError
from unittest.mock import call, Mock

from django.conf import settings
from django.contrib.auth.models import User, Group
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.urlresolvers import reverse
from django.test import TestCase, override_settings

from allauth.account.models import EmailAddress

from accounts.models import OnlineDisclaimer
from accounts.views import ProfileUpdateView, profile, DisclaimerCreateView

from common.tests.helpers import _create_session, assert_mailchimp_post_data, \
    TestSetupMixin


class ProfileUpdateViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(ProfileUpdateViewTests, cls).setUpTestData()
        cls.url = reverse('profile:update_profile')
        cls.group, _ = Group.objects.get_or_create(name='subscribed')

    def setUp(self):
        super(ProfileUpdateViewTests, self).setUp()
        self.user.first_name="Test"
        self.user.last_name="User"
        self.user.save()

    def test_updating_user_data(self):
        """
        Test custom view to allow users to update their details
        """
        self.client.login(username=self.user.username, password='test')
        self.client.post(
            self.url, {'username': self.user.username,
                  'first_name': 'Fred', 'last_name': self.user.last_name}
        )
        self.user.refresh_from_db()
        self.assertEquals(self.user.first_name, "Fred")


    def test_updates_mailchimp_with_first_name(self):
        self.client.login(username=self.user.username, password='test')
        self.client.post(
            self.url, {'username': self.user.username,
                  'first_name': 'Fred', 'last_name': self.user.last_name}
        )
        self.user.refresh_from_db()
        self.assertFalse(self.user.subscribed())
        assert_mailchimp_post_data(
            self.mock_request, self.user, 'unsubscribed'
        )

    def test_updates_mailchimp_with_last_name(self):
        self.client.login(username=self.user.username, password='test')
        self.client.post(
            self.url, {'username': self.user.username,
                  'first_name': self.user.first_name, 'last_name': 'New'}
        )
        self.user.refresh_from_db()
        assert_mailchimp_post_data(
            self.mock_request, self.user, 'unsubscribed'
        )

    def test_mailchimp_updated_with_existing_subscription_status(self):
        self.client.login(username=self.user.username, password='test')
        self.client.post(
            self.url,
            {
                'username': self.user.username,
                'first_name': 'Fred',
                'last_name': self.user.last_name
            }
        )

        self.user.refresh_from_db()
        self.assertFalse(self.user.subscribed())
        assert_mailchimp_post_data(
            self.mock_request, self.user, 'unsubscribed'
        )

        self.group.user_set.add(self.user)
        self.assertTrue(self.user.subscribed())
        request = self.factory.post(
            self.url,
            {
                'username': self.user.username,
                'first_name': 'Fred1',
                'last_name': self.user.last_name
            }
        )
        request.user = self.user
        view = ProfileUpdateView.as_view()
        view(request)
        self.user.refresh_from_db()
        assert_mailchimp_post_data(
            self.mock_request, self.user, 'subscribed'
        )

    def test_username_changes_do_not_update_mailchimp(self):
        self.client.login(username=self.user.username, password='test')
        self.client.post(
            self.url,
            {
                'username': 'foo',
                'first_name': self.user.first_name,
                'last_name': self.user.last_name
            }
        )
        self.user.refresh_from_db()

        self.assertEqual(self.user.username, 'foo')
        self.assertEqual(self.mock_request.call_count, 0)

    @override_settings(MAILCHIMP_LIST_ID='fake')
    def test_invalid_mailchimp_list_id(self):
        self.mock_request.side_effect = HTTPError(
            Mock(return_value={'status': 404}), 'not found'
        )

        self.client.login(username=self.user.username, password='test')
        with self.assertLogs(level='ERROR') as cm:
            resp = self.client.post(self.url,
            {
                'username': self.user.username,
                'first_name': 'Foo',
                'last_name': self.user.last_name
            })

        self.assertEqual(len(cm.output), 1)
        self.assertIn('Error updating mailchimp', cm.output[0])
        # post succeeds, even though calls to mailchimp raise 404
        self.assertEqual(resp.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Foo')

        # called with the invalid id
        self.mock_request.assert_called_with(
            timeout=20,
            hooks={'response': []},
            method='POST',
            url='https://{}.api.mailchimp.com/3.0/lists/fake'.format(
                settings.MAILCHIMP_SECRET
            ),
            auth=HTTPBasicAuth(
                settings.MAILCHIMP_USER, settings.MAILCHIMP_SECRET
            ),
            json={
                'update_existing': True,
                'members': [
                    {
                        'email_address': self.user.email,
                        'status': 'unsubscribed',
                        'status_if_new': 'unsubscribed',
                        'merge_fields': {
                            'FNAME': self.user.first_name,
                            'LNAME': self.user.last_name
                        }
                    }
                ]
            }
        )


class CustomEmailViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(CustomEmailViewTests, cls).setUpTestData()
        cls.group, _ = Group.objects.get_or_create(name='subscribed')
        cls.url = reverse('account_email')

    def setUp(self):
        super(CustomEmailViewTests, self).setUp()
        # set primary email
        EmailAddress.objects.create(
            user=self.user, email=self.user.email, primary=True, verified=True
        )

    def test_change_primary_email_unsubscribed_user(self):
        # create another email address for this user
        EmailAddress.objects.create(
            user=self.user, email='new@test.com', primary=False, verified=True
        )
        self.client.login(username=self.user.username, password='test')
        self.assertFalse(self.user.subscribed())
        data = {'email': 'new@test.com', 'action_primary': True}
        resp = self.client.post(self.url, data=data)

        self.user.refresh_from_db()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.user.email, 'new@test.com')

        # mailchimp called twice, to ensure old email is unsubscribed and new
        # email added/updated with user's current status
        self.assertEqual(self.mock_request.call_count, 2)
        first_call = call(
            timeout=20,
            hooks={'response': []},
            method='POST',
            url='https://{}.api.mailchimp.com/3.0/lists/{}'.format(
                settings.MAILCHIMP_SECRET, settings.MAILCHIMP_LIST_ID
            ),
            auth=HTTPBasicAuth(
                settings.MAILCHIMP_USER, settings.MAILCHIMP_SECRET
            ),
            json={
                'update_existing': True,
                'members': [
                    {
                        'email_address': 'test@test.com',
                        'status': 'unsubscribed',
                        'status_if_new': 'unsubscribed',
                        'merge_fields': {
                            'FNAME': self.user.first_name,
                            'LNAME': self.user.last_name
                        }
                    }
                ]
            }
        )
        second_call = call(
            timeout=20,
            hooks={'response': []},
            method='POST',
            url='https://{}.api.mailchimp.com/3.0/lists/{}'.format(
                settings.MAILCHIMP_SECRET, settings.MAILCHIMP_LIST_ID
            ),
            auth=HTTPBasicAuth(
                settings.MAILCHIMP_USER, settings.MAILCHIMP_SECRET
            ),
            json={
                'update_existing': True,
                'members': [
                    {
                        'email_address': 'new@test.com',
                        'status': 'unsubscribed',
                        'status_if_new': 'unsubscribed',
                        'merge_fields': {
                            'FNAME': self.user.first_name,
                            'LNAME': self.user.last_name
                        }
                    }
                ]
            }
        )
        self.assertEqual(
            self.mock_request.call_args_list, [first_call, second_call]
        )

    def test_change_primary_email_subscribed_user(self):
        # create another email address for this user
        EmailAddress.objects.create(
            user=self.user, email='new@test.com', primary=False, verified=True
        )
        # subscribe user
        self.group.user_set.add(self.user)
        self.client.login(username=self.user.username, password='test')
        self.assertTrue(self.user.subscribed())
        data = {'email': 'new@test.com', 'action_primary': True}
        resp = self.client.post(self.url, data=data)

        self.user.refresh_from_db()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.user.email, 'new@test.com')

        # mailchimp called twice, to ensure old email is unsubscribed and new
        # email added/updated with user's current status
        self.assertEqual(self.mock_request.call_count, 2)
        first_call = call(
            timeout=20,
            hooks={'response': []},
            method='POST',
            url='https://{}.api.mailchimp.com/3.0/lists/{}'.format(
                settings.MAILCHIMP_SECRET, settings.MAILCHIMP_LIST_ID
            ),
            auth=HTTPBasicAuth(
                settings.MAILCHIMP_USER, settings.MAILCHIMP_SECRET
            ),
            json={
                'update_existing': True,
                'members': [
                    {
                        'email_address': 'test@test.com',
                        'status': 'unsubscribed',
                        'status_if_new': 'unsubscribed',
                        'merge_fields': {
                            'FNAME': self.user.first_name,
                            'LNAME': self.user.last_name
                        }
                    }
                ]
            }
        )
        second_call = call(
            timeout=20,
            hooks={'response': []},
            method='POST',
            url='https://{}.api.mailchimp.com/3.0/lists/{}'.format(
                settings.MAILCHIMP_SECRET, settings.MAILCHIMP_LIST_ID
            ),
            auth=HTTPBasicAuth(
                settings.MAILCHIMP_USER, settings.MAILCHIMP_SECRET
            ),
            json={
                'update_existing': True,
                'members': [
                    {
                        'email_address': 'new@test.com',
                        'status': 'subscribed',
                        'status_if_new': 'subscribed',
                        'merge_fields': {
                            'FNAME': self.user.first_name,
                            'LNAME': self.user.last_name
                        }
                    }
                ]
            }
        )
        self.assertEqual(
            self.mock_request.call_args_list, [first_call, second_call]
        )

    def test_mailchimp_not_called_if_action_errors(self):
        # Try to change primary to unverified email --> error
        # create another unverified email address for this user
        EmailAddress.objects.create(
            user=self.user, email='new@test.com', primary=False, verified=False
        )
        self.client.login(username=self.user.username, password='test')
        data = {'email': 'new@test.com', 'action_primary': True}
        self.client.post(self.url, data=data)

        self.user.refresh_from_db()
        # Email address not changed
        self.assertEqual(self.user.email, 'test@test.com')
        # mailchimp not updated
        self.assertEqual(self.mock_request.call_count, 0)

    def test_mailchimp_not_called_if_not_changing_primary(self):
        # create another email address for this user
        EmailAddress.objects.create(
            user=self.user, email='new@test.com', primary=False, verified=False
        )
        self.assertEqual(
            EmailAddress.objects.filter(user=self.user).count(), 2
        )
        self.client.login(username=self.user.username, password='test')
        data = {'email': 'new@test.com', 'action_remove': True}
        resp = self.client.post(self.url, data=data)

        self.user.refresh_from_db()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            EmailAddress.objects.filter(user=self.user).count(), 1
        )
        self.assertEqual(self.mock_request.call_count, 0)

    @override_settings(MAILCHIMP_LIST_ID='fake')
    def test_invalid_mailchimp_list_id(self):
        self.mock_request.side_effect = HTTPError(
            Mock(return_value={'status': 404}), 'not found'
        )
        # create another email address for this user
        EmailAddress.objects.create(
            user=self.user, email='new@test.com', primary=False, verified=True
        )
        self.client.login(username=self.user.username, password='test')
        self.assertFalse(self.user.subscribed())
        data = {'email': 'new@test.com', 'action_primary': True}
        with self.assertLogs(level='ERROR') as cm:
            resp = self.client.post(self.url, data=data)
        self.assertEqual(len(cm.output), 1)
        self.assertIn('Error updating mailchimp', cm.output[0])
        # post succeds, even though calls to mailchimp raise 404
        self.assertEqual(resp.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'new@test.com')
        # only attempted to call mailchimp once
        self.assertEqual(self.mock_request.call_count, 1)

        # called with the invalid id; only called to try to unsubscribe old
        # email
        self.mock_request.assert_called_with(
            timeout=20,
            hooks={'response': []},
            method='POST',
            url='https://{}.api.mailchimp.com/3.0/lists/fake'.format(
                settings.MAILCHIMP_SECRET
            ),
            auth=HTTPBasicAuth(
                settings.MAILCHIMP_USER, settings.MAILCHIMP_SECRET
            ),
            json={
                'update_existing': True,
                'members': [
                    {
                        'email_address': 'test@test.com',
                        'status': 'unsubscribed',
                        'status_if_new': 'unsubscribed',
                        'merge_fields': {
                            'FNAME': self.user.first_name,
                            'LNAME': self.user.last_name
                        }
                    }
                ]
            }
        )


class ProfileTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(ProfileTests, cls).setUpTestData()
        Group.objects.get_or_create(name='instructors')

    def setUp(self):
        super(ProfileTests, self).setUp()
        self.user_with_online_disclaimer = mommy.make_recipe('booking.user')
        mommy.make(OnlineDisclaimer, user=self.user_with_online_disclaimer)
        self.user_no_disclaimer = mommy.make_recipe('booking.user')

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

    def setUp(self):
        super(CustomLoginViewTests, self).setUp()
        self.user = User.objects.create(username='test_user', is_active=True)
        self.user.set_password('password')
        self.user.save()
        EmailAddress.objects.create(user=self.user,
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

    def test_login_from_password_change(self):
        # facebook url is modified to return to the profile page
        resp = self.client.get(
            reverse('login') + '?next=/accounts/password/change/'
        )

        # url is weirdly formatted one way if we run only this test and the
        # other if we run all. Not sure why yet, but it would behave correctly
        # either way
        self.assertTrue(
            'href="/accounts/facebook/login/?process=login'
            '&next=%2Faccounts%2Fprofile"' in resp.rendered_content or
            'href="/accounts/facebook/login/?next=%2Faccounts%2Fprofile'
            '&process=login"' in resp.rendered_content
        )

        resp = self.client.get(
            reverse('login') + '?next=/accounts/password/set/'
        )
        self.assertTrue(
            'href="/accounts/facebook/login/?process=login'
            '&next=%2Faccounts%2Fprofile"' in resp.rendered_content or
            'href="/accounts/facebook/login/?next=%2Faccounts%2Fprofile'
            '&process=login"' in resp.rendered_content
        )

        # post with login username and password overrides next in request
        # params to return to profile
        resp = self.client.post(
            reverse('login') + '?next=/accounts/password/change/',
            {'login': self.user.username, 'password': 'password'}
        )

        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('profile:profile'), resp.url)

        resp = self.client.post(
            reverse('login') + '?next=/accounts/password/set/',
            {'login': self.user.username, 'password': 'password'}
        )

        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('profile:profile'), resp.url)


class DisclaimerCreateViewTests(TestSetupMixin, TestCase):

    def setUp(self):
        super(DisclaimerCreateViewTests, self).setUp()
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


class MailingListSubscribeViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(MailingListSubscribeViewTests, cls).setUpTestData()
        cls.subscribed = mommy.make(Group, name='subscribed')

    def test_login_required(self):
        url = reverse('subscribe')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(
            resp.url, reverse('login') + '?next=/accounts/mailing-list/'
        )

        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_get_shows_correct_subscription_status(self):
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(reverse('subscribe'))
        self.assertIn(
            "You are not currently subscribed to the mailing list.",
            resp.rendered_content
        )

        self.subscribed.user_set.add(self.user)
        resp = self.client.get(reverse('subscribe'))
        self.assertIn(
            "You are currently subscribed to the mailing list.  "
            "Please click below if you would like to unsubscribe.",
            resp.rendered_content
        )

    def test_can_change_subscription(self):
        self.subscribed = Group.objects.get(name='subscribed')
        self.client.login(username=self.user.username, password='test')
        self.assertNotIn(self.subscribed, self.user.groups.all())

        self.client.post(reverse('subscribe'), {'subscribe': 'Subscribe'})
        self.assertIn(self.subscribed, self.user.groups.all())
        # mailchimp updated
        assert_mailchimp_post_data(self.mock_request, self.user, 'subscribed')

        self.client.post(reverse('subscribe'), {'unsubscribe': 'Unsubscribe'})
        self.assertNotIn(self.subscribed, self.user.groups.all())
        # mailchimp updated
        assert_mailchimp_post_data(
            self.mock_request, self.user, 'unsubscribed'
        )