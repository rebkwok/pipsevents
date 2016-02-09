from model_mommy import mommy

from django.core.urlresolvers import reverse
from django.core import mail
from django.test import TestCase
from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage

from booking.models import Booking
from booking.tests.helpers import _create_session
from studioadmin.views import (
    choose_users_to_email,
    email_users_view,
)
from studioadmin.views.helpers import url_with_querystring

from studioadmin.tests.test_views.helpers import TestPermissionMixin


class ChooseUsersToEmailTests(TestPermissionMixin, TestCase):

    def _get_response(self, user):
        url = reverse('studioadmin:choose_email_users')
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return choose_users_to_email(request)

    def _post_response(self, user, form_data):
        url = reverse('studioadmin:choose_email_users')
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return choose_users_to_email(request)

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
        resp = self._get_response(self.user)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_cannot_access(self):
        """
        test that the page redirects if user is in the instructor group but is
        not a staff user
        """
        resp = self._get_response(self.instructor_user)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user)
        self.assertEquals(resp.status_code, 200)

    def test_filter_users_by_event_booked(self):
        mommy.make_recipe('booking.user', _quantity=2)
        event = mommy.make_recipe('booking.future_EV')
        mommy.make_recipe('booking.booking', user=self.user, event=event)
        form_data = self.formset_data(
            {'filter': 'Show Students', 'filter-events': [event.id]}
        )
        resp = self._post_response(self.staff_user, form_data)

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
            {'filter': 'Show Students', 'filter-lessons': [pole_class.id]}
        )
        resp = self._post_response(self.staff_user, form_data)

        # incl user, staff_user, instructor_user
        self.assertEqual(User.objects.count(), 5)

        usersformset = resp.context_data['usersformset']
        self.assertEqual(len(usersformset.forms), 1)

        user = usersformset.forms[0]
        self.assertEqual(user.instance, self.user)

    def test_filter_with_no_events_selected(self):
        mommy.make_recipe('booking.user', _quantity=2)
        pole_class = mommy.make_recipe('booking.future_PC')
        mommy.make_recipe('booking.booking', user=self.user, event=pole_class)
        form_data = self.formset_data(
            {
                'filter': 'Show Students',
                'filter-lessons': [''],
                'filter-events': ['']}
        )
        resp = self._post_response(self.staff_user, form_data)

        # incl user, staff_user, instructor_user
        self.assertEqual(User.objects.count(), 5)

        usersformset = resp.context_data['usersformset']
        self.assertEqual(len(usersformset.forms), 5)

        users = [form.instance for form in usersformset.forms]
        self.assertEqual(set(users), set(User.objects.all()))

    def test_filter_users_by_multiple_events_and_classes(self):
        new_user1 = mommy.make_recipe('booking.user')
        new_user2 = mommy.make_recipe('booking.user')
        event = mommy.make_recipe('booking.future_EV')
        pole_class = mommy.make_recipe('booking.future_PC')
        mommy.make_recipe('booking.booking', user=self.user, event=pole_class)
        mommy.make_recipe('booking.booking', user=new_user1, event=event)
        form_data = self.formset_data(
            {
                'filter': 'Show Students',
                'filter-lessons': [pole_class.id],
                'filter-events': [event.id]}
        )
        resp = self._post_response(self.staff_user, form_data)

        # incl user, staff_user, instructor_user
        self.assertEqual(User.objects.count(), 5)

        usersformset = resp.context_data['usersformset']
        self.assertEqual(len(usersformset.forms), 2)

        users = [form.instance for form in usersformset.forms]
        self.assertEqual(set(users), set([self.user, new_user1]))

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
                'filter-events': [event.id]}
        )
        resp = self._post_response(self.staff_user, form_data)

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
                'filter-events': [event.id for event in events]}
        )
        resp = self._post_response(self.staff_user, form_data)

        # incl user, staff_user, instructor_user
        self.assertEqual(User.objects.count(), 4)
        self.assertEqual(Booking.objects.filter(user=new_user).count(), 3)
        usersformset = resp.context_data['usersformset']
        # user has 3 bookings, for each of the selected events, but is only
        # displayed once
        self.assertEqual(len(usersformset.forms), 1)

        user = usersformset.forms[0].instance
        self.assertEqual(user, new_user)


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
        event = mommy.make_recipe('booking.future_EV')
        lesson = mommy.make_recipe('booking.future_PC')
        resp = self._get_response(
            self.staff_user, [self.user.id],
            event_ids=[event.id], lesson_ids=[lesson.id]
        )
        form = resp.context_data['form']
        self.assertEqual(
            form.initial['subject'], "; ".join([str(event), str(lesson)])
        )

    def test_emails_sent(self):
        event = mommy.make_recipe('booking.future_EV')
        resp = self._post_response(
            self.staff_user, [self.user.id],
            event_ids=[event.id], lesson_ids=[],
            form_data={
                'subject': 'Test email',
                'message': 'Test message',
                'from_address': 'test@test.com'}
        )
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.body, 'Test message')
        self.assertEqual(email.subject, '[watermelon studio bookings] Test email')

    def test_cc_email_sent(self):
        resp = self._post_response(
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
        resp = self._post_response(
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
