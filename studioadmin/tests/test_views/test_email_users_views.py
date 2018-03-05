from unittest.mock import patch
from model_mommy import mommy

from django.urls import reverse
from django.core import mail
from django.test import TestCase
from django.contrib.auth.models import Group, User
from django.contrib.messages.storage.fallback import FallbackStorage

from activitylog.models import ActivityLog
from booking.models import Booking
from common.tests.helpers import _create_session
from studioadmin.views import (
    email_users_view,
)
from studioadmin.views.helpers import url_with_querystring

from studioadmin.tests.test_views.helpers import TestPermissionMixin


class ChooseUsersToEmailTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(ChooseUsersToEmailTests, cls).setUpTestData()
        cls.url = reverse('studioadmin:choose_email_users')

    def formset_data(self, extra_data={}):

        data = {
            'form-TOTAL_FORMS': 1,
            'form-INITIAL_FORMS': 1,
            'form-0-id': str(self.user.id),
            }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse('studioadmin:choose_email_users')
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(self.url)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_cannot_access(self):
        """
        test that the page redirects if user is in the instructor group but is
        not a staff user
        """
        self.client.login(
            username=self.instructor_user.username, password='test'
        )
        resp = self.client.get(self.url)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.get(self.url)
        self.assertEquals(resp.status_code, 200)

    def test_filter_users_by_event_booked(self):
        mommy.make_recipe('booking.user', _quantity=2)
        event = mommy.make_recipe('booking.future_EV')
        mommy.make_recipe('booking.booking', user=self.user, event=event)
        form_data = self.formset_data(
            {
                'filter': 'Show Students',
                'filter-events': [event.id],
                'filter-lessons': [],
                'filter-students': []
            }
        )

        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.post(self.url, form_data)

        # incl user, staff_user, instructor_user
        self.assertEqual(User.objects.count(), 5)

        usersformset = resp.context_data['usersformset']
        self.assertEqual(len(usersformset.forms), 1)

        user = usersformset.forms[0]
        self.assertEqual(user.instance, self.user)

    def test_filter_users_by_class_booked(self):
        mommy.make_recipe('booking.user', _quantity=2)
        pole_class = mommy.make_recipe('booking.future_PC')
        mommy.make_recipe('booking.booking', user=self.user, event=pole_class)
        form_data = self.formset_data(
            {
                'filter': 'Show Students',
                'filter-lessons': [pole_class.id],
                'filter-events': [],
                'filter-students': []
            }
        )
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.post(self.url, form_data)

        # incl user, staff_user, instructor_user
        self.assertEqual(User.objects.count(), 5)

        usersformset = resp.context_data['usersformset']
        self.assertEqual(len(usersformset.forms), 1)

        user = usersformset.forms[0]
        self.assertEqual(user.instance, self.user)

    def test_filter_users_by_user(self):
        mommy.make_recipe('booking.user', _quantity=2)
        event = mommy.make_recipe('booking.future_EV')
        lesson = mommy.make_recipe('booking.future_CL')
        user1 = mommy.make_recipe('booking.user')
        user2 = mommy.make_recipe('booking.user')

        mommy.make_recipe('booking.booking', user=user1, event=event)
        mommy.make_recipe('booking.booking', user=user2, event=lesson)

        form_data = self.formset_data(
            {
                'filter': 'Show Students',
                'filter-events': [],
                'filter-lessons': [],
                'filter-students': [self.user.id]
            }
        )

        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.post(self.url, form_data)

        # incl user, staff_user, instructor_user
        self.assertEqual(User.objects.count(), 7)

        usersformset = resp.context_data['usersformset']
        self.assertEqual(len(usersformset.forms), 1)

        user = usersformset.forms[0]
        self.assertEqual(user.instance, self.user)

    def test_filter_users_without_events_removes_previous_selections(self):
        user = mommy.make_recipe('booking.user')
        user1 = mommy.make_recipe('booking.user')
        event = mommy.make_recipe('booking.future_EV')
        event1 = mommy.make_recipe('booking.future_EV')
        lesson = mommy.make_recipe('booking.future_PC')
        mommy.make_recipe('booking.booking', event=event, user=user)
        mommy.make_recipe('booking.booking', event=event1, user=user1)
        mommy.make_recipe('booking.booking', event=lesson, user=user1)

        form_data = self.formset_data(
            {
                'filter': 'Show Students',
                'filter-lessons': [],
                'filter-events': [],
                'filter-students': []
            }
        )
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.post(self.url, form_data)

        # incl user, staff_user, instructor_user
        self.assertEqual(User.objects.count(), 5)

        # usersformset only shows selected users
        usersformset = resp.context_data['usersformset']
        self.assertEqual(len(usersformset.forms), 0)

    def test_filter_with_no_events_selected(self):
        mommy.make_recipe('booking.user', _quantity=2)
        pole_class = mommy.make_recipe('booking.future_PC')
        mommy.make_recipe('booking.booking', user=self.user, event=pole_class)
        form_data = self.formset_data(
            {
                'filter': 'Show Students',
                'filter-lessons': [],
                'filter-events': [],
                'filter-students': []
            }
        )
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.post(self.url, form_data)

        # incl user, staff_user, instructor_user
        self.assertEqual(User.objects.count(), 5)

        # usersformset only shows selected users
        usersformset = resp.context_data['usersformset']
        self.assertEqual(len(usersformset.forms), 0)

    def test_filter_users_by_multiple_events_and_classes(self):
        new_user1 = mommy.make_recipe('booking.user')
        mommy.make_recipe('booking.user')
        event = mommy.make_recipe('booking.future_EV')
        pole_class = mommy.make_recipe('booking.future_PC')
        mommy.make_recipe('booking.booking', user=self.user, event=pole_class)
        mommy.make_recipe('booking.booking', user=new_user1, event=event)
        form_data = self.formset_data(
            {
                'filter': 'Show Students',
                'filter-lessons': [pole_class.id],
                'filter-events': [event.id],
                'filter-students': []
            }
        )
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.post(self.url, form_data)

        # incl user, staff_user, instructor_user
        self.assertEqual(User.objects.count(), 5)

        usersformset = resp.context_data['usersformset']
        self.assertEqual(len(usersformset.forms), 2)

        users = [form.instance for form in usersformset.forms]
        self.assertEqual(set(users), {self.user, new_user1})

    def test_filter_users_by_multiple_events_and_classes_and_students(self):
        new_user1 = mommy.make_recipe('booking.user')
        new_user2 = mommy.make_recipe('booking.user')
        new_user3 = mommy.make_recipe('booking.user')
        new_user4 = mommy.make_recipe('booking.user')
        event = mommy.make_recipe('booking.future_EV')
        pole_class = mommy.make_recipe('booking.future_PC')
        pole_class2 = mommy.make_recipe('booking.future_PC')
        mommy.make_recipe('booking.booking', user=self.user, event=pole_class)
        mommy.make_recipe('booking.booking', user=new_user1, event=event)
        mommy.make_recipe('booking.booking', user=new_user2, event=event)
        mommy.make_recipe('booking.booking', user=new_user3, event=pole_class2)

        # new user 2 is selected based on both filter-events and filter-students
        # new user 1 is selected based on filter-events only
        # self.user is selected based on filter-lessons only
        # new user 4 is selected based on filter-students only
        # new user 3 has a booking but not selected via filter-lessons
        # staff user is not selected

        form_data = self.formset_data(
            {
                'filter': 'Show Students',
                'filter-lessons': [pole_class.id],
                'filter-events': [event.id],
                'filter-students': [new_user2.id, new_user4.id]
            }
        )
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.post(self.url, form_data)

        # incl user, staff_user, instructor_user
        self.assertEqual(User.objects.count(), 7)

        usersformset = resp.context_data['usersformset']
        self.assertEqual(len(usersformset.forms), 4)

        users = [form.instance for form in usersformset.forms]
        self.assertEqual(
            set(users), {self.user, new_user1, new_user2, new_user4}
        )

    def test_users_for_cancelled_bookings_not_shown(self):
        new_user = mommy.make_recipe('booking.user')
        event = mommy.make_recipe('booking.future_EV')
        mommy.make_recipe(
            'booking.booking', user=self.user, event=event, status='CANCELLED'
        )
        mommy.make_recipe('booking.booking', user=new_user, event=event)
        form_data = self.formset_data(
            {
                'filter': 'Show Students',
                'filter-events': [event.id],
                'filter-lessons': [],
                'filter-students': []
            }
        )
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.post(self.url, form_data)

        usersformset = resp.context_data['usersformset']
        self.assertEqual(len(usersformset.forms), 1)

        user = usersformset.forms[0].instance
        self.assertEqual(user, new_user)

    def test_filter_users_with_multiple_bookings(self):
        new_user = mommy.make_recipe('booking.user')
        events = mommy.make_recipe('booking.future_EV', _quantity=3)
        for event in events:
            mommy.make_recipe('booking.booking', user=new_user, event=event)
        form_data = self.formset_data(
            {
                'filter': 'Show Students',
                'filter-events': [event.id for event in events],
                'filter-lessons': [],
                'filter-students': []}
        )
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.post(self.url, form_data)

        # incl user, staff_user, instructor_user
        self.assertEqual(User.objects.count(), 4)
        self.assertEqual(Booking.objects.filter(user=new_user).count(), 3)
        usersformset = resp.context_data['usersformset']
        # user has 3 bookings, for each of the selected events, but is only
        # displayed once
        self.assertEqual(len(usersformset.forms), 1)

        user = usersformset.forms[0].instance
        self.assertEqual(user, new_user)

    def test_remove_previous_events_and_classes_data_from_session(self):
        new_user1 = mommy.make_recipe('booking.user')
        new_user2 = mommy.make_recipe('booking.user')
        old_event = mommy.make_recipe('booking.future_EV')
        old_pole_class = mommy.make_recipe('booking.future_PC')
        event = mommy.make_recipe('booking.future_EV')
        pole_class = mommy.make_recipe('booking.future_PC')
        mommy.make_recipe('booking.booking', user=self.user, event=pole_class)
        mommy.make_recipe('booking.booking', user=new_user1, event=event)
        mommy.make_recipe('booking.booking', user=new_user2, event=old_event)
        mommy.make_recipe(
            'booking.booking', user=new_user2, event=old_pole_class
        )

        form_data = self.formset_data(
            {
                'filter': 'Show Students',
                'filter-lessons': [old_pole_class.id],
                'filter-events': [old_event.id],
                'filter-students': []
            }
        )
        self.client.login(username=self.staff_user.username, password='test')
        self.client.post(self.url, form_data)
        self.assertEqual(
            self.client.session['lessons'], [str(old_pole_class.id)]
        )
        self.assertEqual(self.client.session['events'], [str(old_event.id)])

        form_data = self.formset_data(
            {
                'filter': 'Show Students',
                'filter-lessons': [],
                'filter-events': [],
                'filter-students': []
            }
        )
        # Filter again without refreshing and with no selections;
        # need to remove old session data
        self.client.post(self.url, form_data)
        self.assertIsNone(self.client.session.get('lessons'))
        self.assertIsNone(self.client.session.get('events'))

    def test_session_data_reset_on_get(self):
        user1 = mommy.make_recipe('booking.user')
        user2 = mommy.make_recipe('booking.user')
        event = mommy.make_recipe('booking.future_EV')
        pole_class = mommy.make_recipe('booking.future_PC')
        mommy.make_recipe('booking.booking', user=user1, event=event)
        mommy.make_recipe('booking.booking', user=user2, event=pole_class)

        form_data = self.formset_data(
            {
                'filter': 'Show Students',
                'filter-lessons': [pole_class.id],
                'filter-events': [event.id],
                'filter-students': []
            }
        )

        self.client.login(username=self.staff_user.username, password='test')
        # post to set the session data
        self.client.post(
            reverse('studioadmin:choose_email_users'), form_data
        )
        self.assertEqual(self.client.session['events'], [str(event.id)])
        self.assertEqual(self.client.session['lessons'], [str(pole_class.id)])

        self.client.get(reverse('studioadmin:choose_email_users'))
        self.assertIsNone(self.client.session.get('events'))
        self.assertIsNone(self.client.session.get('lessons'))

    def test_get_users_to_email(self):
        new_user1 = mommy.make_recipe('booking.user')
        event = mommy.make_recipe('booking.future_EV')
        pole_class = mommy.make_recipe('booking.future_PC')
        mommy.make_recipe('booking.booking', user=self.user, event=pole_class)
        mommy.make_recipe('booking.booking', user=new_user1, event=event)

        session_data = {
            'events': [event.id],
            'lessons': [pole_class.id]
        }

        self.client.login(username=self.staff_user.username, password='test')
        # post with filter to set session data

        filter_form_data = self.formset_data(
            {
                'filter': 'Show Students',
                'filter-lessons': [pole_class.id],
                'filter-events': [event.id],
                'filter-students': []
            }
        )
        self.client.post(self.url, filter_form_data)

        form_data = self.formset_data(
            {
                'filter-lessons': [pole_class.id],
                'filter-events': [event.id],
                'form-TOTAL_FORMS': 2,
                'form-INITIAL_FORMS': 2,
                'form-0-id': self.user.id,
                'form-0-email_user': True,
                'form-1-id': new_user1.id,
                'form-1-email_user': True,
            }
        )
        resp = self.client.post(self.url, form_data)
        self.assertEqual(
            sorted(self.client.session['users_to_email']),
            sorted([self.user.id, new_user1.id])
        )
        self.assertEqual(resp.status_code, 302)

        self.assertEqual(
            url_with_querystring(
                reverse('studioadmin:email_users_view'),
                events=[str(event.id)], lessons=[str(pole_class.id)]),
            resp.url
        )


