# -*- coding: utf-8 -*-

from datetime import datetime
from mock import patch
from model_mommy import mommy

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from booking.models import EventType

from studioadmin.forms import DAY_CHOICES, TimetableSessionFormSet, \
    SessionAdminForm, UploadTimetableForm
from timetable.models import Session


class TimetableSessionFormSetTests(TestCase):

    def setUp(self):
        self.session = mommy.make(Session)

    def formset_data(self, extra_data={}):

        data = {
            'form-TOTAL_FORMS': 1,
            'form-INITIAL_FORMS': 1,
            'form-0-id': str(self.session.id),
            'form-0-cost': '7',
            'form-0-max-participants': '10',
            'form-0-booking_open': 'on',
            'form-0-payment_open': 'on',
            }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_event_formset_valid(self):
        formset = TimetableSessionFormSet(data=self.formset_data())
        self.assertTrue(formset.is_valid())

    def test_additional_form_data(self):
        formset = TimetableSessionFormSet(
            data=self.formset_data(), queryset=Session.objects.all())
        form =formset.forms[0]
        self.assertEquals(form.formatted_day, DAY_CHOICES[self.session.day])
        self.assertEquals(form.booking_open_id, 'booking_open_0')
        self.assertEquals(form.payment_open_id, 'payment_open_0')

    def test_can_delete(self):
        session_to_delete = mommy.make(Session)
        extra_data = {
            'form-TOTAL_FORMS': 2,
            'form-INITIAL_FORMS': 2,
            'form-1-DELETE': 'on',
            'form-1-id': session_to_delete.id,
            'form-1-cost': '7',
            'form-1-max-participants': '10',
            'form-1-booking_open': 'on',
            'form-1-payment_open': 'on',
            }
        formset = TimetableSessionFormSet(data=self.formset_data(extra_data),
                               queryset=Session.objects.all())
        self.assertEqual(len(formset.deleted_forms), 1)
        deleted_form = formset.deleted_forms[0]
        self.assertEqual(deleted_form.cleaned_data['id'], session_to_delete)


