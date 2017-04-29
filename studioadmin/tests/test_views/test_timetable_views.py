from datetime import datetime
from unittest.mock import patch
from model_mommy import mommy

from django.conf import settings
from django.core.urlresolvers import reverse
from django.test import TestCase
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone

from booking.models import Event
from booking.tests.helpers import _create_session, format_content
from studioadmin.views import (
    timetable_admin_list,
    TimetableSessionUpdateView,
    TimetableSessionCreateView,
    upload_timetable_view,
)

from timetable.models import Session
from studioadmin.tests.test_views.helpers import TestPermissionMixin


class TimetableAdminListViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(TimetableAdminListViewTests, self).setUp()
        self.session = mommy.make_recipe('booking.mon_session', cost=10)

    def _get_response(self, user):
        url = reverse('studioadmin:timetable')
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return timetable_admin_list(request)

    def _post_response(self, user, form_data):
        url = reverse('studioadmin:timetable')
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return timetable_admin_list(request)

    def formset_data(self, extra_data={}):

        data = {
            'form-TOTAL_FORMS': 1,
            'form-INITIAL_FORMS': 1,
            'form-0-id': self.session.id,
            'form-0-booking_open': self.session.booking_open,
            'form-0-payment_open': self.session.payment_open,
            'form-0-advance_payment_required': self.session.advance_payment_required
            }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse('studioadmin:timetable')
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

    def test_can_delete_sessions(self):
        mommy.make_recipe('booking.tue_session', _quantity=2)
        mommy.make_recipe('booking.wed_session', _quantity=2)
        self.assertEqual(Session.objects.count(), 5)

        data = {
            'form-TOTAL_FORMS': 5,
            'form-INITIAL_FORMS': 5,
            }

        for i, session in enumerate(Session.objects.all()):
            data['form-{}-id'.format(i)] = session.id
            data['form-{}-cost'.format(i)] = session.cost
            data['form-{}-max_participants'.format(i)] = session.max_participants
            data['form-{}-booking_open'.format(i)] = session.booking_open
            data['form-{}-payment_open'.format(i)] = session.payment_open

        data['form-0-DELETE'] = 'on'

        self._post_response(self.staff_user, data)
        self.assertEqual(Session.objects.count(), 4)

    def test_can_update_existing_session(self):
        self.assertEqual(self.session.advance_payment_required, True)

        self._post_response(
            self.staff_user, self.formset_data(
                extra_data={'form-0-advance_payment_required': False}
            )
        )
        self.session.refresh_from_db()
        self.assertEqual(self.session.advance_payment_required, False)

    def test_submitting_valid_form_redirects_back_to_timetable(self):
        resp = self._post_response(
            self.staff_user, self.formset_data()
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:timetable'))


class TimetableSessionUpdateViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(TimetableSessionUpdateViewTests, self).setUp()
        self.session = mommy.make_recipe('booking.mon_session')

    def _get_response(self, user, ttsession):
        url = reverse('studioadmin:edit_session', args=[ttsession.id])
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        view = TimetableSessionUpdateView.as_view()
        return view(request, pk=ttsession.id)

    def _post_response(self, user, ttsession, form_data):
        url = reverse('studioadmin:edit_session', args=[ttsession.id])
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

        view = TimetableSessionUpdateView.as_view()
        return view(request, pk=ttsession.id)

    def form_data(self, ttsession, extra_data={}):
        data = {
            'id': ttsession.id,
            'name': ttsession.name,
            'event_type': ttsession.event_type.id,
            'day': ttsession.day,
            'time': ttsession.time.strftime('%H:%M'),
            'contact_email': ttsession.contact_email,
            'contact_person': ttsession.contact_person,
            'cancellation_period': ttsession.cancellation_period,
            'location': ttsession.location,
            'allow_booking_cancellation': True,
            'paypal_email': settings.DEFAULT_PAYPAL_EMAIL,
        }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse('studioadmin:edit_session', args=[self.session.id])
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user, self.session)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_cannot_access(self):
        """
        test that the page redirects if user is in the instructor group but is
        not a staff user
        """
        resp = self._get_response(self.instructor_user, self.session)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user, self.session)
        self.assertEquals(resp.status_code, 200)

    def test_submitting_valid_session_form_redirects_back_to_timetable(self):
        resp = self._post_response(
            self.staff_user, self.session, self.form_data(self.session)
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:timetable'))

    def test_context_data(self):
        resp = self._get_response(self.staff_user, self.session)
        self.assertEqual(resp.context_data['sidenav_selection'], 'timetable')
        self.assertEqual(resp.context_data['session_day'], 'Monday')

    def test_can_edit_session_data(self):
        self.assertEqual(self.session.day, '01MON')
        resp = self._post_response(
            self.staff_user, self.session,
            self.form_data(self.session, extra_data={'day': '03WED'})
        )
        session = Session.objects.get(id=self.session.id)
        self.assertEqual(session.day, '03WED')

    def test_submitting_with_no_changes_does_not_change_session(self):
        self._post_response(
            self.staff_user, self.session, self.form_data(self.session)
        )
        ttsession = Session.objects.get(id=self.session.id)

        self.assertEqual(self.session.id, ttsession.id)
        self.assertEqual(self.session.name, ttsession.name)
        self.assertEqual(self.session.event_type, ttsession.event_type)
        self.assertEqual(self.session.day, ttsession.day)
        self.assertEqual(
            self.session.time.strftime('%H:%M'),
            ttsession.time.strftime('%H:%M')
        )
        self.assertEqual(self.session.contact_email, ttsession.contact_email)
        self.assertEqual(self.session.contact_person, ttsession.contact_person)
        self.assertEqual(
            self.session.cancellation_period,
            ttsession.cancellation_period
        )
        self.assertEqual(self.session.location, ttsession.location)

    def test_update_paypal_email_to_non_default(self):
        form_data = self.form_data(
            self.session,
            {
                'paypal_email': 'testpaypal@test.com',
                'paypal_email_check': 'testpaypal@test.com'
            }
        )
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.post(
            reverse('studioadmin:edit_session', args=[self.session.id]),
            form_data, follow=True
        )

        self.assertIn(
            "You have changed the paypal receiver email. If you haven't used "
            "this email before, it is strongly recommended that you test the "
            "email address here",
            format_content(str(resp.content)).replace('\\', '')
        )
        self.assertIn(
            "/studioadmin/test-paypal-email?email=testpaypal@test.com",
            str(resp.content)
        )

        self.session.refresh_from_db()
        self.assertEqual(self.session.paypal_email, 'testpaypal@test.com')

    def test_update_paypal_email_to_default(self):
        self.client.login(username=self.staff_user.username, password='test')
        self.session.paypal_email = 'testpp@pp.com'
        self.session.save()
        form_data = self.form_data(
            self.session,
            {
                'paypal_email': settings.DEFAULT_PAYPAL_EMAIL,
                'paypal_email_check': settings.DEFAULT_PAYPAL_EMAIL
            }
        )
        resp = self.client.post(
            reverse('studioadmin:edit_session', args=[self.session.id]),
            form_data, follow=True
        )
        self.assertNotIn(
            "You have changed the paypal receiver email.",
            format_content(str(resp.content)).replace('\\', '')
        )
        self.session.refresh_from_db()
        self.assertEqual(self.session.paypal_email, settings.DEFAULT_PAYPAL_EMAIL)

    def test_update_no_changes(self):
        self.client.login(username=self.staff_user.username, password='test')
        form_data = self.form_data(
            self.session,
            {
                'max_participants': self.session.max_participants,
                'cost': self.session.cost,
                'booking_open': self.session.booking_open,
                'payment_open': self.session.payment_open,
                'advance_payment_required': self.session.advance_payment_required,
            }
        )
        resp = self.client.post(
            reverse('studioadmin:edit_session', args=[self.session.id]),
            form_data, follow=True
        )
        self.assertIn('No changes made', format_content(str(resp.content)))


class TimetableSessionCreateViewTests(TestPermissionMixin, TestCase):

    def _get_response(self, user):
        url = reverse('studioadmin:add_session')
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

        view = TimetableSessionCreateView.as_view()
        return view(request)

    def _post_response(self, user, form_data):
        url = reverse('studioadmin:add_session')
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

        view = TimetableSessionCreateView.as_view()
        return view(request)

    def form_data(self, extra_data={}):
        ev_type = mommy.make_recipe('booking.event_type_PC')
        data = {
            'name': 'test_event',
            'event_type': ev_type.id,
            'day': '01MON',
            'time': '18:00',
            'contact_email': 'test@test.com',
            'contact_person': 'test',
            'cancellation_period': 24,
            'location': 'Watermelon Studio',
            'allow_booking_cancellation': True,
            'paypal_email': settings.DEFAULT_PAYPAL_EMAIL,
        }
        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse('studioadmin:add_session')
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

    def test_submitting_valid_session_form_redirects_back_to_timetable(self):
        resp = self._post_response(self.staff_user, self.form_data())
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:timetable'))

    def test_context_data(self):
        resp = self._get_response(self.staff_user)
        self.assertEqual(resp.context_data['sidenav_selection'], 'add_session')

    def test_can_add_event(self):
        self.assertEqual(Session.objects.count(), 0)
        resp = self._post_response(self.staff_user, self.form_data())
        self.assertEqual(Session.objects.count(), 1)
        ttsession = Session.objects.first()
        self.assertEqual(ttsession.name, 'test_event')

    def test_create_event_with_non_default_paypal_email(self):
        form_data = self.form_data(
            {
                'paypal_email': 'testpaypal@test.com',
                'paypal_email_check': 'testpaypal@test.com'
            }
        )
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.post(
            reverse('studioadmin:add_session'),
            form_data, follow=True
        )

        self.assertIn(
            "You have changed the paypal receiver email from the default value. "
            "If you haven't used "
            "this email before, it is strongly recommended that you test the "
            "email address here",
            format_content(str(resp.content)).replace('\\', '')
        )
        self.assertIn(
            "/studioadmin/test-paypal-email?email=testpaypal@test.com",
            str(resp.content)
        )

        session = Session.objects.latest('id')
        self.assertEqual(session.paypal_email, 'testpaypal@test.com')

        form_data = self.form_data()
        resp = self.client.post(
            reverse('studioadmin:add_session'),
            form_data, follow=True
        )
        self.assertNotIn(
            "You have changed the paypal receiver email from the default value.",
            format_content(str(resp.content)).replace('\\', '')
        )
        session1 = Session.objects.latest('id')
        self.assertEqual(session1.paypal_email, settings.DEFAULT_PAYPAL_EMAIL)


class UploadTimetableTests(TestPermissionMixin, TestCase):

    def _get_response(self, user):
        url = reverse('studioadmin:upload_timetable')
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return upload_timetable_view(request)

    def _post_response(self, user, form_data):
        url = reverse('studioadmin:upload_timetable')
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return upload_timetable_view(request)

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse('studioadmin:upload_timetable')
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

    @patch('studioadmin.forms.timetable_forms.timezone')
    def test_events_are_created(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 6, 1, 0, 0, tzinfo=timezone.utc
        )
        mommy.make_recipe('booking.mon_session', _quantity=5)
        self.assertEqual(Event.objects.count(), 0)
        form_data = {
            'start_date': 'Mon 08 Jun 2015',
            'end_date': 'Sun 14 Jun 2015',
            'sessions': [session.id for session in Session.objects.all()]
        }
        self._post_response(self.staff_user, form_data)
        self.assertEqual(Event.objects.count(), 5)
        event_names = [event.name for event in Event.objects.all()]
        session_names =  [session.name for session in Session.objects.all()]
        self.assertEqual(sorted(event_names), sorted(session_names))

    @patch('studioadmin.forms.timetable_forms.timezone')
    def test_does_not_create_duplicate_sessions(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 6, 1, 0, 0, tzinfo=timezone.utc
        )
        mommy.make_recipe('booking.mon_session', _quantity=5)
        self.assertEqual(Event.objects.count(), 0)
        form_data = {
            'start_date': 'Mon 08 Jun 2015',
            'end_date': 'Sun 14 Jun 2015',
            'sessions': [session.id for session in Session.objects.all()]
        }
        self._post_response(self.staff_user, form_data)
        self.assertEqual(Event.objects.count(), 5)

        mommy.make_recipe('booking.tue_session', _quantity=2)
        form_data.update(
            {'sessions': [session.id for session in Session.objects.all()]}
        )
        self.assertEqual(Session.objects.count(), 7)
        self._post_response(self.staff_user, form_data)
        self.assertEqual(Event.objects.count(), 7)