class EmailUsersTests(TestPermissionMixin, TestCase):

    def _get_response(
        self, user, users_to_email, event_ids=[], lesson_ids=[]
    ):
        url = url_with_querystring(
            reverse('studioadmin:email_users_view'),
            events=event_ids, lessons=lesson_ids
        )
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.session['users_to_email'] = users_to_email
        request.session['events'] = event_ids
        request.session['lessons'] = lesson_ids
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return email_users_view(request)

    def _post_response(
        self, user, users_to_email, form_data, event_ids=[], lesson_ids=[]
    ):
        url = url_with_querystring(
            reverse('studioadmin:email_users_view'),
            events=event_ids, lessons=lesson_ids
        )
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.session['users_to_email'] = users_to_email
        request.session['events'] = event_ids
        request.session['lessons'] = lesson_ids
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return email_users_view(request)

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse('studioadmin:email_users_view')
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user, [self.user.id])
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_cannot_access(self):
        """
        test that the page redirects if user is in the instructor group but is
        not a staff user
        """
        resp = self._get_response(self.instructor_user, [self.user.id])
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user, [self.user.id])
        self.assertEquals(resp.status_code, 200)

    def test_users_and_events_in_context(self):
        event = mommy.make_recipe('booking.future_EV', name='Test Event')
        lesson = mommy.make_recipe('booking.future_PC', name='Test Class')
        resp = self._get_response(
            self.staff_user, [self.user.id],
            event_ids=[event.id], lesson_ids=[lesson.id]
        )
        self.assertEqual([ev for ev in resp.context_data['events']], [event])
        self.assertEqual(
            [lsn for lsn in resp.context_data['lessons']], [lesson]
        )
        self.assertEqual(
            [user for user in resp.context_data['users_to_email']], [self.user]
        )

    def test_subject_is_autopoulated(self):
        event = mommy.make_recipe('booking.future_EV', name='Workshop')
        lesson = mommy.make_recipe('booking.future_PC', name='Class')
        resp = self._get_response(
            self.staff_user, [self.user.id],
            event_ids=[event.id], lesson_ids=[lesson.id]
        )
        form = resp.context_data['form']
        self.assertIn(
            form.initial['subject'],
            [
                "; ".join([str(event), str(lesson)]),
                "; ".join([str(lesson), str(event)])
            ]
        )

    def test_emails_sent(self):
        event = mommy.make_recipe('booking.future_EV')
        user = mommy.make_recipe('booking.user', email='other@test.com')
        self._post_response(
            self.staff_user, [self.user.id, user.id],
            event_ids=[event.id], lesson_ids=[],
            form_data={
                'subject': 'Test email',
                'message': 'Test message',
                'from_address': 'test@test.com'}
        )
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn('Test message', email.body)
        self.assertEqual(email.to, [])
        self.assertEqual(email.reply_to, ['test@test.com'])
        self.assertEqual(sorted(email.bcc), [self.user.email, user.email])
        self.assertEqual(
            email.subject, 'Test email'
        )

    @patch('studioadmin.views.email_users.EmailMultiAlternatives.send')
    def test_email_errors(self, mock_send):
        mock_send.side_effect = Exception('Error sending email')
        event = mommy.make_recipe('booking.future_EV')
        self._post_response(
            self.staff_user, [self.user.id],
            event_ids=[event.id], lesson_ids=[],
            form_data={
                'subject': 'Test email',
                'message': 'Test message',
                'from_address': 'test@test.com'}
        )
        self.assertEqual(len(mail.outbox), 0)
        log = ActivityLog.objects.latest('id')
        self.assertEqual(
            log.log,
            'Bulk email error '
            '(email subject "Test email"), '
            'sent by by admin user {}'.format(
                self.staff_user.username
            )
        )

    def test_cc_email_sent(self):
        self._post_response(
            self.staff_user, [self.user.id],
            event_ids=[], lesson_ids=[],
            form_data={
                'subject': 'Test email',
                'message': 'Test message',
                'from_address': 'test@test.com',
                'cc': True}
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].cc[0], 'test@test.com')

    def test_reply_to_set_to_from_address(self):
        self._post_response(
            self.staff_user, [self.user.id],
            event_ids=[], lesson_ids=[],
            form_data={
                'subject': 'Test email',
                'message': 'Test message',
                'from_address': 'test@test.com',
                'cc': True}
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].reply_to[0], 'test@test.com')

    def test_with_form_errors(self):
        resp = self._post_response(
            self.staff_user, [self.user.id],
            event_ids=[], lesson_ids=[],
            form_data={
                'subject': 'Test email',
                'message': 'Test message',
            }
        )
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn('Please correct errors in form', resp.rendered_content)

    def test_email_mailing_list(self):
        url = reverse('studioadmin:mailing_list_email')
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.get(url)

        # group is created in view if it doesn't already exist
        group = Group.objects.get(name='subscribed')
        self.assertFalse(group.user_set.exists())
        self.assertEqual(resp.context_data['users_to_email'].count(), 0)

        subscribed_users = mommy.make_recipe('booking.user', _quantity=3)
        mommy.make_recipe('booking.user', _quantity=3)
        for user in subscribed_users:
            group.user_set.add(user)

        resp = self.client.get(url)
        # staff, instructor, user plus 6 created here
        self.assertEqual(User.objects.count(), 9)
        # only the 3 in the subscribed group
        self.assertEqual(resp.context_data['users_to_email'].count(), 3)
        self.assertEqual(
            sorted([user.id for user in resp.context_data['users_to_email']]),
            sorted([user.id for user in subscribed_users])
        )

    def test_email_mailing_list_for_more_than_100_users(self):
        url = reverse('studioadmin:mailing_list_email')
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.get(url)

        # group is created in view if it doesn't already exist
        group = Group.objects.get(name='subscribed')
        self.assertFalse(group.user_set.exists())
        self.assertEqual(resp.context_data['users_to_email'].count(), 0)

        for i in range(150):
            mommy.make_recipe(
                'booking.user', email='subscribed{}@test.com'.format(i)
            )
        subscribed_users = User.objects.filter(email__icontains='subscribed')

        mommy.make_recipe('booking.user', _quantity=3)
        for user in subscribed_users:
            group.user_set.add(user)

        form_data = {
            'subject': 'Test email',
            'message': 'Test message',
            'from_address': 'test@test.com',
            'cc': True
        }

        url = reverse('studioadmin:mailing_list_email')
        self.client.login(username=self.staff_user.username, password='test')
        self.client.post(url, form_data)
        self.assertEqual(len(mail.outbox), 2)  # emails split to 2 emails
        # from address cc'd on first email only
        self.assertEqual(mail.outbox[0].cc, ['test@test.com'])
        self.assertEqual(mail.outbox[1].cc, [])
        self.assertEqual(len(mail.outbox[0].bcc), 99)
        self.assertEqual(len(mail.outbox[1].bcc), 51)

        self._post_response(
            self.staff_user, [user.id for user in User.objects.all()],
            event_ids=[], lesson_ids=[],
            form_data=form_data
        )
        self.assertEqual(len(mail.outbox), 4)  # emails split to 2 emails
        # from address cc'd on both emails
        self.assertEqual(mail.outbox[-2].cc, ['test@test.com'])
        self.assertEqual(mail.outbox[-1].cc, [])
        self.assertEqual(len(mail.outbox[-2].bcc), 99)
        self.assertEqual(len(mail.outbox[-1].bcc), 57)

    def test_unsubscribe_link_in_mailing_list_emails_only(self):
        form_data = {
            'subject': 'Test email',
            'message': 'Test message',
            'from_address': 'test@test.com',
            'cc': True
        }

        subscribed_user = mommy.make_recipe(
            'booking.user', email='subscribed@test.com'
        )
        group = mommy.make(Group, name='subscribed')
        group.user_set.add(subscribed_user)

        # mailing list
        url = reverse('studioadmin:mailing_list_email')
        self.client.login(username=self.staff_user.username, password='test')
        self.client.post(url, form_data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].bcc, ['subscribed@test.com'])
        self.assertIn(
            'Unsubscribe from this mailing list', mail.outbox[0].body
        )
        self.assertIn(
            reverse('subscribe'), mail.outbox[0].body
        )

        # bulk email
        self._post_response(
            self.staff_user, [self.user.id], event_ids=[], lesson_ids=[],
            form_data=form_data
        )
        self.assertEqual(len(mail.outbox), 2)  # mailing list email is first
        self.assertEqual(mail.outbox[-1].bcc, [self.user.email])
        self.assertNotIn(
            'Unsubscribe from this mailing list', mail.outbox[-1].body
        )

    def test_sending_test_email_only_goes_to_from_address(self):
        form_data = {
            'subject': 'Test email',
            'message': 'Test message',
            'from_address': 'test@test.com',
            'cc': True,
            'send_test': True
        }

        subscribed_user = mommy.make_recipe(
            'booking.user', email='subscribed@test.com'
        )
        subscribed_user1 = mommy.make_recipe(
            'booking.user', email='subscribed1@test.com'
        )
        group = mommy.make(Group, name='subscribed')
        group.user_set.add(subscribed_user)
        group.user_set.add(subscribed_user1)

        # mailing list
        url = reverse('studioadmin:mailing_list_email')
        self.client.login(username=self.staff_user.username, password='test')
        self.client.post(url, form_data)

        self.assertEqual(len(mail.outbox), 1)
        # email is sent to the 'from' address only
        self.assertEqual(mail.outbox[0].bcc, ['test@test.com'])
        # cc ignored for test email
        self.assertEqual(mail.outbox[0].cc, [])
        self.assertEqual(
            mail.outbox[0].subject,
            'Test email [TEST EMAIL]'.format(
            )
        )

        del form_data['send_test']
        self.client.post(url, form_data)

        self.assertEqual(len(mail.outbox), 2)
        # email is sent to the mailing list users
        self.assertEqual(
            sorted(mail.outbox[1].bcc),
            sorted(['subscribed@test.com', 'subscribed1@test.com'])
        )
        self.assertEqual(mail.outbox[1].cc, ['test@test.com'])
        self.assertEqual(mail.outbox[1].reply_to, ['test@test.com'])
        self.assertEqual(
            mail.outbox[1].subject,
            'Test email'.format(
            )
        )
