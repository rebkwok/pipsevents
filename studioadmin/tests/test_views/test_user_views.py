from model_bakery import baker

from django.urls import reverse
from django.db.models import Q
from django.test import TestCase
from django.contrib.auth.models import Group, User, Permission
from django.contrib.messages.storage.fallback import FallbackStorage

from accounts.models import DisclaimerContent, OnlineDisclaimer, PrintDisclaimer
from common.tests.helpers import _create_session, assert_mailchimp_post_data
from studioadmin.utils import int_str, chaffify
from studioadmin.views import UserListView
from studioadmin.views.users import NAME_FILTERS
from studioadmin.tests.test_views.helpers import TestPermissionMixin


class UserListViewTests(TestPermissionMixin, TestCase):

    def _get_response(self, user, form_data={}):
        url = reverse('studioadmin:users')
        session = _create_session()
        request = self.factory.get(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        view = UserListView.as_view()
        return view(request)

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse('studioadmin:users')
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_can_access(self):
        """
        test that the page can be accessed by a non-staff user who is in the
        instructor group
        """
        resp = self._get_response(self.instructor_user)
        self.assertEqual(resp.status_code, 200)

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user)
        self.assertEqual(resp.status_code, 200)

    def test_all_users_are_displayed(self):
        baker.make_recipe('booking.user', _quantity=6)
        # 9 users total, incl self.user, self.instructor_user self.staff_user
        self.assertEqual(User.objects.count(), 9)
        resp = self._get_response(self.staff_user)
        self.assertEqual(
            list(resp.context_data['users']), list(User.objects.all())
        )

    def test_abbreviations_for_long_username(self):
        """
        Usernames > 15 characters are split to 2 lines
        """
        baker.make_recipe(
            'booking.user',
            username='test123456789101112'
        )
        resp = self._get_response(self.staff_user)
        self.assertIn('test12345678-</br>9101112', resp.rendered_content)

    def test_abbreviations_for_long_names(self):
        """
        Names > 12 characters are split to 2 lines; names with hyphens are
        split on the first hyphen
        """
        baker.make_recipe(
            'booking.user',
            first_name='namewithmorethan12characters',
            last_name='name-with-three-hyphens'
        )
        resp = self._get_response(self.staff_user)
        self.assertIn(
            'namewith-</br>morethan12characters', resp.rendered_content
        )
        self.assertIn('name-</br>with-three-hyphens', resp.rendered_content)

    def test_abbreviations_for_long_email(self):
        """
        Email > 25 characters is truncated
        """
        baker.make_recipe(
            'booking.user',
            email='test12345678@longemail.com'
        )
        resp = self._get_response(self.staff_user)
        self.assertIn('test12345678@longemail...', resp.rendered_content)

    def test_regular_student_button_not_shown_for_instructors(self):
        not_reg_student = baker.make_recipe('booking.user')
        reg_student = baker.make_recipe('booking.user')
        perm = Permission.objects.get(codename='is_regular_student')
        reg_student.user_permissions.add(perm)
        reg_student.save()

        resp = self._get_response(self.staff_user)
        resp.render()
        self.assertIn(
            'id="toggle_regular_student_{}"'.format(reg_student.id),
            str(resp.content)
        )
        self.assertIn(
            'id="toggle_regular_student_{}"'.format(not_reg_student.id),
            str(resp.content)
        )

        resp = self._get_response(self.instructor_user)
        resp.render()
        self.assertNotIn(
            'id="toggle_regular_student_{}"'.format(reg_student.id),
            str(resp.content)
        )
        self.assertNotIn(
            'id="toggle_regular_student_{}"'.format(not_reg_student.id),
            str(resp.content)
        )

    def test_change_regular_student(self):
        not_reg_student = baker.make_recipe('booking.user')
        reg_student = baker.make_recipe('booking.user')
        perm = Permission.objects.get(codename='is_regular_student')
        reg_student.user_permissions.add(perm)
        reg_student.save()

        self.assertTrue(reg_student.has_perm('booking.is_regular_student'))
        self.client.login(username=self.staff_user, password='test')
        self.client.get(
            reverse('studioadmin:toggle_regular_student', args=[reg_student.id])
        )
        changed_student = User.objects.get(id=reg_student.id)
        self.assertFalse(changed_student.has_perm('booking.is_regular_student'))

        self.assertFalse(not_reg_student.has_perm('booking.is_regular_student'))
        self.client.get(
            reverse(
                'studioadmin:toggle_regular_student', args=[not_reg_student.id]
            )
        )

        changed_student = User.objects.get(id=not_reg_student.id)
        self.assertTrue(changed_student.has_perm('booking.is_regular_student'))

    def test_cannot_remove_regular_student_for_superuser(self):
        reg_student = baker.make_recipe('booking.user')
        superuser = baker.make_recipe(
            'booking.user', first_name='Donald', last_name='Duck', username='dd'
        )
        superuser.is_superuser = True
        superuser.save()

        perm = Permission.objects.get(codename='is_regular_student')
        reg_student.user_permissions.add(perm)
        reg_student.save()

        self.assertTrue(reg_student.has_perm('booking.is_regular_student'))
        self.assertTrue(superuser.has_perm('booking.is_regular_student'))

        self.client.login(
            username=self.staff_user.username, password='test'
        )
        self.client.get(
            reverse('studioadmin:toggle_regular_student', args=[reg_student.id])
        )

        changed_student = User.objects.get(id=reg_student.id)
        self.assertFalse(changed_student.has_perm('booking.is_regular_student'))

        self.client.get(
            reverse('studioadmin:toggle_regular_student', args=[superuser.id])
        )

        # status hasn't changed
        self.assertTrue(superuser.has_perm('booking.is_regular_student'))

    def test_user_search(self):

        baker.make_recipe(
            'booking.user', username='FooBar', first_name='Foo',
            last_name='Bar'
        )
        baker.make_recipe(
            'booking.user', username='Testing1', first_name='Foo',
            last_name='Bar'
        )
        baker.make_recipe(
            'booking.user', username='Testing2', first_name='Boo',
            last_name='Bar'
        )

        resp = self._get_response(self.staff_user, {
            'search_submitted': 'Search',
            'search': 'Foo'})
        self.assertEqual(len(resp.context_data['users']), 2)

        resp = self._get_response(self.staff_user, {
            'search_submitted': 'Search',
            'search': 'FooBar'})
        self.assertEqual(len(resp.context_data['users']), 1)

        resp = self._get_response(self.staff_user, {
            'search_submitted': 'Search',
            'search': 'testing'})
        self.assertEqual(len(resp.context_data['users']), 2)

        self.assertEqual(User.objects.count(), 6)
        resp = self._get_response(self.staff_user, {
            'search': 'Foo',
            'reset': 'Reset'
        })
        self.assertEqual(len(resp.context_data['users']), 6)

    def test_user_filter(self):
        baker.make_recipe(
            'booking.user', username='FooBar', first_name='AUser',
            last_name='Bar'
        )
        baker.make_recipe(
            'booking.user', username='Testing1', first_name='aUser',
            last_name='Bar'
        )
        baker.make_recipe(
            'booking.user', username='Testing2', first_name='BUser',
            last_name='Bar'
        )

        resp = self._get_response(self.staff_user, {
            'filter': 'A'})
        self.assertEqual(len(resp.context_data['users']), 2)
        for user in resp.context_data['users']:
            self.assertTrue(user.first_name.upper().startswith('A'))

         # 6 users total, incl self.user, self.instructor_user self.staff_user
        self.assertEqual(User.objects.count(), 6)
        resp = self._get_response(self.staff_user, {
            'filter': 'All'})
        self.assertEqual(len(resp.context_data['users']), 6)

    def test_user_filter_and_search(self):
        baker.make_recipe(
            'booking.user', username='FooBar', first_name='AUser',
            last_name='Bar'
        )
        baker.make_recipe(
            'booking.user', username='Testing1', first_name='aUser',
            last_name='Bar'
        )
        baker.make_recipe(
            'booking.user', username='Testing2', first_name='BUser',
            last_name='Bar'
        )

        resp = self._get_response(self.staff_user, {
            'filter': 'A', 'search': 'Test'})
        self.assertEqual(len(resp.context_data['users']), 1)
        found_user = resp.context_data['users'][0]
        self.assertEqual(found_user.first_name, "aUser")

    def test_filter_options(self):
        # make a user with first name starting with all options
        for option in NAME_FILTERS:
            baker.make_recipe('booking.user', first_name='{}Usr'.format(option))
        # delete any starting with Z
        User.objects.filter(first_name__istartswith='Z').delete()
        resp = self._get_response(self.staff_user)
        filter_options = resp.context_data['filter_options']
        for opt in filter_options:
            if opt['value'] == 'Z':
                self.assertFalse(opt['available'])
            else:
                self.assertTrue(opt['available'])

        users = User.objects.filter(
            Q(first_name__istartswith='A') |
            Q(first_name__istartswith='B') |
            Q(first_name__istartswith='C')
        )
        for user in users:
            user.username = "{}_testfoo".format(user.first_name)
            user.save()

        resp = self._get_response(
            self.staff_user, {'search': 'testfoo', 'search_submitted': 'Search'}
        )
        filter_options = resp.context_data['filter_options']
        for opt in filter_options:
            if opt['value'] in ['All', 'A', 'B', 'C']:
                self.assertTrue(opt['available'])
            else:
                self.assertFalse(opt['available'])

    def test_instructor_cannot_change_regular_student(self):
        reg_student = baker.make_recipe('booking.user')
        perm = Permission.objects.get(codename='is_regular_student')
        reg_student.user_permissions.add(perm)
        reg_student.save()

        resp = self._get_response(
            self.instructor_user, {'change_user': [reg_student.id]}
        )
        reg_student = User.objects.get(id=reg_student.id)
        self.assertTrue(reg_student.has_perm('booking.is_regular_student'))

    def test_display_disclaimers(self):
        """
        Test that users with online disclaimers do not display print disclaimer
        button; users with print disclaimer or no disclaimer show print
        disclaimer button
        """
        superuser = User.objects.create_superuser(
            username='super', email='super@test.com', password='test'
        )

        user_with_print_disclaimer = baker.make_recipe('booking.user')
        baker.make(PrintDisclaimer, user=user_with_print_disclaimer)
        user_with_online_disclaimer = baker.make_recipe('booking.user')
        baker.make(OnlineDisclaimer, user=user_with_online_disclaimer, version=DisclaimerContent.current_version())
        user_with_no_disclaimer = baker.make_recipe('booking.user')

        resp = self._get_response(superuser)
        self.assertIn(
            'class="has-disclaimer-pill"', str(resp.rendered_content)
        )
        self.assertIn(
            reverse(
                'studioadmin:user_disclaimer',
                args=[int_str(chaffify(user_with_online_disclaimer.id))]
            ),
            str(resp.rendered_content)
        )
        self.assertIn(
            'id="toggle_print_disclaimer_{}"'.format(
                user_with_print_disclaimer.id
            ),
            str(resp.rendered_content)
        )
        self.assertIn(
            'id="toggle_print_disclaimer_{}"'.format(
                user_with_no_disclaimer.id
            ),
            str(resp.rendered_content)
        )
        self.assertNotIn(
            'id="toggle_print_disclaimer_{}"'.format(
                user_with_online_disclaimer.id
            ),
            str(resp.rendered_content)
        )
        resp = self._get_response(self.staff_user)
        self.assertIn(
            'class="has-disclaimer-pill"', str(resp.rendered_content)
        )
        self.assertIn(
            reverse(
                'studioadmin:user_disclaimer',
                args=[int_str(chaffify(user_with_online_disclaimer.id))]
            ),
            str(resp.rendered_content)
        )

    def test_print_disclaimer_button_only_shown_for_superusers(self):
        user_with_print_disclaimer = baker.make_recipe('booking.user')
        baker.make(PrintDisclaimer, user=user_with_print_disclaimer)
        superuser = User.objects.create_superuser(
            username='super', email='super@test.com', password='test'
        )
        resp = self._get_response(superuser)
        self.assertIn(
            'id="toggle_print_disclaimer_{}"'.format(
                user_with_print_disclaimer.id
            ),
            str(resp.rendered_content)
        )
        resp = self._get_response(self.staff_user)
        self.assertNotIn(
            'id="toggle_print_disclaimer_{}"'.format(
                user_with_print_disclaimer.id
            ),
            str(resp.rendered_content)
        )
        resp = self._get_response(self.instructor_user)
        self.assertNotIn(
            'id="toggle_print_disclaimer_{}"'.format(
                user_with_print_disclaimer.id
            ),
            str(resp.rendered_content)
        )

    def test_change_print_disclaimer(self):
        user_with_print_disclaimer = baker.make_recipe('booking.user')
        print_disc = baker.make(PrintDisclaimer, user=user_with_print_disclaimer)
        self.assertEqual(
            print_disc.id,
            user_with_print_disclaimer.print_disclaimer.id
        )

        self.assertEqual(PrintDisclaimer.objects.count(), 1)
        self.client.login(username=self.staff_user.username, password='test')
        self.client.get(
            reverse(
                'studioadmin:toggle_print_disclaimer',
                args=[user_with_print_disclaimer.id]
            )
        )

        # print disclaimer has been deleted
        self.assertEqual(PrintDisclaimer.objects.count(), 0)

        self.client.get(
            reverse(
                'studioadmin:toggle_print_disclaimer',
                args=[user_with_print_disclaimer.id]
            )
        )
        self.assertEqual(PrintDisclaimer.objects.count(), 1)
        user = User.objects.get(id=user_with_print_disclaimer.id)
        # a new print disclaimer has been created
        self.assertNotEqual(
            print_disc.id,
            user.print_disclaimer.id
        )

    def test_instructor_cannot_change_print_disclaimer(self):
        user_with_print_disclaimer = baker.make_recipe('booking.user')
        print_disc = baker.make(PrintDisclaimer, user=user_with_print_disclaimer)
        self.assertEqual(
            print_disc.id,
            user_with_print_disclaimer.print_disclaimer.id
        )

        self.assertEqual(PrintDisclaimer.objects.count(), 1)
        self.client.login(username=self.staff_user.username, password='test')
        self.client.get(
            reverse(
                'studioadmin:toggle_print_disclaimer',
                args=[user_with_print_disclaimer.id]
                )
        )
        # print disclaimer has been deleted
        self.assertEqual(PrintDisclaimer.objects.count(), 0)

        self.client.login(username=self.instructor_user.username, password='test')
        resp = self.client.get(
            reverse(
                'studioadmin:toggle_print_disclaimer',
                args=[user_with_print_disclaimer.id]
            )
        )
        # not permitted - no print disclaimer created
        self.assertEqual(PrintDisclaimer.objects.count(), 0)
        self.assertIn(resp.url, reverse('booking:permission_denied'))

    def test_mailing_list_button_not_shown_for_instructors(self):
        subscribed_user = baker.make_recipe('booking.user')
        unsubscribed_user = baker.make_recipe('booking.user')
        subscribed = baker.make(Group, name='subscribed')
        subscribed.user_set.add(subscribed_user)

        resp = self._get_response(self.staff_user)
        self.assertIn(
            'id="toggle_subscribed_{}"'.format(subscribed_user.id),
            resp.rendered_content
        )
        self.assertIn(
            'id="toggle_subscribed_{}"'.format(unsubscribed_user.id),
            resp.rendered_content
        )

        resp = self._get_response(self.instructor_user)
        resp.render()
        self.assertNotIn(
            'id="toggle_subscribed_{}"'.format(subscribed_user.id),
            str(resp.content)
        )
        self.assertNotIn(
            'id="toggle_subscribed_{}"'.format(unsubscribed_user.id),
            str(resp.content)
        )

    def test_change_mailing_list(self):
        subscribed_user = baker.make_recipe('booking.user')
        unsubscribed_user = baker.make_recipe('booking.user')
        subscribed = baker.make(Group, name='subscribed')
        subscribed.user_set.add(subscribed_user)

        self.assertIn(subscribed, subscribed_user.groups.all())
        self.client.login(username=self.staff_user.username, password='test')
        # unsubscribing user
        self.client.get(
            reverse('studioadmin:toggle_subscribed', args=[subscribed_user.id])
        )
        assert_mailchimp_post_data(
            self.mock_request, subscribed_user, 'unsubscribed'
        )

        subscribed_user.refresh_from_db()
        self.assertNotIn(subscribed, subscribed_user.groups.all())

        self.mock_request.reset_mock()
        self.assertNotIn(subscribed, unsubscribed_user.groups.all())
        self.client.get(
            reverse(
                'studioadmin:toggle_subscribed', args=[unsubscribed_user.id]
            )
        )
        unsubscribed_user.refresh_from_db()
        self.assertIn(subscribed, unsubscribed_user.groups.all())
        assert_mailchimp_post_data(
            self.mock_request, unsubscribed_user, 'subscribed'
        )

    def test_instructor_cannot_change_mailing_list(self):
        subscribed_user = baker.make_recipe('booking.user')
        subscribed = baker.make(Group, name='subscribed')
        subscribed.user_set.add(subscribed_user)

        self.assertIn(subscribed, subscribed_user.groups.all())
        self.client.login(
            username=self.instructor_user.username, password='test'
        )
        resp = self.client.get(
            reverse('studioadmin:toggle_subscribed', args=[subscribed_user.id])
        )
        self.assertIn(resp.url, reverse('booking:permission_denied'))
        subscribed_user.refresh_from_db()
        self.assertIn(subscribed, subscribed_user.groups.all())





