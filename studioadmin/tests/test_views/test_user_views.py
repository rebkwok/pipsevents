import random

from datetime import timedelta
from mock import patch
from model_mommy import mommy

from django.conf import settings
from django.core.urlresolvers import reverse
from django.core import mail
from django.db.models import Q
from django.test import TestCase
from django.contrib.auth.models import Group, User, Permission
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone

from accounts.models import OnlineDisclaimer, PrintDisclaimer
from booking.models import Booking, Block, BlockType, EventType, WaitingListUser
from booking.tests.helpers import _create_session, format_content
from studioadmin.utils import int_str, chaffify
from studioadmin.views import (
    UserListView,
    user_blocks_view,
    user_bookings_view,
)
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
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_can_access(self):
        """
        test that the page can be accessed by a non-staff user who is in the
        instructor group
        """
        resp = self._get_response(self.instructor_user)
        self.assertEquals(resp.status_code, 200)

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user)
        self.assertEquals(resp.status_code, 200)

    def test_all_users_are_displayed(self):
        mommy.make_recipe('booking.user', _quantity=6)
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
        mommy.make_recipe(
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
        mommy.make_recipe(
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
        mommy.make_recipe(
            'booking.user',
            email='test12345678@longemail.com'
        )
        resp = self._get_response(self.staff_user)
        self.assertIn('test12345678@longemail...', resp.rendered_content)

    def test_display_regular_students(self):
        not_reg_student = mommy.make_recipe('booking.user')
        reg_student = mommy.make_recipe('booking.user')
        perm = Permission.objects.get(codename='is_regular_student')
        reg_student.user_permissions.add(perm)
        reg_student.save()

        resp = self._get_response(self.staff_user)
        resp.render()
        self.assertIn(
            'id="regular_student_button" value="{}">Yes'.format(reg_student.id),
            str(resp.content)
        )
        self.assertIn(
            'id="regular_student_button" value="{}">No'.format(not_reg_student.id),
            str(resp.content)
        )

    def test_regular_student_button_not_shown_for_instructors(self):
        not_reg_student = mommy.make_recipe('booking.user')
        reg_student = mommy.make_recipe('booking.user')
        perm = Permission.objects.get(codename='is_regular_student')
        reg_student.user_permissions.add(perm)
        reg_student.save()

        resp = self._get_response(self.staff_user)
        resp.render()
        self.assertIn(
            'id="regular_student_button" value="{}">Yes'.format(reg_student.id),
            str(resp.content)
        )
        self.assertIn(
            'id="regular_student_button" value="{}">No'.format(not_reg_student.id),
            str(resp.content)
        )

        resp = self._get_response(self.instructor_user)
        resp.render()
        self.assertNotIn(
            'id="regular_student_button" value="{}">Yes'.format(reg_student.id),
            str(resp.content)
        )
        self.assertNotIn(
            'id="regular_student_button" value="{}">No'.format(not_reg_student.id),
            str(resp.content)
        )

    def test_change_regular_student(self):
        not_reg_student = mommy.make_recipe('booking.user')
        reg_student = mommy.make_recipe('booking.user')
        perm = Permission.objects.get(codename='is_regular_student')
        reg_student.user_permissions.add(perm)
        reg_student.save()

        self.assertTrue(reg_student.has_perm('booking.is_regular_student'))
        self._get_response(
            self.staff_user, {'change_user': [reg_student.id]}
        )
        changed_student = User.objects.get(id=reg_student.id)
        self.assertFalse(changed_student.has_perm('booking.is_regular_student'))

        self.assertFalse(not_reg_student.has_perm('booking.is_regular_student'))
        self._get_response(
            self.staff_user, {'change_user': [not_reg_student.id]}
        )
        changed_student = User.objects.get(id=not_reg_student.id)
        self.assertTrue(changed_student.has_perm('booking.is_regular_student'))

    def test_cannot_remove_regular_student_for_superuser(self):
        reg_student = mommy.make_recipe('booking.user')
        superuser = mommy.make_recipe(
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
            reverse('studioadmin:users'), {'change_user': [reg_student.id]}
        )

        changed_student = User.objects.get(id=reg_student.id)
        self.assertFalse(changed_student.has_perm('booking.is_regular_student'))

        resp = self.client.get(
            reverse('studioadmin:users'), {'change_user': [superuser.id]},
            follow=True
        )

        # status hasn't changed
        self.assertTrue(superuser.has_perm('booking.is_regular_student'))
        self.assertIn(
            'Donald Duck (dd) is a superuser; you cannot remove permissions',
            format_content(resp.rendered_content)
        )

    def test_user_search(self):

        mommy.make_recipe(
            'booking.user', username='FooBar', first_name='Foo',
            last_name='Bar'
        )
        mommy.make_recipe(
            'booking.user', username='Testing1', first_name='Foo',
            last_name='Bar'
        )
        mommy.make_recipe(
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
        mommy.make_recipe(
            'booking.user', username='FooBar', first_name='AUser',
            last_name='Bar'
        )
        mommy.make_recipe(
            'booking.user', username='Testing1', first_name='aUser',
            last_name='Bar'
        )
        mommy.make_recipe(
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
        mommy.make_recipe(
            'booking.user', username='FooBar', first_name='AUser',
            last_name='Bar'
        )
        mommy.make_recipe(
            'booking.user', username='Testing1', first_name='aUser',
            last_name='Bar'
        )
        mommy.make_recipe(
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
            mommy.make_recipe('booking.user', first_name='{}Usr'.format(option))
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
        reg_student = mommy.make_recipe('booking.user')
        perm = Permission.objects.get(codename='is_regular_student')
        reg_student.user_permissions.add(perm)
        reg_student.save()

        resp = self._get_response(
            self.instructor_user, {'change_user': [reg_student.id]}
        )
        self.assertIn('This action is not permitted', resp.rendered_content)
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

        user_with_print_disclaimer = mommy.make_recipe('booking.user')
        mommy.make(PrintDisclaimer, user=user_with_print_disclaimer)
        user_with_online_disclaimer = mommy.make_recipe('booking.user')
        mommy.make(OnlineDisclaimer, user=user_with_online_disclaimer)
        user_with_no_disclaimer = mommy.make_recipe('booking.user')

        resp = self._get_response(superuser)
        self.assertIn(
            'id="print_disclaimer_button" value="{}">Yes'.format(user_with_print_disclaimer.id),
            str(resp.rendered_content)
        )
        self.assertIn(
            'id="print_disclaimer_button" value="{}">No'.format(user_with_no_disclaimer.id),
            str(resp.rendered_content)
        )
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
        user_with_print_disclaimer = mommy.make_recipe('booking.user')
        mommy.make(PrintDisclaimer, user=user_with_print_disclaimer)
        superuser = User.objects.create_superuser(
            username='super', email='super@test.com', password='test'
        )
        resp = self._get_response(superuser)
        self.assertIn(
            'id="print_disclaimer_button" value="{}">Yes'.format(
                user_with_print_disclaimer.id
            ),
            str(resp.rendered_content)
        )
        resp = self._get_response(self.staff_user)
        self.assertNotIn(
            'id="print_disclaimer_button" value="{}">Yes'.format(
                user_with_print_disclaimer.id
            ),
            str(resp.rendered_content)
        )
        resp = self._get_response(self.instructor_user)
        self.assertNotIn(
            'id="print_disclaimer_button" value="{}">Yes'.format(
                user_with_print_disclaimer.id
            ),
            str(resp.rendered_content)
        )

    def test_change_print_disclaimer(self):
        user_with_print_disclaimer = mommy.make_recipe('booking.user')
        print_disc = mommy.make(PrintDisclaimer, user=user_with_print_disclaimer)
        self.assertEqual(
            print_disc.id,
            user_with_print_disclaimer.print_disclaimer.id
        )

        self.assertEqual(PrintDisclaimer.objects.count(), 1)
        self._get_response(
            self.staff_user, {'change_print_disclaimer': [user_with_print_disclaimer.id]}
        )
        # print disclaimer has been deleted
        self.assertEqual(PrintDisclaimer.objects.count(), 0)

        self._get_response(
            self.staff_user, {'change_print_disclaimer': [user_with_print_disclaimer.id]}
        )
        self.assertEqual(PrintDisclaimer.objects.count(), 1)
        user = User.objects.get(id = user_with_print_disclaimer.id)
        # a new print disclaimer has been created
        self.assertNotEqual(
            print_disc.id,
            user.print_disclaimer.id
        )

    def test_instructor_cannot_change_print_disclaimer(self):
        user_with_print_disclaimer = mommy.make_recipe('booking.user')
        print_disc = mommy.make(PrintDisclaimer, user=user_with_print_disclaimer)
        self.assertEqual(
            print_disc.id,
            user_with_print_disclaimer.print_disclaimer.id
        )

        self.assertEqual(PrintDisclaimer.objects.count(), 1)
        self._get_response(
            self.staff_user, {'change_print_disclaimer': [user_with_print_disclaimer.id]}
        )
        # print disclaimer has been deleted
        self.assertEqual(PrintDisclaimer.objects.count(), 0)

        resp = self._get_response(
            self.instructor_user,
            {'change_print_disclaimer': [user_with_print_disclaimer.id]}
        )
        # not permitted - no print disclaimer created
        self.assertEqual(PrintDisclaimer.objects.count(), 0)
        self.assertIn('This action is not permitted', resp.rendered_content)

    def test_display_mailing_list_status(self):
        subscribed_user = mommy.make_recipe('booking.user')
        unsubscribed_user = mommy.make_recipe('booking.user')
        subscribed = mommy.make(Group, name='subscribed')
        subscribed.user_set.add(subscribed_user)

        resp = self._get_response(self.staff_user)
        self.assertIn('"subscribe_button" value="{}">Yes'.format(subscribed_user.id),
            resp.rendered_content
        )
        self.assertIn(
            'id="subscribe_button" value="{}">No'.format(unsubscribed_user.id),
            resp.rendered_content
        )

    def test_mailing_list_button_not_shown_for_instructors(self):
        subscribed_user = mommy.make_recipe('booking.user')
        unsubscribed_user = mommy.make_recipe('booking.user')
        subscribed = mommy.make(Group, name='subscribed')
        subscribed.user_set.add(subscribed_user)

        resp = self._get_response(self.staff_user)
        self.assertIn('"subscribe_button" value="{}">Yes'.format(subscribed_user.id),
            resp.rendered_content
        )
        self.assertIn(
            'id="subscribe_button" value="{}">No'.format(unsubscribed_user.id),
            resp.rendered_content
        )

        resp = self._get_response(self.instructor_user)
        resp.render()
        self.assertNotIn(
            'id="subscribe_button" value="{}">Yes'.format(subscribed_user.id),
            str(resp.content)
        )
        self.assertNotIn(
            'id="subscribe_button" value="{}">No'.format(unsubscribed_user.id),
            str(resp.content)
        )

    def test_change_mailing_list(self):
        subscribed_user = mommy.make_recipe('booking.user')
        unscubscribed_user = mommy.make_recipe('booking.user')
        subscribed = mommy.make(Group, name='subscribed')
        subscribed.user_set.add(subscribed_user)

        self.assertIn(subscribed, subscribed_user.groups.all())
        self._get_response(
            self.staff_user, {'change_subscription': [subscribed_user.id]}
        )
        changed_student = subscribed_user.refresh_from_db()
        self.assertNotIn(subscribed, subscribed_user.groups.all())

        self.assertNotIn(subscribed, unscubscribed_user.groups.all())
        self._get_response(
            self.staff_user, {'change_subscription': [unscubscribed_user.id]}
        )
        changed_student = unscubscribed_user.refresh_from_db()
        self.assertIn(subscribed, unscubscribed_user.groups.all())

    def test_instructor_cannot_change_mailing_list(self):
        subscribed_user = mommy.make_recipe('booking.user')
        subscribed = mommy.make(Group, name='subscribed')
        subscribed.user_set.add(subscribed_user)

        self.assertIn(subscribed, subscribed_user.groups.all())
        resp = self._get_response(
            self.instructor_user, {'change_subscription': [subscribed_user.id]}
        )

        self.assertIn('This action is not permitted', resp.rendered_content)
        subscribed_user.refresh_from_db()
        self.assertIn(subscribed, subscribed_user.groups.all())


class UserBookingsViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(UserBookingsViewTests, self).setUp()

        past_classes1 = mommy.make_recipe('booking.past_class', _quantity=2)
        past_classes2 = mommy.make_recipe('booking.past_class', _quantity=2)
        future_classes1 = mommy.make_recipe('booking.future_PC', _quantity=2)
        future_classes2 = mommy.make_recipe('booking.future_PC', _quantity=2)
        future_classes3 = mommy.make_recipe('booking.future_PC', _quantity=2)

        self.future_user_bookings = [
                mommy.make_recipe(
                'booking.booking', user=self.user, paid=True,
                payment_confirmed=True, event=event, status='OPEN',
            ) for event in future_classes1
        ]
        self.past_user_bookings = [
            mommy.make_recipe(
                'booking.booking', user=self.user, paid=True,
                payment_confirmed=True, event=event, status='OPEN'
            ) for event in past_classes1
        ]
        self.future_cancelled_bookings = [
                mommy.make_recipe(
                'booking.booking', user=self.user, paid=True,
                payment_confirmed=True, event=event, status='CANCELLED'
            ) for event in future_classes2
        ]
        self.past_cancelled_bookings = [
            mommy.make_recipe(
                'booking.booking', user=self.user, paid=True,
                payment_confirmed=True, event=event, status='CANCELLED'
            ) for event in past_classes2
        ]
        [
            mommy.make_recipe(
                'booking.booking', paid=True,
                payment_confirmed=True, event=event,
            ) for event in future_classes3
        ]

    def formset_data(self, extra_data={}):
        data = {
            'bookings-TOTAL_FORMS': 2,
            'bookings-INITIAL_FORMS': 2,
            'bookings-0-id': self.future_user_bookings[0].id,
            'bookings-0-event': self.future_user_bookings[0].event.id,
            'bookings-0-status': self.future_user_bookings[0].status,
            'bookings-0-paid': self.future_user_bookings[0].paid,
            'bookings-1-id': self.future_user_bookings[1].id,
            'bookings-1-event': self.future_user_bookings[1].event.id,
            'bookings-1-status': self.future_user_bookings[1].status,
            'bookings-1-deposit_paid': self.future_user_bookings[1].deposit_paid,
            'bookings-1-paid': self.future_user_bookings[1].paid,
            }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def _get_response(self, user, user_id, booking_status='future'):
        url = reverse(
            'studioadmin:user_bookings_list',
            kwargs={'user_id': user_id, 'booking_status': booking_status}
        )
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return user_bookings_view(
            request, user_id, booking_status=booking_status
        )

    def _post_response(
        self, user, user_id, form_data, booking_status='future'
        ):
        url = reverse(
            'studioadmin:user_bookings_list',
            kwargs={'user_id': user_id, 'booking_status': booking_status}
        )
        form_data['booking_status'] = [booking_status]
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return user_bookings_view(
            request, user_id, booking_status=booking_status
        )

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse(
            'studioadmin:user_bookings_list',
            kwargs={'user_id': self.user.id, 'booking_status': 'future'}
        )
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user, self.user.id)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_cannot_access(self):
        """
        test that the page redirects if user is in the instructor group but is
        not a staff user
        """
        resp = self._get_response(self.instructor_user, self.user.id)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user, self.user.id)
        self.assertEquals(resp.status_code, 200)

    def test_view_users_bookings(self):
        """
        Test only user's bookings for future events shown by default
        """
        self.assertEqual(Booking.objects.count(), 10)
        resp = self._get_response(self.staff_user, self.user.id)
        # get all but last form (last form is the empty extra one)
        booking_forms = resp.context_data['userbookingformset'].forms[:-1]
        # show future bookings, both open and cancelled
        self.assertEqual(
            len(booking_forms),
            len(self.future_user_bookings) + len(self.future_cancelled_bookings)
        )

        self.assertEqual(
            sorted([booking.instance.id for booking in booking_forms]),
            sorted(
                [bk.id for bk in
                 self.future_user_bookings + self.future_cancelled_bookings]
            )
        )

    def test_filter_bookings_by_booking_status(self):

        # future bookings
        resp = self._get_response(self.staff_user, self.user.id, 'future')
        # get all but last form (last form is the empty extra one)
        booking_forms = resp.context_data['userbookingformset'].forms[:-1]
        self.assertEqual(len(booking_forms), 4)
        self.assertEqual(
            [booking.instance for booking in booking_forms],
            self.future_user_bookings + self.future_cancelled_bookings
        )

        # past bookings
        resp = self._get_response(self.staff_user, self.user.id, 'past')
        # get all but last form (last form is the empty extra one)
        booking_forms = resp.context_data['userbookingformset'].forms[:-1]
        self.assertEqual(len(booking_forms), 4)
        self.assertEqual(
            sorted([booking.instance.id for booking in booking_forms]),
            sorted([
                       bk.id for bk in
                       self.past_user_bookings + self.past_cancelled_bookings
                    ])
        )

    def test_can_update_booking(self):
        self.assertFalse(self.future_user_bookings[0].deposit_paid)
        self.assertTrue(self.future_user_bookings[0].paid)
        form_data = self.formset_data({'bookings-0-paid': False,
        'formset_submitted': 'Submit'})

        self._post_response(self.staff_user, self.user.id, form_data=form_data)
        booking = Booking.objects.get(id=self.future_user_bookings[0].id)
        self.assertFalse(booking.deposit_paid)
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)

    def test_can_update_booking_deposit_paid(self):

        unpaid_booking = mommy.make_recipe(
            'booking.booking', user=self.user,
            event__date=timezone.now()+timedelta(3),
            status='OPEN',
        )
        self.assertFalse(unpaid_booking.paid)
        self.assertFalse(unpaid_booking.deposit_paid)

        extra_data = {
            'bookings-TOTAL_FORMS': 3,
            'bookings-INITIAL_FORMS': 3,
            'bookings-2-id': unpaid_booking.id,
            'bookings-2-event': unpaid_booking.event.id,
            'bookings-2-status': unpaid_booking.status,
            'bookings-2-deposit_paid': True,
            'bookings-2-paid': unpaid_booking.paid,
            'formset_submitted': 'Submit'
        }

        form_data = self.formset_data(extra_data)

        self._post_response(self.staff_user, self.user.id, form_data=form_data)
        unpaid_booking.refresh_from_db()
        self.assertTrue(unpaid_booking.deposit_paid)
        self.assertFalse(unpaid_booking.paid)
        self.assertFalse(unpaid_booking.payment_confirmed)

    def test_can_add_booking(self):
        self.assertEqual(Booking.objects.count(), 10)
        event = mommy.make_recipe('booking.future_EV')
        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-2-event': event.id,
                'bookings-2-status': 'OPEN'
            }
        )
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )
        self.assertEqual(Booking.objects.count(), 11)

        bookings = Booking.objects.filter(event=event)
        self.assertEqual(len(bookings), 1)

        booking = bookings[0]
        self.assertEqual(booking.user, self.user)

    def test_changing_booking_status_updates_payment_status_also(self):
        self.assertEqual(self.future_user_bookings[0].status, 'OPEN')
        self.assertTrue(self.future_user_bookings[0].paid)
        self.assertTrue(self.future_user_bookings[0].payment_confirmed)
        form_data = self.formset_data(
            {
                'bookings-0-status': 'CANCELLED'
            }
        )
        self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )

        booking = Booking.objects.get(id=self.future_user_bookings[0].id)
        self.assertEqual(booking.status, 'CANCELLED')
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)

    def test_changing_booking_status_to_cancelled_removed_block(self):
        block = mommy.make_recipe(
            'booking.block', user=self.user
        )
        booking = mommy.make_recipe(
            'booking.booking',
            event__event_type=block.block_type.event_type, block=block,
            user=self.user, paid=True, payment_confirmed=True
        )

        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-INITIAL_FORMS': 3,
                'bookings-2-id': booking.id,
                'bookings-2-event': booking.event.id,
                'bookings-2-status': 'CANCELLED',
                'bookings-2-block': block.id,
                'bookings-2-paid': booking.paid
            }
        )

        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'CANCELLED')
        self.assertIsNone(booking.block)
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)

    def test_can_assign_booking_to_available_block(self):
        booking = mommy.make_recipe(
            'booking.booking',
            event__date=timezone.now()+timedelta(2),
            user=self.user,
            paid=False,
            payment_confirmed=False
        )
        block = mommy.make_recipe(
            'booking.block', block_type__event_type=booking.event.event_type,
            user=self.user
        )
        self.assertFalse(booking.block)
        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-INITIAL_FORMS': 3,
                'bookings-2-id': booking.id,
                'bookings-2-event': booking.event.id,
                'bookings-2-status': booking.status,
                'bookings-2-block': block.id
            }
        )
        self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )

        booking = Booking.objects.get(id=booking.id)
        self.assertEqual(booking.block, block)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)

    def test_create_new_block_booking(self):
        event1 = mommy.make_recipe('booking.future_EV')
        block1 = mommy.make_recipe(
            'booking.block', block_type__event_type=event1.event_type,
            user=self.user
        )

        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-2-event': event1.id,
                'bookings-2-status': 'OPEN',
                'bookings-2-block': block1.id
            }
        )
        self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )
        booking = Booking.objects.get(event=event1)
        self.assertEqual(booking.block, block1)

    def test_cannot_create_new_block_booking_with_wrong_blocktype(self):
        event1 = mommy.make_recipe('booking.future_EV')
        event2 = mommy.make_recipe('booking.future_EV')

        block1 = mommy.make_recipe(
            'booking.block', block_type__event_type=event1.event_type,
            user=self.user
        )
        block2 = mommy.make_recipe(
            'booking.block', block_type__event_type=event2.event_type,
            user=self.user
        )
        self.assertEqual(Booking.objects.count(), 10)
        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-2-event': event1.id,
                'bookings-2-status': 'OPEN',
                'bookings-2-block': block2.id
            }
        )
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )
        errors = resp.context_data['userbookingformset'].errors
        self.assertIn(
            {
                'block': ['{} (type "{}") can only be block-booked with a ' \
                          '"{}" block type.'.format(
                    event1, event1.event_type, event1.event_type
                )] \
            },
            errors)
        bookings = Booking.objects.filter(event=event1)
        self.assertEqual(len(bookings), 0)
        self.assertEqual(Booking.objects.count(), 10)

    def test_cannot_overbook_block(self):
        event_type = mommy.make_recipe('booking.event_type_PC')
        event = mommy.make_recipe('booking.future_EV', event_type=event_type)
        event1 = mommy.make_recipe('booking.future_EV', event_type=event_type)
        block = mommy.make_recipe(
            'booking.block', block_type__event_type=event_type,
            block_type__size=1,
            user=self.user
        )
        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-2-event': event.id,
                'bookings-2-status': 'OPEN',
                'bookings-2-block': block.id
            }
        )

        # create new booking with this block
        self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )
        self.assertEqual(Booking.objects.count(), 11)
        bookings = Booking.objects.filter(event=event)
        self.assertEqual(len(bookings), 1)
        new_booking = bookings[0]
        self.assertEqual(new_booking.block, block)

        # block is now full
        block = Block.objects.get(id=block.id)
        self.assertTrue(block.full)

        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 4,
                'bookings-INITIAL_FORMS': 3,
                'bookings-2-id': new_booking.id,
                'bookings-2-event': event.id,
                'bookings-2-status': new_booking.status,
                'bookings-3-event': event1.id,
                'bookings-3-block': block.id,
                'bookings-3-status': 'OPEN'
            }
        )
        # try to create new booking with this block
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )
        errors = resp.context_data['userbookingformset'].errors
        self.assertIn(
            {
                'block': ['Block selected for {} is now full. ' \
                            'Add another block for this user or confirm ' \
                            'payment was made directly.'.format(event1)] \
            },
            errors)

    def test_cannot_create_new_block_booking_when_no_available_blocktype(self):
        event1 = mommy.make_recipe('booking.future_EV')
        event2 = mommy.make_recipe('booking.future_PC')

        block1 = mommy.make_recipe(
            'booking.block', block_type__event_type=event1.event_type,
            user=self.user
        )

        self.assertEqual(Booking.objects.count(), 10)
        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-2-event': event2.id,
                'bookings-2-status': 'OPEN',
                'bookings-2-block': block1.id
            }
        )
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )
        errors = resp.context_data['userbookingformset'].errors
        self.assertIn(
            {
                'block': ['{} ({} type "{}") cannot be ' \
                            'block-booked'.format(
                    event2, 'class', event2.event_type
                )]
            },
            errors)
        bookings = Booking.objects.filter(event=event2)
        self.assertEqual(len(bookings), 0)
        self.assertEqual(Booking.objects.count(), 10)

    def test_cannot_add_booking_to_full_event(self):
        event = mommy.make_recipe('booking.future_EV', max_participants=2)
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-2-event': event.id,
                'bookings-2-status': 'OPEN'
            }
        )
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )

        self.assertIn(
            'Please correct the following errors:__all__Attempting to create '
            'booking for full event',
            format_content(resp.rendered_content)
        )
        # new booking has not been made
        bookings = Booking.objects.filter(event=event)
        self.assertEqual(len(bookings), 2)

    def test_cannot_make_block_booking_unpaid(self):
        event1 = mommy.make_recipe('booking.future_EV')
        block1 = mommy.make_recipe(
            'booking.block', block_type__event_type=event1.event_type,
            user=self.user
        )
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, block=block1, event=event1,
        )
        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-INITIAL_FORMS': 3,
                'bookings-2-id': booking.id,
                'bookings-2-event': event1.id,
                'bookings-2-status': booking.status,
                'bookings-2-paid': False,
                'bookings-2-block': block1.id,
            }
        )

        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )
        errors = resp.context_data['userbookingformset'].errors
        self.assertIn(
            {
                'paid': [
                    'Cannot make block booking for {} unpaid'.format(event1)
                ]
            },
            errors
        )

    def test_formset_unchanged(self):
        """
        test formset submitted unchanged redirects back to user bookings list
        """
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=self.formset_data(
                {'formset_submitted': 'Submit'}
            )
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url,
            reverse(
                'studioadmin:user_bookings_list',
                kwargs={'user_id': self.user.id, 'booking_status': 'future'}
            )
        )

    def test_create_new_booking_as_free_class(self):
        event1 = mommy.make_recipe(
            'booking.future_PC',
            event_type__subtype='Pole level class'
        )
        block1 = mommy.make_recipe(
            'booking.block', block_type__event_type=event1.event_type,
            user=self.user
        )

        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-2-event': event1.id,
                'bookings-2-status': 'OPEN',
                'bookings-2-free_class': True
            }
        )
        self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )
        booking = Booking.objects.get(event=event1)
        self.assertTrue(booking.free_class)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)

    def test_cannot_assign_free_class_to_normal_block(self):
        event1 = mommy.make_recipe(
            'booking.future_PC',
            event_type__subtype='Pole level class'
        )
        block1 = mommy.make_recipe(
            'booking.block', block_type__event_type=event1.event_type,
            user=self.user
        )
        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-2-event': event1.id,
                'bookings-2-status': 'OPEN',
                'bookings-2-block': block1.id,
                'bookings-2-free_class': True
            }
        )
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )
        errors = resp.context_data['userbookingformset'].errors
        self.assertIn(
            {
                'free_class': ['"Free class" cannot be assigned to a block.']
            },
            errors)
        bookings = Booking.objects.filter(event=event1)
        self.assertEqual(len(bookings), 0)

    def test_confirmation_email_sent_if_data_changed(self):
        form_data = self.formset_data(
            {
                'bookings-0-status': 'CANCELLED',
                'bookings-0-send_confirmation': 'on',
            }
        )
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_confirmation_email_not_sent_if_data_unchanged(self):
        form_data=self.formset_data(
            {'formset_submitted': 'Submit',
            'bookings-0-send_confirmation': 'on'}
        )
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
            )
        self.assertEqual(len(mail.outbox), 0)

    def test_cannot_assign_cancelled_booking_to_available_block(self):
        booking = mommy.make_recipe(
            'booking.booking',
            event__date=timezone.now()+timedelta(2),
            user=self.user,
            paid=False,
            payment_confirmed=False,
            status='CANCELLED'
        )
        block = mommy.make_recipe(
            'booking.block', block_type__event_type=booking.event.event_type,
            user=self.user
        )
        self.assertFalse(booking.block)
        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-INITIAL_FORMS': 3,
                'bookings-2-id': booking.id,
                'bookings-2-event': booking.event.id,
                'bookings-2-status': booking.status,
                'bookings-2-block': block.id
            }
        )
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )

        booking.refresh_from_db()
        self.assertFalse(booking.block)
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)

        errors = resp.context_data['userbookingformset'].errors
        self.assertIn(
            {
                'block': [
                    'A cancelled booking cannot be assigned to a ' \
                    'block.  Please change status of booking for {} to "OPEN" ' \
                    'before assigning block'.format(booking.event)
                ]
            },
            errors)

    def test_cannot_assign_booking_for_cancelled_event_to_available_block(self):
        event = mommy.make_recipe('booking.future_EV', cancelled=True)
        booking = mommy.make_recipe(
            'booking.booking',
            event=event,
            user=self.user,
        )
        block = mommy.make_recipe(
            'booking.block', block_type__event_type=event.event_type,
            user=self.user
        )
        self.assertFalse(booking.block)
        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-INITIAL_FORMS': 3,
                'bookings-2-id': booking.id,
                'bookings-2-event': event.id,
                'bookings-2-status': booking.status,
                'bookings-2-block': block.id
            }
        )
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )

        booking.refresh_from_db()
        self.assertFalse(booking.block)

        errors = resp.context_data['userbookingformset'].errors
        self.assertIn(
            {'block': [
                'Cannot assign booking for cancelled event {} to a '
                'block'.format(event)
                ],
             'status': [
                'Cannot reopen booking for cancelled event {}'.format(event)
                ]},
            errors
        )

    def test_reopen_booking_for_cancelled_event(self):
        event = mommy.make_recipe('booking.future_EV', cancelled=True)
        booking = mommy.make_recipe(
            'booking.booking',
            event=event,
            user=self.user,
            status="CANCELLED"
        )

        self.assertFalse(booking.block)
        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-INITIAL_FORMS': 3,
                'bookings-2-id': booking.id,
                'bookings-2-event': event.id,
                'bookings-2-status':'OPEN',
            }
        )
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'CANCELLED')

        errors = resp.context_data['userbookingformset'].errors
        self.assertIn(
            {
                'status': [
                    'Cannot reopen booking for cancelled event {}'.format(event)
                ]
            },
            errors)

    def test_assign_booking_for_cancelled_event_to_free_class(self):
        event = mommy.make_recipe('booking.future_EV', cancelled=True)
        booking = mommy.make_recipe(
            'booking.booking',
            event=event,
            user=self.user,
            status='CANCELLED'
        )

        self.assertFalse(booking.block)
        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-INITIAL_FORMS': 3,
                'bookings-2-id': booking.id,
                'bookings-2-event': event.id,
                'bookings-2-free_class': True,
                'bookings-2-status': booking.status
            }
        )
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )

        booking.refresh_from_db()
        self.assertFalse(booking.free_class)

        errors = resp.context_data['userbookingformset'].errors
        self.assertIn(
            {
                'free_class': [
                    'Cannot assign booking for cancelled event {} as free '
                    'class'.format(event)
                ]
            },
            errors)

    def test_assign_booking_for_cancelled_event_as_paid(self):
        event = mommy.make_recipe('booking.future_EV', cancelled=True)
        booking = mommy.make_recipe(
            'booking.booking',
            event=event,
            user=self.user,
            status='CANCELLED'
        )

        self.assertFalse(booking.block)
        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-INITIAL_FORMS': 3,
                'bookings-2-id': booking.id,
                'bookings-2-event': event.id,
                'bookings-2-paid': True,
                'bookings-2-status': booking.status
            }
        )
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )

        booking.refresh_from_db()
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)

        errors = resp.context_data['userbookingformset'].errors
        self.assertIn(
            {
                'paid': [
                    'Cannot assign booking for cancelled event {} as '
                    'paid'.format(event)
                ]
            },
            errors)

    def test_assign_booking_for_cancelled_event_as_deposit_paid(self):
        event = mommy.make_recipe('booking.future_EV', cancelled=True)
        booking = mommy.make_recipe(
            'booking.booking',
            event=event,
            user=self.user,
            status='CANCELLED'
        )

        self.assertFalse(booking.block)
        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-INITIAL_FORMS': 3,
                'bookings-2-id': booking.id,
                'bookings-2-event': event.id,
                'bookings-2-deposit_paid': True,
                'bookings-2-status': booking.status
            }
        )
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )

        booking.refresh_from_db()
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)

        errors = resp.context_data['userbookingformset'].errors
        self.assertIn(
            {
                'deposit_paid': [
                    'Cannot assign booking for cancelled event {} as '
                    'deposit paid'.format(event)
                ]
            },
            errors)

    def test_can_assign_free_class_to_free_class_block(self):
        event1 = mommy.make_recipe(
            'booking.future_PC',
            event_type__subtype='Pole level class'
        )
        free_blocktype = mommy.make_recipe(
            'booking.blocktype', size=1, cost=0,
            event_type=event1.event_type, identifier='free class'
        )
        free_block = mommy.make_recipe(
            'booking.block', block_type=free_blocktype,
            user=self.user
        )
        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-2-event': event1.id,
                'bookings-2-status': 'OPEN',
                'bookings-2-block': free_block.id,
                'bookings-2-free_class': True
            }
        )
        self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )
        bookings = Booking.objects.filter(event=event1)
        self.assertEqual(len(bookings), 1)

    def test_reopen_cancelled_booking(self):
        booking = self.future_user_bookings[0]
        booking.status = 'CANCELLED'
        booking.paid = False
        booking.payment_confirmed = False
        booking.save()
        self.assertEqual(booking.status, 'CANCELLED')
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)
        form_data = self.formset_data(
            {
                'bookings-0-status': 'OPEN'
            }
        )
        self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'OPEN')
        # payment status not changed unless specifically updated in form
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)

    def test_remove_block_from_booking(self):
        booking = self.future_user_bookings[0]
        block = mommy.make_recipe(
            'booking.block_5', user=booking.user,
            block_type__event_type=booking.event.event_type
        )
        booking.block = block
        booking.save()
        self.assertEqual(booking.block, block)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)
        form_data = self.formset_data(
            {
                'bookings-0-block': ''
            }
        )
        self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )

        booking.refresh_from_db()
        self.assertEqual(booking.block, None)
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)

    def test_new_booking_uses_last_in_10_blocks_block(self):
        """
        Checking for and creating the free block is done at the model level;
        check this is triggered from the studioadmin user bookings changes too
        """
        event_type = mommy.make(
            EventType, event_type='CL', subtype='Pole level class'
        )
        mommy.make_recipe(
            'booking.blocktype', size=1, cost=0,
            event_type=event_type, identifier='free class'
        )

        event = mommy.make_recipe('booking.future_PC', event_type=event_type)
        block = mommy.make_recipe(
            'booking.block_10', user=self.user,
            block_type__event_type=event_type, paid=True,
            start_date=timezone.now()
        )
        mommy.make_recipe(
            'booking.booking', user=self.user, block=block, _quantity=9
        )

        self.assertEqual(Block.objects.count(), 1)

        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-2-event': event.id,
                'bookings-2-status': 'OPEN',
                'bookings-2-block': block.id,
                'booking_status': 'OPEN'
            }
        )
        self.client.login(username=self.staff_user.username, password='test')
        url = reverse(
            'studioadmin:user_bookings_list',
            kwargs={'user_id': self.user.id, 'booking_status': 'OPEN'}
        )
        resp = self.client.post(url, form_data, follow=True)

        booking = Booking.objects.last()
        self.assertEqual(booking.block, block)
        self.assertEqual(Block.objects.count(), 2)
        self.assertTrue(block.children.exists())
        self.assertIn(
            'You have added the last booking to a 10 class block; '
            'free class block has been created.',
            format_content(resp.rendered_content)
        )

    def test_using_last_in_10_blocks_block_free_block_already_exists(self):
        """
        Also done at the model level; if free class block already exists, a
        new one is not created
        Check correct messages shown in content
        """
        event_type = mommy.make(
            EventType, event_type='CL', subtype='Pole level class'
        )
        free_blocktype = mommy.make_recipe(
            'booking.blocktype', size=1, cost=0,
            event_type=event_type, identifier='free class'
        )

        event = mommy.make_recipe('booking.future_PC', event_type=event_type)
        block = mommy.make_recipe(
            'booking.block_10', user=self.user,
            block_type__event_type=event_type, paid=True,
            start_date=timezone.now()
        )
        # make free block on this block
        mommy.make(
            Block, user=self.user, block_type=free_blocktype, parent=block
        )

        mommy.make_recipe(
            'booking.booking', user=self.user, block=block, _quantity=9
        )

        self.assertEqual(Block.objects.count(), 2)

        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-2-event': event.id,
                'bookings-2-status': 'OPEN',
                'bookings-2-block': block.id,
                'booking_status': 'OPEN'
            }
        )
        self.client.login(username=self.staff_user.username, password='test')
        url = reverse(
            'studioadmin:user_bookings_list',
            kwargs={'user_id': self.user.id, 'booking_status': 'OPEN'}
        )
        resp = self.client.post(url, form_data, follow=True)

        booking = Booking.objects.last()
        self.assertEqual(booking.block, block)
        self.assertEqual(Block.objects.count(), 2)
        self.assertTrue(block.children.exists())
        self.assertNotIn(
            'You have added the last booking to a 10 class block; '
            'free class block has been created.',
            format_content(resp.rendered_content)
        )

    @patch('studioadmin.views.users.send_mail')
    def test_email_errors_when_sending_confirmation(self, mock_send_emails):
        mock_send_emails.side_effect = Exception('Error sending mail')
        form_data = self.formset_data(
            {
                'bookings-0-status': 'CANCELLED',
                'bookings-0-send_confirmation': 'on',
            }
        )
        booking = self.future_user_bookings[0]
        self.assertEqual(booking.status, 'OPEN')
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )

        # email to support only
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [settings.SUPPORT_EMAIL])
        # email failed but changes still made
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'CANCELLED')

    @patch('studioadmin.views.users.send_mail')
    @patch('booking.email_helpers.send_mail')
    def test_email_errors_when_sending_confirmation_and_support_mail(
            self, mock_send_emails, mock_send_emails1
    ):
        mock_send_emails.side_effect = Exception('Error sending mail')
        mock_send_emails1.side_effect = Exception('Error sending mail')
        form_data = self.formset_data(
            {
                'bookings-0-status': 'CANCELLED',
                'bookings-0-send_confirmation': 'on',
            }
        )
        booking = self.future_user_bookings[0]
        self.assertEqual(booking.status, 'OPEN')
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )

        # no email
        self.assertEqual(len(mail.outbox), 0)
        # email failed but changes still made
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'CANCELLED')

    def test_cancel_booking_for_full_event_emails_waiting_list(self):
        event = mommy.make_recipe(
            'booking.future_EV', name='Test event', max_participants=2
        )
        user = mommy.make_recipe('booking.user')
        booking = mommy.make_recipe(
            'booking.booking', user=user, event=event, status='OPEN')

        # fill event and make a waiting list
        mommy.make_recipe('booking.booking', event=event)
        user1 = mommy.make_recipe('booking.user', email='test@test.com')
        mommy.make(WaitingListUser, event=event, user=user1)

        data = {
            'bookings-TOTAL_FORMS': 1,
            'bookings-INITIAL_FORMS': 1,
            'bookings-0-id': booking.id,
            'bookings-0-event': event.id,
            'bookings-0-status': 'CANCELLED',
            'bookings-0-paid': booking.paid,
            }

        resp = self._post_response(
            self.staff_user, user.id, form_data=data
        )

        booking.refresh_from_db()
        # booking now cancelled
        self.assertEqual(booking.status, 'CANCELLED')

        # waiting list emailed
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].bcc, ['test@test.com'])
        self.assertEqual(
            mail.outbox[0].subject,
            '{} {}'.format(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, event)
        )
        self.assertIn(
            'A space has become available for {}'.format(event),
            mail.outbox[0].body
        )

    @patch('studioadmin.views.users.send_waiting_list_email')
    def test_email_errors_when_sending_waiting_list_email(self, mock_send):
        mock_send.side_effect = Exception('Error sending mail')
        event = mommy.make_recipe(
            'booking.future_EV', name='Test event', max_participants=2
        )
        user = mommy.make_recipe('booking.user')
        booking = mommy.make_recipe(
            'booking.booking', user=user, event=event, status='OPEN')

        # fill event and make a waiting list
        mommy.make_recipe('booking.booking', event=event)
        user1 = mommy.make_recipe('booking.user', email='test@test.com')
        mommy.make(WaitingListUser, event=event, user=user1)

        data = {
            'bookings-TOTAL_FORMS': 1,
            'bookings-INITIAL_FORMS': 1,
            'bookings-0-id': booking.id,
            'bookings-0-event': event.id,
            'bookings-0-status': 'CANCELLED',
            'bookings-0-paid': booking.paid,
            }

        resp = self._post_response(
            self.staff_user, user.id, form_data=data
        )

        booking.refresh_from_db()
        # booking now cancelled
        self.assertEqual(booking.status, 'CANCELLED')

        # email only sent to support
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [settings.SUPPORT_EMAIL])

        self.assertEqual(
            mail.outbox[0].subject,
            '{} An error occurred! (Studioadmin user booking list - waiting '
            'list email)'.format(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX)
        )

    @patch('booking.email_helpers.send_mail')
    @patch('studioadmin.views.users.send_waiting_list_email')
    def test_email_errors_when_sending_waiting_list_email_and_support(
            self, mock_send, mock_send_mail
    ):
        mock_send.side_effect = Exception('Error sending mail')
        mock_send_mail.side_effect = Exception('Error sending mail')
        event = mommy.make_recipe(
            'booking.future_EV', name='Test event', max_participants=2
        )
        user = mommy.make_recipe('booking.user')
        booking = mommy.make_recipe(
            'booking.booking', user=user, event=event, status='OPEN')

        # fill event and make a waiting list
        mommy.make_recipe('booking.booking', event=event)
        user1 = mommy.make_recipe('booking.user', email='test@test.com')
        mommy.make(WaitingListUser, event=event, user=user1)

        data = {
            'bookings-TOTAL_FORMS': 1,
            'bookings-INITIAL_FORMS': 1,
            'bookings-0-id': booking.id,
            'bookings-0-event': event.id,
            'bookings-0-status': 'CANCELLED',
            'bookings-0-paid': booking.paid,
            }

        resp = self._post_response(
            self.staff_user, user.id, form_data=data
        )

        # no email sent
        self.assertEqual(len(mail.outbox), 0)

        booking.refresh_from_db()
        # but changes still make
        self.assertEqual(booking.status, 'CANCELLED')

    def test_cancel_direct_paid_CL_or_RH_creates_transfer_block(self):
        self.assertFalse(
            BlockType.objects.filter(identifier='transferred').exists()
        )
        cl_booking = mommy.make_recipe(
            'booking.booking',
            event__event_type__event_type='CL',
            user=self.user, paid=True, payment_confirmed=True
        )
        rh_booking = mommy.make_recipe(
            'booking.booking',
            event__event_type__event_type='RH',
            user=self.user, paid=True, payment_confirmed=True
        )
        ev_booking = mommy.make_recipe(
            'booking.booking',
            event__event_type__event_type='EV',
            user=self.user, paid=True, payment_confirmed=True
        )

        data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 5,
                'bookings-INITIAL_FORMS': 5,
                'bookings-2-id': cl_booking.id,
                'bookings-2-event': cl_booking.event.id,
                'bookings-2-status': 'CANCELLED',
                'bookings-2-paid': cl_booking.paid,
                'bookings-3-id': rh_booking.id,
                'bookings-3-event': rh_booking.event.id,
                'bookings-3-status': 'CANCELLED',
                'bookings-3-paid': rh_booking.paid,
                'bookings-4-id': ev_booking.id,
                'bookings-4-event': ev_booking.event.id,
                'bookings-4-status': 'CANCELLED',
                'bookings-4-paid': ev_booking.paid,
                'booking_status': ['future']
            }
        )

        self.client.login(username=self.staff_user.username, password='test')
        self.client.post(
            reverse(
                'studioadmin:user_bookings_list',
                args=[self.user.id, 'future']
            ),
            data
        )

        self.assertTrue(
            BlockType.objects.filter(identifier='transferred').exists()
        )
        self.assertEqual(
            Block.objects.filter(
                block_type__identifier='transferred', user=self.user
            ).count(),
            2
        )

        cl_booking.refresh_from_db()
        self.assertEqual(cl_booking.status, 'CANCELLED')
        self.assertFalse(cl_booking.paid)
        self.assertFalse(cl_booking.payment_confirmed)
        cl_block = Block.objects.get(
            user=self.user, transferred_booking_id=cl_booking.id,
        )
        self.assertEqual(
            cl_block.block_type.event_type, cl_booking.event.event_type
        )

        rh_booking.refresh_from_db()
        self.assertEqual(rh_booking.status, 'CANCELLED')
        self.assertFalse(rh_booking.paid)
        self.assertFalse(rh_booking.payment_confirmed)
        rh_block = Block.objects.get(
            user=self.user, transferred_booking_id=rh_booking.id,
        )
        self.assertEqual(
            rh_block.block_type.event_type, rh_booking.event.event_type
        )

        ev_booking.refresh_from_db()
        self.assertEqual(ev_booking.status, 'CANCELLED')
        self.assertFalse(ev_booking.paid)
        self.assertFalse(ev_booking.payment_confirmed)

        with self.assertRaises(Block.DoesNotExist):
            Block.objects.get(
                user=self.user, transferred_booking_id=ev_booking.id,
            )

    def test_cancel_free_non_block_CL_or_RH_creates_transfer_block(self):
        self.assertFalse(
            BlockType.objects.filter(identifier='transferred').exists()
        )
        cl_booking = mommy.make_recipe(
            'booking.booking',
            event__event_type__event_type='CL',
            user=self.user, paid=True, payment_confirmed=True, free_class=True
        )
        rh_booking = mommy.make_recipe(
            'booking.booking',
            event__event_type__event_type='RH',
            user=self.user, paid=True, payment_confirmed=True, free_class=True
        )
        ev_booking = mommy.make_recipe(
            'booking.booking',
            event__event_type__event_type='EV',
            user=self.user, paid=True, payment_confirmed=True, free_class=True
        )

        data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 5,
                'bookings-INITIAL_FORMS': 5,
                'bookings-2-id': cl_booking.id,
                'bookings-2-event': cl_booking.event.id,
                'bookings-2-status': 'CANCELLED',
                'bookings-2-paid': cl_booking.paid,
                'bookings-2-free_class': cl_booking.free_class,
                'bookings-3-id': rh_booking.id,
                'bookings-3-event': rh_booking.event.id,
                'bookings-3-status': 'CANCELLED',
                'bookings-3-paid': rh_booking.paid,
                'bookings-3-free_class': rh_booking.free_class,
                'bookings-4-id': ev_booking.id,
                'bookings-4-event': ev_booking.event.id,
                'bookings-4-status': 'CANCELLED',
                'bookings-4-paid': ev_booking.paid,
                'bookings-4-free_class': ev_booking.free_class,
                'booking_status': ['future']
            }
        )

        self.client.login(username=self.staff_user.username, password='test')
        self.client.post(
            reverse(
                'studioadmin:user_bookings_list',
                args=[self.user.id, 'future']
            ),
            data, follow=True
        )
        self.assertTrue(
            BlockType.objects.filter(identifier='transferred').exists()
        )
        self.assertEqual(
            Block.objects.filter(
                block_type__identifier='transferred', user=self.user
            ).count(),
            2
        )

        cl_booking.refresh_from_db()
        self.assertEqual(cl_booking.status, 'CANCELLED')
        self.assertFalse(cl_booking.paid)
        self.assertFalse(cl_booking.payment_confirmed)
        cl_block = Block.objects.get(
            user=self.user, transferred_booking_id=cl_booking.id,
        )
        self.assertEqual(
            cl_block.block_type.event_type, cl_booking.event.event_type
        )

        rh_booking.refresh_from_db()
        self.assertEqual(rh_booking.status, 'CANCELLED')
        self.assertFalse(rh_booking.paid)
        self.assertFalse(rh_booking.payment_confirmed)
        rh_block = Block.objects.get(
            user=self.user, transferred_booking_id=rh_booking.id,
        )
        self.assertEqual(
            rh_block.block_type.event_type, rh_booking.event.event_type
        )

        ev_booking.refresh_from_db()
        self.assertEqual(ev_booking.status, 'CANCELLED')
        self.assertFalse(ev_booking.paid)
        self.assertFalse(ev_booking.payment_confirmed)

        with self.assertRaises(Block.DoesNotExist):
            Block.objects.get(
                user=self.user, transferred_booking_id=ev_booking.id,
            )

    def test_cancel_block_booked_CL_does_not_creates_transfer_block(self):
        block = mommy.make(
            Block,
            user=self.user, block_type__event_type__event_type='CL'
        )
        cl_booking = mommy.make_recipe(
            'booking.booking',
            event__event_type__event_type='CL', block=block,
            user=self.user, paid=True, payment_confirmed=True
        )

        data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-INITIAL_FORMS': 3,
                'bookings-2-id': cl_booking.id,
                'bookings-2-event': cl_booking.event.id,
                'bookings-2-status': 'CANCELLED',
                'bookings-2-paid': cl_booking.paid,
                'bookings-2-block': cl_booking.block.id,
                'booking_status': ['future']
            }
        )

        self.client.login(username=self.staff_user.username, password='test')
        self.client.post(
            reverse(
                'studioadmin:user_bookings_list',
                args=[self.user.id, 'future']
            ),
            data
        )

        self.assertFalse(
            BlockType.objects.filter(identifier='transferred').exists()
        )

        cl_booking.refresh_from_db()
        self.assertEqual(cl_booking.status, 'CANCELLED')
        self.assertFalse(cl_booking.paid)
        self.assertFalse(cl_booking.payment_confirmed)
        self.assertIsNone(cl_booking.block)

        with self.assertRaises(Block.DoesNotExist):
            Block.objects.get(
                user=self.user, transferred_booking_id=cl_booking.id,
            )

    def test_cancel_free_block_booked_CL_does_not_creates_transfer_block(self):
        free_blocktype = mommy.make_recipe('booking.free_blocktype')
        block = mommy.make(Block, user=self.user, block_type=free_blocktype)
        cl_booking = mommy.make_recipe(
            'booking.booking',
            event__event_type__event_type='CL', block=block,
            user=self.user, paid=True, payment_confirmed=True, free_class=True
        )

        data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-INITIAL_FORMS': 3,
                'bookings-2-id': cl_booking.id,
                'bookings-2-event': cl_booking.event.id,
                'bookings-2-status': 'CANCELLED',
                'bookings-2-paid': cl_booking.paid,
                'bookings-2-block': cl_booking.block.id,
                'booking_status': ['future']
            }
        )

        self.client.login(username=self.staff_user.username, password='test')
        self.client.post(
            reverse(
                'studioadmin:user_bookings_list',
                args=[self.user.id, 'future']
            ),
            data
        )

        self.assertFalse(
            BlockType.objects.filter(identifier='transferred').exists()
        )

        cl_booking.refresh_from_db()
        self.assertEqual(cl_booking.status, 'CANCELLED')
        self.assertFalse(cl_booking.paid)
        self.assertFalse(cl_booking.payment_confirmed)
        self.assertIsNone(cl_booking.block)

        with self.assertRaises(Block.DoesNotExist):
            Block.objects.get(
                user=self.user, transferred_booking_id=cl_booking.id,
            )


class UserBlocksViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(UserBlocksViewTests, self).setUp()
        self.block = mommy.make_recipe('booking.block', user=self.user)

    def _get_response(self, user, user_id):
        url = reverse(
            'studioadmin:user_blocks_list',
            kwargs={'user_id': user_id}
        )
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return user_blocks_view(request, user_id)

    def _post_response(self, user, user_id, form_data):
        url = reverse(
            'studioadmin:user_blocks_list',
            kwargs={'user_id': user_id}
        )
        session = _create_session()
        request = self.factory.post(url, form_data, follow=True)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return user_blocks_view(request, user_id)

    def formset_data(self, extra_data={}):

        data = {
            'blocks-TOTAL_FORMS': 1,
            'blocks-INITIAL_FORMS': 1,
            'blocks-0-id': str(self.block.id),
            'blocks-0-block_type': str(self.block.block_type.id),
            'blocks-0-start_date': self.block.start_date.strftime(
                '%Y-%m-%d %H:%M:%S'
            ),
            'initial-blocks-0-start_date': self.block.start_date.strftime(
                '%Y-%m-%d %H:%M:%S'
            ),
            'blocks-0-paid': self.block.paid
            }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse(
            'studioadmin:user_blocks_list',
            kwargs={'user_id': self.user.id}
        )
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user, self.user.id)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_cannot_access(self):
        """
        test that the page redirects if user is in the instructor group but is
        not a staff user
        """
        resp = self._get_response(self.instructor_user, self.user.id)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user, self.user.id)
        self.assertEquals(resp.status_code, 200)

    def test_view_users_blocks(self):
        """
        Test only user's bookings for future events shown by default
        """
        new_user = mommy.make_recipe('booking.user')
        new_blocks = mommy.make_recipe(
            'booking.block', user=new_user, _quantity=2
        )
        self.assertEqual(Block.objects.count(), 3)
        resp = self._get_response(self.staff_user, new_user.id)
        # get all but last form (last form is the empty extra one)
        block_forms = resp.context_data['userblockformset'].forms[:-1]
        self.assertEqual(len(block_forms), 2)

        new_blocks.reverse()  # blocks are shown in reverse order by start date
        self.assertEqual(
            [block.instance for block in block_forms],
            new_blocks
        )

    def test_can_update_block(self):
        self.assertFalse(self.block.paid)
        resp = self._post_response(
            self.staff_user, self.user.id,
            self.formset_data({'blocks-0-paid': True})
        )
        block = Block.objects.get(id=self.block.id)
        self.assertTrue(block.paid)

    def test_can_create_block(self):
        block_type = mommy.make_recipe('booking.blocktype')
        self.assertEqual(Block.objects.count(), 1)
        resp = self._post_response(
            self.staff_user, self.user.id,
            self.formset_data(
                {
                    'blocks-TOTAL_FORMS': 2,
                    'blocks-1-block_type': block_type.id
                }
            )
        )
        self.assertEqual(Block.objects.count(), 2)

    def test_formset_unchanged(self):
        """
        test formset submitted unchanged redirects back to user block list
        """
        resp = self._post_response(
            self.staff_user, self.user.id, self.formset_data()
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url,
            reverse(
                'studioadmin:user_blocks_list',
                kwargs={'user_id': self.user.id}
            )
        )

    def test_delete_block(self):
        self.assertFalse(self.block.paid)
        self._post_response(
            self.staff_user, self.user.id,
            self.formset_data({'blocks-0-DELETE': True})
        )
        with self.assertRaises(Block.DoesNotExist):
            Block.objects.get(id=self.block.id)

    def test_submitting_with_form_errors_shows_messages(self):
        block_type = mommy.make_recipe('booking.blocktype')
        self.assertEqual(Block.objects.count(), 1)
        data = self.formset_data(
            {
                'blocks-TOTAL_FORMS': 2,
                'blocks-1-block_type': block_type.id,
                'blocks-1-start_date': '34 Jan 2023'
            }
        )
        url = reverse(
            'studioadmin:user_blocks_list',
            kwargs={'user_id': self.user.id}
        )
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.post(url, data)

        self.assertIn(
            'There were errors in the following fields:start_date',
            format_content(resp.rendered_content)
        )
        self.assertEqual(Block.objects.count(), 1)


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

        resp = self.client.get(
            reverse('studioadmin:mailing_list'), {'unsubscribe': [ml_user.id]}
        )
        ml_user.refresh_from_db()
        self.assertNotIn(self.subscribed, ml_user.groups.all())
