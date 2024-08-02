import pytz

from datetime import datetime
from datetime import timezone as dt_timezone

from unittest.mock import patch
from model_bakery import baker

from django.conf import settings
from django.urls import reverse
from django.test import TestCase

from booking.models import Event, FilterCategory
from common.tests.helpers import format_content

from timetable.models import Session
from studioadmin.tests.test_views.helpers import TestPermissionMixin


class TimetableAdminListViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(TimetableAdminListViewTests, self).setUp()
        self.session = baker.make_recipe('booking.mon_session', cost=10)
        self.client.force_login(self.staff_user)
        self.url = reverse('studioadmin:timetable')

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
        self.client.logout()
        resp = self.client.get(self.url)
        redirected_url = reverse('account_login') + "?next={}".format(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_cannot_access(self):
        """
        test that the page redirects if user is in the instructor group but is
        not a staff user
        """
        self.client.force_login(self.instructor_user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_can_delete_sessions(self):
        baker.make_recipe('booking.tue_session', _quantity=2)
        baker.make_recipe('booking.wed_session', _quantity=2)
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

        resp = self.client.post(self.url, data)
        self.assertEqual(Session.objects.count(), 4)

    def test_can_update_existing_session(self):
        self.assertEqual(self.session.advance_payment_required, True)

        self.client.post(self.url, self.formset_data(
                extra_data={'form-0-advance_payment_required': False}
            )
        )
        self.session.refresh_from_db()
        self.assertEqual(self.session.advance_payment_required, False)

    def test_submitting_valid_form_redirects_back_to_timetable(self):
        resp = self.client.post(self.url, self.formset_data())
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:timetable'))


class TimetableSessionUpdateViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(TimetableSessionUpdateViewTests, self).setUp()
        self.session = baker.make_recipe('booking.mon_session')
        self.url = reverse('studioadmin:edit_session', args=[self.session.id])
        self.client.force_login(self.staff_user)

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
        self.client.logout()
        resp = self.client.get(self.url)
        redirected_url = reverse('account_login') + "?next={}".format(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_cannot_access(self):
        """
        test that the page redirects if user is in the instructor group but is
        not a staff user
        """
        self.client.force_login(self.instructor_user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_submitting_valid_session_form_redirects_back_to_timetable(self):
        resp = self.client.post(self.url, self.form_data(self.session))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:timetable'))

    def test_context_data(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.context_data['sidenav_selection'], 'timetable')
        self.assertEqual(resp.context_data['session_day'], 'Monday')

    def test_can_edit_session_data(self):
        self.assertEqual(self.session.day, '01MON')
        resp = self.client.post(self.url, self.form_data(self.session, extra_data={'day': '03WED'}))
        session = Session.objects.get(id=self.session.id)
        self.assertEqual(session.day, '03WED')

    def test_edit_with_categories(self):
        session = baker.make_recipe("booking.mon_session", event_type__event_type="CL")
        assert not session.categories.exists()
        category = baker.make(FilterCategory, category="test ghi")
        form_data = self.form_data(
            ttsession=session, extra_data={'categories': [category.id]}
        )
        resp = self.client.post(reverse('studioadmin:edit_session', args=[session.id]), form_data)
        session.refresh_from_db()
        assert FilterCategory.objects.count() == 1
        assert session.categories.first().category == "test ghi"

    def test_edit_with_new_category(self):
        baker.make(FilterCategory, category="test hij")
        form_data = self.form_data(
            ttsession=self.session, extra_data={'new_category': "Test 1b"}
        )
        resp = self.client.post(self.url, form_data)
        self.session.refresh_from_db()
        assert FilterCategory.objects.count() == 2
        assert self.session.categories.first().category == "Test 1b"

    def test_submitting_with_no_changes_does_not_change_session(self):
        resp = self.client.post(self.url, self.form_data(self.session))
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
        resp = self.client.post(self.url, form_data, follow=True)

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
        resp = self.client.post(self.url, form_data, follow=True)
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
        resp = self.client.post(self.url, form_data, follow=True)
        self.assertIn('No changes made', format_content(str(resp.content)))


class TimetableSessionCreateViewTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.url = reverse('studioadmin:add_session')
    
    def setUp(self):
        self.client.force_login(self.staff_user)

    def form_data(self, extra_data={}):
        ev_type = baker.make_recipe('booking.event_type_PC')
        data = {
            'name': 'test_event',
            'event_type': ev_type.id,
            'day': '01MON',
            'time': '18:00',
            'contact_email': 'test@test.com',
            'contact_person': 'test',
            'cancellation_period': 24,
            'location': Event.LOCATION_CHOICES[0][0],
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
        self.client.logout()
        resp = self.client.get(self.url)
        redirected_url = reverse('account_login') + "?next={}".format(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_cannot_access(self):
        """
        test that the page redirects if user is in the instructor group but is
        not a staff user
        """
        self.client.force_login(self.instructor_user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_submitting_valid_session_form_redirects_back_to_timetable(self):
        resp = self.client.post(self.url, self.form_data())
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:timetable'))

    def test_context_data(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.context_data['sidenav_selection'], 'add_session')

    def test_can_add_event(self):
        self.assertEqual(Session.objects.count(), 0)
        resp = self.client.post(self.url, self.form_data())
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
        resp = self.client.post(self.url, form_data, follow=True)

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
        resp = self.client.post(self.url, form_data, follow=True)
        self.assertNotIn(
            "You have changed the paypal receiver email from the default value.",
            format_content(str(resp.content)).replace('\\', '')
        )
        session1 = Session.objects.latest('id')
        self.assertEqual(session1.paypal_email, settings.DEFAULT_PAYPAL_EMAIL)


class UploadTimetableTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.url = reverse('studioadmin:upload_timetable')
    
    def setUp(self):
        self.client.force_login(self.staff_user)

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        self.client.logout()
        resp = self.client.get(self.url)
        redirected_url = reverse('account_login') + "?next={}".format(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_cannot_access(self):
        """
        test that the page redirects if user is in the instructor group but is
        not a staff user
        """
        self.client.force_login(self.instructor_user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    @patch('studioadmin.forms.timetable_forms.timezone')
    def test_events_are_created(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 6, 1, 0, 0, tzinfo=dt_timezone.utc
        )
        baker.make_recipe('booking.mon_session', _quantity=5)
        self.assertEqual(Event.objects.count(), 0)
        form_data = {
            'start_date': 'Mon 08 Jun 2015',
            'end_date': 'Sun 14 Jun 2015',
            'sessions': [session.id for session in Session.objects.all()],
            'override_options_visible_on_site': "1",
            'override_options_booking_open': "default",
            'override_options_payment_open': "default",
        }
        self.client.post(self.url, form_data)
        self.assertEqual(Event.objects.count(), 5)
        event_names = [event.name for event in Event.objects.all()]
        session_names =  [session.name for session in Session.objects.all()]
        self.assertEqual(sorted(event_names), sorted(session_names))

    @patch('studioadmin.forms.timetable_forms.timezone')
    def test_events_are_created_with_overridden_settings(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 6, 1, 0, 0, tzinfo=dt_timezone.utc
        )
        baker.make_recipe('booking.mon_session', booking_open=True, payment_open=True, _quantity=5)
        self.assertEqual(Event.objects.count(), 0)
        form_data = {
            'start_date': 'Mon 08 Jun 2015',
            'end_date': 'Sun 14 Jun 2015',
            'sessions': [session.id for session in Session.objects.all()],
            'override_options_visible_on_site': "0",
            'override_options_booking_open': "0",
            'override_options_payment_open': "0",
        }
        self.client.post(self.url, form_data)
        self.assertEqual(Event.objects.filter(booking_open=False, payment_open=False, visible_on_site=False).count(), 5)

    @patch('studioadmin.forms.timetable_forms.timezone')
    def test_does_not_create_duplicate_sessions(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 6, 1, 0, 0, tzinfo=dt_timezone.utc
        )
        baker.make_recipe('booking.mon_session', _quantity=5)
        self.assertEqual(Event.objects.count(), 0)
        form_data = {
            'start_date': 'Mon 08 Jun 2015',
            'end_date': 'Sun 14 Jun 2015',
            'sessions': [session.id for session in Session.objects.all()],
            'override_options_visible_on_site': "1",
            'override_options_booking_open': "default",
            'override_options_payment_open': "default",
        }
        self.client.post(self.url, form_data)
        self.assertEqual(Event.objects.count(), 5)

        baker.make_recipe('booking.tue_session', _quantity=2)
        form_data.update(
            {'sessions': [session.id for session in Session.objects.all()]}
        )
        self.assertEqual(Session.objects.count(), 7)
        self.client.post(self.url, form_data)
        self.assertEqual(Event.objects.count(), 7)

    @patch('studioadmin.forms.timetable_forms.timezone')
    def test_upload_timetable_with_duplicate_existing_classes(self, mock_tz):
        """
        add duplicates to context for warning display
        """
        mock_tz.now.return_value = datetime(
            2015, 6, 1, 0, 0, tzinfo=dt_timezone.utc
        )
        session = baker.make_recipe('booking.tue_session', name='test')

        # create date in Europe/London, convert to UTC
        localtz = pytz.timezone('Europe/London')
        local_ev_date = localtz.localize(datetime.combine(
            datetime(2015, 6, 2, 0, 0, tzinfo=dt_timezone.utc),
            session.time)
        )
        converted_ev_date = local_ev_date.astimezone(pytz.utc)

        # create duplicate existing classes for (tues) 2/6/15
        baker.make_recipe(
            'booking.future_PC', name='test', event_type=session.event_type,
            location=session.location,
            date=converted_ev_date,
            _quantity=2)
        self.assertEqual(Event.objects.count(), 2)
        form_data = {
            'start_date': 'Mon 01 Jun 2015',
            'end_date': 'Wed 03 Jun 2015',
            'sessions': [session.id],
            'override_options_visible_on_site': "1",
            'override_options_booking_open': "default",
            'override_options_payment_open': "default",
        }
        resp = self.client.post(self.url, form_data)
        # no new classes created
        self.assertEqual(Event.objects.count(), 2)

        # duplicates in context for template warning
        self.assertEqual(len(resp.context['duplicate_classes']), 1)
        self.assertEqual(resp.context['duplicate_classes'][0]['count'], 2)
        self.assertEqual(
            resp.context['duplicate_classes'][0]['class'].name, 'test'
        )
        # existing in context for template warning (shows first of duplicates only)
        self.assertEqual(len(resp.context['existing_classes']), 1)
        self.assertEqual(resp.context['existing_classes'][0].name, 'test')

    def test_get_upload_timetable_multiple_locations(self):
        session_bp = baker.make_recipe(
            'booking.tue_session', name='test', location="Beaverbank Place"
        )
        session_dm = baker.make_recipe(
            'booking.tue_session', name='test1', location="Davidson's Mains"
        )
        resp = self.client.get(self.url)

        # returns 3 location form with all locations, BP and DM
        self.assertEqual(
            len(resp.context['location_forms']), 3
        )
        self.assertEqual(
            resp.context['location_forms'][0]['location'], "All locations"
        )
        self.assertEqual(
            resp.context['location_forms'][1]['location'], "Beaverbank Place"
        )
        self.assertEqual(
            resp.context['location_forms'][2]['location'], "Davidson's Mains"
        )

        self.assertCountEqual(
            [
                sess.id for sess in
                resp.context['location_forms'][0]['form'].fields['sessions'].queryset
            ],
            [session_bp.id, session_dm.id]
        )
        self.assertCountEqual(
            [
                sess.id for sess in
                resp.context['location_forms'][1]['form'].fields['sessions'].queryset
            ],
            [session_bp.id]
        )
        self.assertCountEqual(
            [
                sess.id for sess in
                resp.context['location_forms'][2]['form'].fields['sessions'].queryset
            ],
            [session_dm.id]
        )

    def test_upload_timetable_with_invalid_form_returns_all_locations(self):
        baker.make_recipe(
            'booking.tue_session', name='test', location="Beaverbank Place"
        )
        session_dm = baker.make_recipe(
            'booking.tue_session', name='test1', location="Davidson's Mains"
        )

        form_data = {
            'start_date': 'invalid date',
            'end_date': 'Wed 03 Jun 2015',
            'sessions': [session_dm.id],
            'override_options_visible_on_site': "1",
            'override_options_booking_open': "default",
            'override_options_payment_open': "default",
        }

        resp = self.client.post(self.url, form_data)

        # returns one location form with all locations
        self.assertEqual(
            len(resp.context['location_forms']), 1
        )
        self.assertEqual(
            resp.context['location_forms'][0]['location'], 'All locations'
        )
        # checked sessions are retained
        self.assertEqual(
            resp.context['location_forms'][0]['form'].data['sessions'],
            str(session_dm.id)
        )
    
    @patch('studioadmin.forms.timetable_forms.timezone')
    def test_events_are_created_with_categories(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 6, 1, 0, 0, tzinfo=dt_timezone.utc
        )
        cat1 = baker.make(FilterCategory, category="cat 1")
        cat2 = baker.make(FilterCategory, category="cat 2")
        session1 = baker.make_recipe('booking.mon_session', name="Mon")
        session1.categories.add(cat1)
        session2 = baker.make_recipe('booking.tue_session', name="Tues")
        session2.categories.add(cat1)
        session2.categories.add(cat2)
        baker.make_recipe('booking.wed_session', name="Wed")

        assert not Event.objects.exists()
        form_data = {
            'start_date': 'Mon 08 Jun 2015',
            'end_date': 'Sun 14 Jun 2015',
            'sessions': [session.id for session in Session.objects.all()],
            'override_options_visible_on_site': "1",
            'override_options_booking_open': "default",
            'override_options_payment_open': "default",
        }

        self.client.post(self.url, form_data)
        assert Event.objects.count() == 3
        mon = Event.objects.get(name="Mon")
        assert list(mon.categories.all()) == [cat1]
        tues = Event.objects.get(name="Tues")
        assert list(tues.categories.all()) == [cat1, cat2]
        wed = Event.objects.get(name="Wed")
        assert list(wed.categories.all()) == []


class CloneEventTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.client.login(username=self.staff_user.username, password='test')
        cat1 = baker.make(FilterCategory, category="cat 1")
        cat2 = baker.make(FilterCategory, category="cat 2")
        self.session = baker.make_recipe('booking.mon_session', name="Mon")
        self.session.categories.add(cat1, cat2)
        self.url = reverse("studioadmin:clone_timetable_session", args=(self.session.id,))

    def test_clone_session(self):
        assert Session.objects.count() == 1
        self.client.get(self.url)

        assert Session.objects.count() == 2
        cloned = Session.objects.latest("id")
        assert cloned.name == "[CLONED] Mon"

        self.client.get(self.url)
        assert Session.objects.count() == 3
        cloned = Session.objects.latest("id")
        assert cloned.name == "[CLONED] Mon_1"

        self.client.get(self.url)
        assert Session.objects.count() == 4
        cloned = Session.objects.latest("id")
        assert cloned.name == "[CLONED] Mon_2"

        for session in Session.objects.all():
            assert set(session.categories.values_list("category", flat=True)) == {"cat 1", "cat 2"}
