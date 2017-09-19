from model_mommy import mommy
from requests.auth import HTTPBasicAuth
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User, Group
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.urlresolvers import reverse
from django.test import TestCase, override_settings

from allauth.account.models import EmailAddress

from accounts.models import OnlineDisclaimer
from accounts.views import ProfileUpdateView, profile, DisclaimerCreateView
from activitylog.models import ActivityLog

from common.tests.helpers import _create_session, assert_mailchimp_post_data, \
    TestSetupMixin


class ApiViewTests(TestSetupMixin, TestCase):
    """
    Tests for the mailchimp webhook that gets called when data on the list is
    updated in mailchimp
    """

    @classmethod
    def setUpTestData(cls):
        super(ApiViewTests, cls).setUpTestData()
        cls.url = reverse('accounts_api:mailing_list_api')
        cls.group, _ = Group.objects.get_or_create(name='subscribed')

    def get_data_dict(
            self, action, email=None, new_email=None, old_email=None,
            first_name=None, last_name=None, list_id=settings.MAILCHIMP_LIST_ID
    ):
        DATA_DICTS = {
            'subscribe':
                {
                    "type": "subscribe",
                    "fired_at": "2009-03-26 21:35:57",
                    "data[id]": "8a25ff1d98",
                    "data[list_id]": list_id,
                    "data[email]": email,
                    "data[email_type]": "html",
                    "data[merges][EMAIL]": email,
                    "data[merges][FNAME]": first_name,
                    "data[merges][LNAME]": last_name,
                    "data[merges][INTERESTS]": "Group1,Group2",
                    "data[ip_opt]": "10.20.10.30",
                    "data[ip_signup]": "10.20.10.30"
                },
            'unsubscribe':
                {
                    "type": "unsubscribe",
                    "fired_at": "2009-03-26 21:40:57",
                    "data[action]": "unsub",
                    "data[reason]": "manual",
                    "data[id]": "8a25ff1d98",
                    "data[list_id]": list_id,
                    "data[email]": email,
                    "data[email_type]": "html",
                    "data[merges][EMAIL]": email,
                    "data[merges][FNAME]": first_name,
                    "data[merges][LNAME]": last_name,
                    "data[merges][INTERESTS]": "Group1,Group2",
                    "data[ip_opt]": "10.20.10.30",
                    "data[campaign_id]": "cb398d21d2",
                    "data[reason]": "hard"
                },
            'update_profile': {
                "type": "profile",
                "fired_at": "2009-03-26 21:31:21",
                "data[id]": "8a25ff1d98",
                "data[list_id]": list_id,
                "data[email]": email,
                "data[email_type]": "html",
                "data[merges][EMAIL]": email,
                "data[merges][FNAME]": first_name,
                "data[merges][LNAME]": last_name,
                "data[merges][INTERESTS]": "Group1,Group2",
                "data[ip_opt]": "10.20.10.30"
                },
            'update_email': {
                "type": "upemail",
                "fired_at": "2009-03-26 22:15:09",
                "data[list_id]": list_id,
                "data[new_id]": "51da8c3259",
                "data[new_email]": new_email,
                "data[old_email]": old_email
            }
        }
        return DATA_DICTS[action]

    def test_get_mailing_list(self):
        # No mailing list users
        resp = self.client.get(self.url)
        self.assertEqual(resp.json(), [])

        # make some mailing list users
        self.group.user_set.add(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(
            resp.json(),
            [
                {'email': 'test@test.com', 'first_name': '', 'last_name': ''}
            ]
        )

        mommy.make_recipe('booking.user')

        self.assertEqual(User.objects.count(), 2)
        # still just one mailing list user shown
        resp = self.client.get(self.url)
        self.assertEqual(
            resp.json(),
            [
                {'email': 'test@test.com', 'first_name': '', 'last_name': ''}
            ]
        )

    def test_subscribe_user_request_from_mailchimp(self):
        self.assertFalse(self.user.subscribed())
        data = self.get_data_dict('subscribe', email=self.user.email)
        resp = self.client.post(self.url, data=data)
        self.assertEqual(resp.status_code, 204)

        self.user.refresh_from_db()
        self.assertTrue(self.user.subscribed())

    def test_unsubscribe_user_request_from_mailchimp(self):
        self.group.user_set.add(self.user)
        self.assertTrue(self.user.subscribed())
        data = self.get_data_dict('unsubscribe', email=self.user.email)
        resp = self.client.post(self.url, data=data)
        self.assertEqual(resp.status_code, 204)

        self.user.refresh_from_db()
        self.assertFalse(self.user.subscribed())

    @patch('accounts.api_views.time.sleep')
    def test_update_profile_request_from_mailchimp(self, mock_sleep):
        # patch sleep() to avoid test delays
        self.assertFalse(self.user.subscribed())
        data = self.get_data_dict(
            'update_profile', email=self.user.email, first_name='Joe',
            last_name='Bloggs'
        )
        resp = self.client.post(self.url, data=data)
        self.assertEqual(resp.status_code, 204)

        self.user.refresh_from_db()
        self.assertFalse(self.user.subscribed())
        self.assertEqual(self.user.first_name, 'Joe')
        self.assertEqual(self.user.last_name, 'Bloggs')
        activity_log = ActivityLog.objects.latest('id')
        self.assertEqual(
            activity_log.log,
            'User profile updated for {} ({}); first name, last name changed '
            'via API request from MailChimp'.format(
            self.user.username, self.user.email
            )
        )
        # sleep for 5 secs is called with update_profile in case we got an
        # update email at the same time (to ensure email is updated before
        # profile)
        mock_sleep.assert_called_once_with(5)

    @patch('accounts.api_views.time.sleep')
    def test_update_profile_request_no_change(self, mock_sleep):
        # patch sleep() to avoid test delays
        self.assertFalse(self.user.subscribed())
        data = self.get_data_dict(
            'update_profile', email=self.user.email,
            first_name=self.user.first_name,
            last_name=self.user.last_name
        )
        resp = self.client.post(self.url, data=data)
        self.assertEqual(resp.status_code, 204)

        self.user.refresh_from_db()
        self.assertFalse(self.user.subscribed())
        self.assertEqual(self.user.first_name, self.user.first_name,)
        self.assertEqual(self.user.last_name, self.user.last_name,)
        activity_log = ActivityLog.objects.latest('id')

        # no activity log for this because no change
        self.assertEqual(
            activity_log.log,
            'New user registered: {} {}, username {}'.format(
            self.user.first_name, self.user.last_name, self.user.username
            )
        )
        # sleep for 5 secs is called with update_profile in case we got an
        # update email at the same time (to ensure email is updated before
        # profile)
        mock_sleep.assert_called_once_with(5)

    def test_update_email_request_from_mailchimp(self):
        self.assertFalse(self.user.subscribed())
        self.assertFalse(EmailAddress.objects.exists())
        data = self.get_data_dict(
            'update_email', old_email=self.user.email,
            new_email='new@test.com',
        )
        resp = self.client.post(self.url, data=data)
        self.assertEqual(resp.status_code, 204)

        self.user.refresh_from_db()
        self.assertFalse(self.user.subscribed())
        self.assertEqual(self.user.email, 'new@test.com')

        # new prmary email address created
        self.assertEqual(
            EmailAddress.objects.get(user=self.user, primary=True).email,
            'new@test.com'
        )

    def test_update_email_request_from_mailchimp_primary_email_already_set(self):
        # changes primary EmailAddress, sets on user.email
        old_email = EmailAddress.objects.create(
            user=self.user, email=self.user.email, verified=True, primary=True
        )
        data = self.get_data_dict(
            'update_email', old_email=self.user.email,
            new_email='new@test.com',
        )
        resp = self.client.post(self.url, data=data)
        self.assertEqual(resp.status_code, 204)

        self.user.refresh_from_db()
        old_email.refresh_from_db()

        self.assertEqual(self.user.email, 'new@test.com')
        self.assertEqual(
            EmailAddress.objects.get(user=self.user, primary=True).email,
            'new@test.com'
        )
        self.assertFalse(old_email.primary)

    def test_update_email_request_from_mailchimp_email_exists_for_user(self):
        # changes primary EmailAddress, sets on user.email
        old_email = EmailAddress.objects.create(
            user=self.user, email=self.user.email, verified=True, primary=True
        )
        new_email = EmailAddress.objects.create(
            user=self.user, email='new@test.com', primary=False
        )
        data = self.get_data_dict(
            'update_email', old_email=self.user.email,
            new_email='new@test.com',
        )
        resp = self.client.post(self.url, data=data)
        self.assertEqual(resp.status_code, 204)

        self.user.refresh_from_db()
        old_email.refresh_from_db()
        new_email.refresh_from_db()
        self.assertEqual(self.user.email, 'new@test.com')
        self.assertEqual(
            EmailAddress.objects.get(user=self.user, primary=True).email,
            'new@test.com'
        )
        self.assertFalse(old_email.primary)

    def test_update_email_request_from_mailchimp_exists_for_diff_user(self):
        # 400
        user = mommy.make_recipe('booking.user')
        EmailAddress.objects.create(user=user, email=user.email)
        data = self.get_data_dict(
            'update_email', old_email=self.user.email,
            new_email=user.email,
        )
        resp = self.client.post(self.url, data=data)
        self.assertEqual(resp.status_code, 400)

    def test_request_from_mailchimp_no_matching_user(self):
        data = self.get_data_dict(
            'subscribe', email='foo@foo.com',
            first_name=self.user.first_name, last_name=self.user.last_name
        )
        resp = self.client.post(self.url, data=data)
        self.assertEqual(resp.status_code, 400)

    def test_request_from_mailchimp_invalid_list_id(self):
        data = self.get_data_dict(
            'subscribe', list_id='invalid-id', email=self.user.email,
            first_name=self.user.first_name, last_name=self.user.last_name
        )
        resp = self.client.post(self.url, data=data)
        self.assertEqual(resp.status_code, 400)


