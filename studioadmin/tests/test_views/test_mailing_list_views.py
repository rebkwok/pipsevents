from model_mommy import mommy

from django.core.urlresolvers import reverse
from django.test import TestCase
from django.contrib.auth.models import Group

from studioadmin.tests.test_views.helpers import TestPermissionMixin


class MailingListViewTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(MailingListViewTests, cls).setUpTestData()
        cls.subscribed = mommy.make(Group, name='subscribed')

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
        ml_users = mommy.make_recipe('booking.user', _quantity=5)
        not_ml_users = mommy.make_recipe('booking.user', _quantity=5)

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
        ml_users = mommy.make_recipe('booking.user', _quantity=5)

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
