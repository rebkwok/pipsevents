from datetime import datetime
from datetime import timezone as dt_timezone
from unittest.mock import Mock, patch

from model_bakery import baker
import pytest

from django.urls import reverse
from django.db.models import Q
from django.test import TestCase
from django.contrib.auth.models import Group, User
from django.core import mail
from django.utils import timezone

from accounts.models import DisclaimerContent, OnlineDisclaimer
from common.tests.helpers import assert_mailchimp_post_data
from studioadmin.utils import int_str, chaffify
from studioadmin.views.users import NAME_FILTERS
from studioadmin.tests.test_views.helpers import TestPermissionMixin
from stripe_payments.tests.mock_connector import MockConnector


class UserListViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.url = reverse('studioadmin:users')
        self.client.force_login(self.staff_user)
        mockresponse = Mock()
        mockresponse.status_code = 200
        self.patcher = patch('requests.request', return_value = mockresponse)
        self.mock_request = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        self.client.logout()
        resp = self.client.get(self.url)
        redirected_url = reverse('account_login') + f"?next={self.url}"
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        assert resp.status_code == 302
        assert resp.url == reverse('booking:permission_denied')

    def test_instructor_group_can_access(self):
        """
        test that the page can be accessed by a non-staff user who is in the
        instructor group
        """
        self.client.force_login(self.instructor_user)
        resp = self.client.get(self.url)
        assert resp.status_code == 200

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self.client.get(self.url)
        assert resp.status_code == 200

    def test_all_users_are_displayed(self):
        baker.make_recipe('booking.user', _quantity=6)
        # 9 users total, incl self.user, self.instructor_user self.staff_user
        assert User.objects.count() == 9
        resp = self.client.get(self.url)
        assert list(resp.context_data['users']) == list(User.objects.all())

    def test_abbreviations_for_long_username(self):
        """
        Usernames > 15 characters are split to 2 lines
        """
        baker.make_recipe(
            'booking.user',
            username='test123456789101112'
        )
        resp = self.client.get(self.url)
        assert 'test12345678-</br>9101112' in resp.rendered_content

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
        resp = self.client.get(self.url)
        assert 'namewith-</br>morethan12characters' in resp.rendered_content
        assert 'name-</br>with-three-hyphens' in resp.rendered_content

    def test_abbreviations_for_long_email(self):
        """
        Email > 25 characters is truncated
        """
        baker.make_recipe(
            'booking.user',
            email='test12345678@longemail.com'
        )
        resp = self.client.get(self.url)
        assert 'test12345678@longemail...' in resp.rendered_content

    def test_toggle_permission_buttons_not_shown_for_instructors(self):
        pp = baker.make_recipe("booking.event_type_PP")
        not_reg_student = baker.make_recipe('booking.user')
        reg_student = baker.make_recipe('booking.user')
        pp.add_permission_to_book(reg_student)

        resp = self.client.get(self.url)
        resp.render()
        self.assertIn(
            f'id="toggle_permission_{reg_student.id}"',
            str(resp.content)
        )
        self.assertIn(
            f'id="toggle_permission_{not_reg_student.id}"',
            str(resp.content)
        )

        self.client.force_login(self.instructor_user)
        resp = self.client.get(self.url)
        resp.render()
        self.assertNotIn(
            f'id="toggle_permission_{reg_student.id}"',
            str(resp.content)
        )
        self.assertNotIn(
            f'id="toggle_permission_{not_reg_student.id}"',
            str(resp.content)
        )

    def test_change_permission(self):
        pp = baker.make_recipe("booking.event_type_PP")
        not_reg_student = baker.make_recipe('booking.user')
        reg_student = baker.make_recipe('booking.user')
        pp.add_permission_to_book(reg_student)

        assert pp.has_permission_to_book(reg_student)
        assert not pp.has_permission_to_book(not_reg_student)

        self.client.login(username=self.staff_user, password='test')
        self.client.get(
            reverse('studioadmin:toggle_permission', args=[reg_student.id, pp.allowed_group.id])
        )
        assert not pp.has_permission_to_book(reg_student)

        self.client.get(
            reverse('studioadmin:toggle_permission', args=[not_reg_student.id, pp.allowed_group.id])
        )
        assert pp.has_permission_to_book(not_reg_student)

    def test_change_permission_to_experienced_sends_email(self):
        pc = baker.make_recipe("booking.event_type_PC", allowed_group__group__name="experienced")
        student = baker.make_recipe('booking.user', email="test@example.com")

        self.client.force_login(self.staff_user)
        self.client.get(
            reverse('studioadmin:toggle_permission', args=(student.id, pc.allowed_group.id))
        )
        assert pc.has_permission_to_book(student)
        assert len(mail.outbox) == 1
        assert "Account upgraded" in mail.outbox[0].subject

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

        resp = self.client.get(self.url + "?search=Foo")
        self.assertEqual(len(resp.context_data['users']), 2)

        resp = self.client.get(self.url + "?search=FooBar")
        self.assertEqual(len(resp.context_data['users']), 1)

        resp = self.client.get(self.url + "?search=testing")
        self.assertEqual(len(resp.context_data['users']), 2)

        self.assertEqual(User.objects.count(), 6)
        resp = self.client.get(self.url + "?search=Foo&reset=Reset")
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
        resp = self.client.get(self.url + "?filter=A")
        self.assertEqual(len(resp.context_data['users']), 2)
        for user in resp.context_data['users']:
            self.assertTrue(user.first_name.upper().startswith('A'))

         # 6 users total, incl self.user, self.instructor_user self.staff_user
        self.assertEqual(User.objects.count(), 6)
        resp = self.client.get(self.url + "?filter=All")
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
        resp = self.client.get(self.url + "?filter=A&search=Test")
        self.assertEqual(len(resp.context_data['users']), 1)
        found_user = resp.context_data['users'][0]
        self.assertEqual(found_user.first_name, "aUser")

    def test_filter_options(self):
        # make a user with first name starting with all options
        for option in NAME_FILTERS:
            baker.make_recipe('booking.user', first_name='{}Usr'.format(option))
        # delete any starting with Z
        User.objects.filter(first_name__istartswith='Z').delete()
        resp = self.client.get(self.url)
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

        resp = self.client.get(self.url + "?search=testfoo")
        filter_options = resp.context_data['filter_options']
        for opt in filter_options:
            if opt['value'] in ['All', 'A', 'B', 'C']:
                self.assertTrue(opt['available'])
            else:
                self.assertFalse(opt['available'])

    def testgroup_filter(self):
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

         # 6 users total, incl self.user, self.instructor_user self.staff_user; 1 instructor doesn't match first name filter
        self.assertEqual(User.objects.count(), 6)
        resp = self.client.get(self.url + "?group_filter=Instructors&pfilter=auser")
        self.assertEqual(len(resp.context_data['users']), 0)
    
    def testgroup_filter_unknown_group(self):
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

         # 6 users total, incl self.user, self.instructor_user self.staff_user; 1 instructor doesn't match first name filter
        self.assertEqual(User.objects.count(), 6)
        resp = self.client.get(self.url + "?group_filter=foo")
        self.assertEqual(len(resp.context_data['users']), 6)

    def testgroup_filter_all_groups(self):
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

         # 6 users total, incl self.user, self.instructor_user self.staff_user
         # group filter case insensitive
        self.assertEqual(User.objects.count(), 6)
        resp = self.client.get(self.url + "?group_filter=all")
        self.assertEqual(len(resp.context_data['users']), 6)

        resp = self.client.get(self.url + "?group_filter=All")
        self.assertEqual(len(resp.context_data['users']), 6)

    def testgroup_filter_and_previous_filter(self):
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
        resp = self.client.get(self.url + "?group_filter=Instructors")
        self.assertEqual(len(resp.context_data['users']), 1)

         # 6 users total, incl self.user, self.instructor_user self.staff_user
        self.assertEqual(User.objects.count(), 6)
        resp = self.client.get(self.url + "?group_filter=All")
        self.assertEqual(len(resp.context_data['users']), 6)

    def test_display_disclaimers(self):
        """
        Test that users with online disclaimers do not display print disclaimer
        button; users with print disclaimer or no disclaimer show print
        disclaimer button
        """
        superuser = User.objects.create_superuser(
            username='super', email='super@test.com', password='test'
        )

        user_with_online_disclaimer = baker.make_recipe('booking.user')
        baker.make(OnlineDisclaimer, user=user_with_online_disclaimer, version=DisclaimerContent.current_version())
        user_with_no_disclaimer = baker.make_recipe('booking.user')

        self.client.force_login(superuser)
        resp = self.client.get(self.url)
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
        self.client.force_login(self.staff_user)
        resp = self.client.get(self.url)
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

    def test_mailing_list_button_not_shown_for_instructors(self):
        subscribed_user = baker.make_recipe('booking.user')
        unsubscribed_user = baker.make_recipe('booking.user')
        subscribed = baker.make(Group, name='subscribed')
        subscribed.user_set.add(subscribed_user)

        resp = self.client.get(self.url)
        self.assertIn(
            'id="toggle_subscribed_{}"'.format(subscribed_user.id),
            resp.rendered_content
        )
        self.assertIn(
            'id="toggle_subscribed_{}"'.format(unsubscribed_user.id),
            resp.rendered_content
        )

        self.client.force_login(self.instructor_user)
        resp = self.client.get(self.url)
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