class SessionAdminFormTests(TestCase):

    def setUp(self):
        self.event_type = mommy.make_recipe('booking.event_type_PC')
        self.event_type_ev = mommy.make_recipe('booking.event_type_OE')
        self.event_type_oc = mommy.make_recipe('booking.event_type_OC')

    def form_data(self, extra_data={}):
        data = {
            'name': 'test_event',
            'event_type': self.event_type.id,
            'day': '01MON',
            'time': '12:00',
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

    def test_form_valid(self):

        form = SessionAdminForm(data=self.form_data())
        self.assertTrue(form.is_valid())

    def test_form_with_invalid_contact_person(self):
        form = SessionAdminForm(
            data=self.form_data({'contact_person': ''}))
        self.assertFalse(form.is_valid())
        self.assertEquals(len(form.errors), 1)
        self.assertIn('contact_person', form.errors.keys())
        self.assertIn(['This field is required.'], form.errors.values())

    def test_form_with_invalid_contact_email(self):
        form = SessionAdminForm(
            data=self.form_data({'contact_email': ''}))
        self.assertFalse(form.is_valid())
        self.assertEquals(len(form.errors), 1)
        self.assertIn('contact_email', form.errors.keys())
        self.assertIn(['This field is required.'], form.errors.values())

        form = SessionAdminForm(
            data=self.form_data({'contact_email': 'test_email'}))
        self.assertFalse(form.is_valid())
        self.assertEquals(len(form.errors), 1)
        self.assertIn('contact_email', form.errors.keys())
        self.assertIn(['Enter a valid email address.'], form.errors.values())

    def test_event_type_queryset_excludes_events(self):
        form = SessionAdminForm(data=self.form_data())
        ev_type_field = form.fields['event_type']
        self.assertEqual(
            set(EventType.objects.filter(event_type='CL')),
            set(ev_type_field.queryset)
        )
        self.assertEquals(ev_type_field.queryset.count(), 2)
        self.assertEqual(
            set(EventType.objects.filter(
                id__in=[self.event_type.id, self.event_type_oc.id]
            )),
            set(ev_type_field.queryset)
        )

    def test_event_type_queryset_inlcudes_room_hire_and_classes(self):

        rh_type = mommy.make_recipe('booking.event_type_RH')

        form = SessionAdminForm(data=self.form_data())
        ev_type_field = form.fields['event_type']
        self.assertEqual(
            set(EventType.objects.filter(
                id__in=[self.event_type.id, self.event_type_oc.id, rh_type.id]
            )),
            set(ev_type_field.queryset)
        )
        self.assertEquals(ev_type_field.queryset.count(), 3)

    def test_invalid_time(self):
        form = SessionAdminForm(
            data=self.form_data(
                {'time': '25:00'}))
        self.assertFalse(form.is_valid())
        self.assertIn('Invalid time format', str(form.errors['time']))

    def test_name_placeholder(self):
        form = SessionAdminForm(data=self.form_data())
        name_field = form.fields['name']
        self.assertEquals(
            name_field.widget.attrs['placeholder'],
            'Name of session e.g. Pole Level 1')

    def test_disallow_booking_cancellation_requires_adv_payment_required(self):
        form = SessionAdminForm(
            data=self.form_data(
                {'allow_booking_cancellation': False, 'cost': 1}
            )
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'Advance payment must be required in order to make booking '
            'cancellation disallowed (i.e. non-refundable)',
            str(form.errors['allow_booking_cancellation'])
        )

    def test_disallow_booking_cancellation_requires_cost(self):
        form = SessionAdminForm(
            data=self.form_data(
                {'allow_booking_cancellation': False}
            )
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'Booking cancellation should be allowed for events/classes with '
            'no associated cost',
            str(form.errors['allow_booking_cancellation'])
        )

    def test_paypal_email_check_required_if_paypal_email_changed(self):
        form = SessionAdminForm(
            data=self.form_data(
                {'paypal_email': 'newpaypal@test.com'}),
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'Please reenter paypal email to confirm changes',
            str(form.errors['paypal_email_check'])
        )

    def test_paypal_email_and_check_must_match(self):
        form = SessionAdminForm(
            data=self.form_data(
                {
                    'paypal_email': 'newpaypal@test.com',
                    'paypal_email_check': 'newpaypal1@test.com'
                },
            )
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'Email addresses do not match',
            str(form.errors['paypal_email_check'])
        )
        self.assertIn(
            'Email addresses do not match',
            str(form.errors['paypal_email'])
        )

        form = SessionAdminForm(
            data=self.form_data(
                {
                    'paypal_email': 'newpaypal@test.com',
                    'paypal_email_check': 'newpaypal@test.com'
                },
            )
        )
        self.assertTrue(form.is_valid())

    def test_fields_requiring_cost(self):
        form = SessionAdminForm(
            data=self.form_data(
                {
                    'cost': 0,
                    'advance_payment_required': True,
                    'payment_time_allowed': '',
                },
            )
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'The following fields require a cost greater than £0: '
            'advance payment required',
            str(form.errors['cost'])
        )

        form = SessionAdminForm(
            data=self.form_data(
                {
                    'cost': 0,
                    'payment_time_allowed': 6,
                    'advance_payment_required': True,
                },
            )
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'The following fields require a cost greater than £0: '
            'advance payment required, payment time allowed',
            str(form.errors['cost'])
        )

    def test_payment_time_allowed_required_advance_payment_required(self):
        form = SessionAdminForm(
            data=self.form_data(
                {
                    'advance_payment_required': False,
                    'payment_time_allowed': '',
                },
            )
        )
        self.assertTrue(form.is_valid())

        form = SessionAdminForm(
            data=self.form_data(
                {
                    'advance_payment_required': False,
                    'payment_time_allowed': 6,
                },
            )
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'To specify payment time allowed, please also tick &quot;advance '
            'payment required&quot;',
            str(form.errors['payment_time_allowed'])
        )


class UploadTimetableFormTests(TestCase):

    def setUp(self):
        self.session = mommy.make_recipe('booking.mon_session')

    def form_data(self, extra_data={}):
        data = {
            'start_date': 'Mon 08 Jun 2015',
            'end_date': 'Mon 15 Jun 2015',
            'sessions': [self.session.id]
        }

        for key, value in extra_data.items():
            data[key] = value

        return data

    @patch('studioadmin.forms.timetable_forms.timezone')
    def test_form_valid(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 6, 6, 12, 0, tzinfo=timezone.utc
            )
        form = UploadTimetableForm(data=self.form_data())
        self.assertTrue(form.is_valid())

    @patch('studioadmin.forms.timetable_forms.timezone')
    def test_start_and_end_date_required(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 6, 6, 12, 0, tzinfo=timezone.utc
            )
        form = UploadTimetableForm(
            data={'sessions': [self.session.id]}
        )
        self.assertFalse(form.is_valid())
        self.assertEquals(len(form.errors), 2)
        self.assertEquals(
            form.errors.get('start_date'), ['This field is required.']
        )
        self.assertEquals(
            form.errors.get('end_date'), ['This field is required.']
        )

    @patch('studioadmin.forms.timetable_forms.timezone')
    def test_invalid_start_date_format(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 6, 6, 12, 0, tzinfo=timezone.utc
            )
        form = UploadTimetableForm(
            data=self.form_data({'start_date': 'Monday 08 June 2015'})
        )
        self.assertFalse(form.is_valid())
        self.assertEquals(len(form.errors), 1)
        self.assertIn('Invalid date format', str(form.errors['start_date']))

    @patch('studioadmin.forms.timetable_forms.timezone')
    def test_start_date_in_past(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 6, 6, 12, 0, tzinfo=timezone.utc
            )
        form = UploadTimetableForm(
            data=self.form_data({'start_date': 'Mon 08 Jun 2000'})
        )
        self.assertFalse(form.is_valid())
        self.assertEquals(len(form.errors), 1)
        self.assertIn('Must be in the future', str(form.errors['start_date']))

    @patch('studioadmin.forms.timetable_forms.timezone')
    def test_invalid_end_date_format(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 6, 6, 12, 0, tzinfo=timezone.utc
            )
        form = UploadTimetableForm(
            data=self.form_data({'end_date': 'Monday 15 June 2015'})
        )
        self.assertFalse(form.is_valid())
        self.assertEquals(len(form.errors), 1)
        self.assertIn('Invalid date format', str(form.errors['end_date']))

    @patch('studioadmin.forms.timetable_forms.timezone')
    def test_end_date_before_start_date(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 6, 6, 12, 0, tzinfo=timezone.utc
            )
        form = UploadTimetableForm(
            data=self.form_data({
                'start_date': 'Tue 16 Jun 2015',
                'end_date': 'Mon 15 Jun 2015'
            })
        )
        self.assertFalse(form.is_valid())
        self.assertEquals(len(form.errors), 1)
        self.assertEquals(
            form.errors['end_date'],
            ['Cannot be before start date']
        )
