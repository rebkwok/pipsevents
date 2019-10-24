from model_bakery import baker

from django.contrib.auth.models import Group, User
from django.urls import reverse
from django.test import TestCase

from common.tests.helpers import assert_mailchimp_post_data

from studioadmin.tests.test_views.helpers import TestPermissionMixin


class MailingListViewTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(MailingListViewTests, cls).setUpTestData()
        cls.subscribed = baker.make(Group, name='subscribed')

    def test_staff_login_required(self):
        url = reverse('studioadmin:mailing_list')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(
            resp.url,
            reverse('login') + '?next=/studioadmin/users/mailing-list/'
        )

        self.client.login(
            username=self.instructor_user.username, password='test'
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(
            resp.url,
            reverse('booking:permission_denied')
        )

        self.client.login(
            username=self.staff_user.username, password='test'
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_shows_only_users_on_mailing_list(self):
        ml_users = baker.make_recipe('booking.user', _quantity=5)
        not_ml_users = baker.make_recipe('booking.user', _quantity=5)

        for user in ml_users:
            self.subscribed.user_set.add(user)
        self.client.login(
            username=self.staff_user.username, password='test'
        )

        url = reverse('studioadmin:mailing_list')
        resp = self.client.get(url)
        self.assertEqual(resp.context_data['users'].count(), 5)
        self.assertEqual(
            sorted([user.id for user in resp.context_data['users']]),
            sorted([user.id for user in ml_users])
        )

    def test_unsubscribe_user(self):
        ml_users = baker.make_recipe('booking.user', _quantity=5)

        for user in ml_users:
            self.subscribed.user_set.add(user)
        ml_user = ml_users[0]

        self.client.login(
            username=self.staff_user.username, password='test'
        )
        self.assertIn(self.subscribed, ml_user.groups.all())

        self.client.get(reverse('studioadmin:unsubscribe', args=[ml_user.id]))
        ml_user.refresh_from_db()
        self.assertNotIn(self.subscribed, ml_user.groups.all())

        # Updates mailchimp subscription
        assert_mailchimp_post_data(self.mock_request, ml_user, 'unsubscribed')

    def test_export_mailing_list(self):
        non_mailing_list_users = []
        for i in range(5):
            user = baker.make_recipe(
                'booking.user', email='test_user_{}@test.com'.format(i),
                first_name='Test_{}'.format(i), last_name='User'
            )
            self.subscribed.user_set.add(user)
            baker.make_recipe(
                'booking.user', email='test_non_ml_user_{}@test.com'.format(i),
                first_name='Test_non_ml{}'.format(i), last_name='User'
            )

        for user in User.objects.all():
            if user not in self.subscribed.user_set.all():
                non_mailing_list_users.append(user)
        self.client.login(
            username=self.staff_user.username, password='test'
        )
        resp = self.client.get(reverse('studioadmin:export_mailing_list'))
        # decode content, strip last EOL and split on EOLs
        content = resp.content.decode("utf-8").strip('\r\n')
        content_list = content.split('\r\n')
        # 6 rows in file, header row and 5 mailing list users
        self.assertEqual(len(content_list), 6)
        for user in self.subscribed.user_set.all():
            self.assertIn(user.email, content)
            self.assertIn(user.first_name, content)
            self.assertIn(user.last_name, content)
        for user in non_mailing_list_users:
            self.assertNotIn(user.email, content)