@pytest.mark.django_db
def test_attendance_list(client):
    user = User.objects.create_user(username="staff", password="test")
    user.is_staff = True
    user.save()

    user1 = User.objects.create_user(username="user1", password="test")
    user2 = User.objects.create_user(username="user2", password="test")
    user3 = User.objects.create_user(username="user3", password="test")

    booking1 = baker.make("booking.booking", event__date=timezone.now(), attended=True, user=user1)
    booking2 = baker.make("booking.booking", event__date=timezone.now(), attended=True, user=user2)
    booking3 = baker.make("booking.booking", event__date=timezone.now(), attended=True, user=user3)

    url = reverse("studioadmin:users_status")
    client.login(username=user.username, password="test")
    resp = client.get(url)
    assert resp.context["sidenav_selection"] == "attendance"
    assert resp.context["user_counts"][user1] == {
        booking1.event.event_type.subtype: 1,
        booking2.event.event_type.subtype: 0,
        booking3.event.event_type.subtype: 0,
    }
    assert resp.context["user_counts"][user2] == {
        booking1.event.event_type.subtype: 0,
        booking2.event.event_type.subtype: 1,
        booking3.event.event_type.subtype: 0,
    }
    assert resp.context["user_counts"][user3] == {
        booking1.event.event_type.subtype: 0,
        booking2.event.event_type.subtype: 0,
        booking3.event.event_type.subtype: 1,
    }


@pytest.mark.django_db
def test_attendance_list_with_dates(client):
    user = User.objects.create_user(username="staff", password="test")
    user.is_staff = True
    user.save()

    user1 = User.objects.create_user(username="user1", password="test")

    event = baker.make_recipe("booking.future_PC", date=datetime(2022, 10, 1, 10, 0, tzinfo=dt_timezone.utc))
    baker.make(
        "booking.booking", event=event, attended=True, user=user1
    )

    # dates miss booking
    url = reverse("studioadmin:users_status") + "?start_date=01 Jun 2022&end_date=10 Jun 2022"
    client.login(username=user.username, password="test")
    resp = client.get(url)

    assert resp.context["user_counts"] == {}

    # booking on end date
    url = reverse("studioadmin:users_status") + "?start_date=01 Jun 2022&end_date=01 Oct 2022"
    resp = client.get(url)
    assert resp.context["user_counts"] == {
        user1: {event.event_type.subtype: 1}
    }

    # post start/end
    url = reverse("studioadmin:users_status")
    resp = client.post(url, data={"start_date": "01 Jun 2022", "end_date": "01 Oct 2022"})
    assert resp.context["user_counts"] == {
        user1: {event.event_type.subtype: 1}
    }


@pytest.mark.django_db
@patch("booking.models.membership_models.StripeConnector", MockConnector)
def test_user_memberships_list(client, configured_stripe_user, purchasable_membership):
    user = User.objects.create_user(username="staff", password="test")
    user.is_staff = True
    user.save()
    baker.make("booking.UserMembership", membership=purchasable_membership, user=configured_stripe_user, subscription_status="active")
    url = reverse("studioadmin:user_memberships_list", args=(configured_stripe_user.id,))
    client.login(username=user.username, password="test")
    resp = client.get(url)
    assert resp.context["sidenav_selection"] == "users"
    assert resp.status_code == 200
    assert resp.context["user"] == configured_stripe_user
