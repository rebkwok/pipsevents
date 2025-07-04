# -*- coding: utf-8 -*-
import pytz

from model_bakery import baker

from django import forms
from django.conf import settings
from django.test import TestCase

from booking.models import Event, EventType, FilterCategory
from studioadmin.forms import EventAdminForm, OnlineTutorialAdminForm


class EventAdminFormTests(TestCase):

    def setUp(self):
        self.event_type = baker.make_recipe('booking.event_type_PC')
        self.event_type_ev = baker.make_recipe('booking.event_type_OE')
        self.event_type_oc = baker.make_recipe('booking.event_type_OC')
        self.event_type_ot = baker.make_recipe('booking.event_type_OT')


    def form_data(self, extra_data={}):
        data = {
            'name': 'test_event',
            'event_type': self.event_type.id,
            'date': '15 Jun 2015 18:00',
            'contact_email': 'test@test.com',
            'contact_person': 'test',
            'cancellation_period': 24,
            'location': Event.LOCATION_CHOICES[0][0],
            'allow_booking_cancellation': True,
            'paypal_email': settings.DEFAULT_PAYPAL_EMAIL,
            "cost": 5,
        }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_form_valid(self):
        form = EventAdminForm(data=self.form_data(), ev_type='CL')
        assert form.is_valid()

    def test_filter_categories(self):
        form = EventAdminForm(ev_type='CL')
        assert isinstance(form.fields["categories"].widget, forms.CheckboxSelectMultiple)
        assert isinstance(form.fields["new_category"].widget, forms.TextInput)
        assert list(form.fields["categories"].queryset) == list(FilterCategory.objects.all())
    
    def test_new_filter_category_exists(self):
        baker.make(FilterCategory, category="test bcd")
        data = self.form_data({"new_category": "Test BCD"})
        form = EventAdminForm(data=data, ev_type='CL')
        assert not form.is_valid()
        assert form.errors == {
            "new_category": ["Category already exists"]
        }

    def test_form_for_cancelled_events(self):
        event = baker.make_recipe('booking.future_PC', event_type=self.event_type)
        data = {
            'id': event.id,
            'name': event.name,
            'event_type': self.event_type.id,
            'date': event.date.astimezone(
                pytz.timezone('Europe/London')
            ).strftime('%d %b %Y %H:%M'),
            'contact_email': event.contact_email,
            'contact_person': event.contact_person,
            'cancellation_period': event.cancellation_period,
            'location': event.location,
            'allow_booking_cancellation': True,
            'paypal_email': event.paypal_email,
            "cost": 5,
        }
        form = EventAdminForm(data=data, instance=event, ev_type='CL')
        self.assertTrue(form.is_valid())
        # event is not cancelled, so cancelled checkbox is hidden
        cancelled_field = form.fields['cancelled']
        assert cancelled_field.disabled
        self.assertEqual(
            cancelled_field.help_text,
            'To cancel, use the Cancel button on the class list page'
        )

        event.cancelled = True
        event.save()
        data.update({'cancelled': True})
        form = EventAdminForm(data=data, instance=event, ev_type='CL')
        cancelled_field = form.fields['cancelled']
        self.assertTrue(form.is_valid())
        self.assertEqual(
            cancelled_field.widget.attrs,
            {'class': 'form-check-input'}
        )
        self.assertEqual(
            cancelled_field.help_text,
            'Untick to reopen class; note that this does not change any other '
            'attributes and does not reopen previously cancelled bookings.  '
            'Class will be reopened with both booking and payment CLOSED'
        )

    def test_form_with_invalid_contact_person(self):
        form = EventAdminForm(
            data=self.form_data({'contact_person': ''}), ev_type='CL')
        self.assertFalse(form.is_valid())
        self.assertEqual(len(form.errors), 1)
        self.assertIn('contact_person', form.errors.keys())
        self.assertIn(['This field is required.'], form.errors.values())

    def test_form_with_invalid_contact_email(self):
        form = EventAdminForm(
            data=self.form_data({'contact_email': ''}), ev_type='CL')
        self.assertFalse(form.is_valid())
        self.assertEqual(len(form.errors), 1)
        self.assertIn('contact_email', form.errors.keys())
        self.assertIn(['This field is required.'], form.errors.values())

        form = EventAdminForm(
            data=self.form_data({'contact_email': 'test_email'}), ev_type='CL')
        self.assertFalse(form.is_valid())
        self.assertEqual(len(form.errors), 1)
        self.assertIn('contact_email', form.errors.keys())
        self.assertIn(['Enter a valid email address.'], form.errors.values())

    def test_event_type_queryset(self):
        form = EventAdminForm(
            data=self.form_data(), ev_type='EV')
        ev_type_field = form.fields['event_type']
        self.assertEqual(
            set(EventType.objects.filter(id=self.event_type_ev.id)),
            set(ev_type_field.queryset)
        )
        self.assertEqual(len(ev_type_field.queryset), 1)

        form = EventAdminForm(
            data=self.form_data(), ev_type='CL')
        ev_type_field = form.fields['event_type']
        self.assertEqual(
            set(EventType.objects.filter(
                id__in=[self.event_type.id, self.event_type_oc.id]
            )),
            set(ev_type_field.queryset)
        )
        self.assertEqual(len(ev_type_field.queryset), 2)

    def test_event_type_queryset_room_hire(self):
        rh_type = baker.make_recipe('booking.event_type_RH')
        form = EventAdminForm(
            data=self.form_data(), ev_type='EV')
        ev_type_field = form.fields['event_type']
        self.assertEqual(
            set(EventType.objects.filter(id=self.event_type_ev.id)),
            set(ev_type_field.queryset)
        )
        self.assertEqual(len(ev_type_field.queryset), 1)

        form = EventAdminForm(
            data=self.form_data(), ev_type='CL')
        ev_type_field = form.fields['event_type']
        self.assertEqual(
            set(EventType.objects.filter(
                id__in=[self.event_type.id, self.event_type_oc.id]
            )),
            set(ev_type_field.queryset)
        )
        self.assertEqual(len(ev_type_field.queryset), 2)

        form = EventAdminForm(
            data=self.form_data(), ev_type='RH')
        ev_type_field = form.fields['event_type']
        self.assertEqual(
            set(EventType.objects.filter(
                id=rh_type.id
            )),
            set(ev_type_field.queryset)
        )
        self.assertEqual(len(ev_type_field.queryset), 1)

    def test_invalid_date(self):
        form = EventAdminForm(
            data=self.form_data(
                {'date': '15 Jun 2015 25:00'}), ev_type='CL')
        self.assertFalse(form.is_valid())
        self.assertIn('Invalid date format', str(form.errors['date']))

    def test_invalid_payment_due_date(self):
        form = EventAdminForm(
            data=self.form_data(
                {'payment_due_date': '31 Jun 2015'}), ev_type='CL')
        self.assertFalse(form.is_valid())
        self.assertIn('Invalid date format', str(form.errors['payment_due_date']))

    def test_payment_due_date_after_cancellation_period(self):
        form = EventAdminForm(
            data=self.form_data(
                {'date': '15 Jun 2015 20:00',
                 'payment_due_date': '16 Jun 2015'},
            ), ev_type='CL')
        self.assertFalse(form.is_valid())
        self.assertIn('Payment due date must be before cancellation period '
                      'starts', str(form.errors['payment_due_date']))

    def test_valid_payment_due_date(self):
        form = EventAdminForm(
            data=self.form_data(
                {
                 'advance_payment_required': True,
                 'date': '15 Jun 2015 20:00',
                 'payment_due_date': '10 Jun 2015',
                 'cost': 1
                },
            ), ev_type='CL')
        self.assertTrue(form.is_valid())

    def test_name_placeholder(self):
        form = EventAdminForm(data=self.form_data(), ev_type='EV')
        name_field = form.fields['name']
        self.assertEqual(
            name_field.widget.attrs['placeholder'],
            'Name of event e.g. Workshop')

        form = EventAdminForm(data=self.form_data(), ev_type='CL')
        name_field = form.fields['name']
        self.assertEqual(
            name_field.widget.attrs['placeholder'],
            'Name of class e.g. Pole Level 1')

    def test_adv_payment_req_requires_due_date_or_time_or_cancel_period(self):
        form = EventAdminForm(
            data=self.form_data(
                {
                    'advance_payment_required': True,
                    'cancellation_period': 0,
                    'cost': 1,
                },
            ),
            ev_type='CL'
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'Please provide a payment due date, payment time allowed or '
            'cancellation period',
            str(form.errors['advance_payment_required'])
        )

        form = EventAdminForm(
            data=self.form_data(
                {
                    'advance_payment_required': True,
                    'payment_due_date': '30 Jun 2015',
                    'payment_time_allowed': 4,
                    'cancellation_period': 1,
                    'cost': 1,
                },
            ),
            ev_type='CL'
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'Please provide payment due date OR payment time '
            'allowed (but not both)',
            str(form.errors['payment_due_date'])
        )
        self.assertIn(
            'Please provide payment due date OR payment time '
            'allowed (but not both)',
            str(form.errors['payment_time_allowed'])
        )

        form = EventAdminForm(
            data=self.form_data(
                {
                    'advance_payment_required': True,
                    'payment_due_date': '01 Jun 2015',
                    'cancellation_period': 1,
                    'cost': 1,
                },
            ),
            ev_type='CL'
        )
        self.assertTrue(form.is_valid())

        form = EventAdminForm(
            data=self.form_data(
                {
                    'advance_payment_required': True,
                    'payment_time_allowed': 4,
                    'cancellation_period': 1,
                    'cost': 1,
                },
            ),
            ev_type='CL'
        )
        self.assertTrue(form.is_valid())

    def test_payment_due_date_requires_advance_payment_req(self):
        form = EventAdminForm(
            data=self.form_data(
                {
                    'advance_payment_required': False,
                    'payment_due_date': '01 Jun 2015',
                    'cost': 1,
                },
            ),
            ev_type='CL'
        )
        self.assertFalse(form.is_valid())

        self.assertIn(
            'To specify a payment due date, please also tick '
            '&quot;advance payment required&quot',
            str(form.errors['payment_due_date'])
        )

    def test_payment_time_allowed_requires_advance_payment_req(self):
        form = EventAdminForm(
            data=self.form_data(
                {
                    'advance_payment_required': False,
                    'payment_time_allowed': 4,
                    'cost': 1,
                },
            ),
            ev_type='CL'
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'To specify payment time allowed, please also tick '
            '&quot;advance payment required&quot;',
            str(form.errors['payment_time_allowed'])
        )

    def test_adv_payment_due_date_and_time_allowed_require_event_cost(self):
        form = EventAdminForm(
            data=self.form_data(
                {
                    'advance_payment_required': True,
                    'cost': ''
                },
            ),
            ev_type='CL'
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'The following fields require a cost greater than £0: '
            'advance payment required',
            str(form.errors['cost'])
        )

        form = EventAdminForm(
            data=self.form_data(
                {
                    'payment_due_date': '01 Jun 2015',
                    'advance_payment_required': True,
                    'cost': ''
                },
            ),
            ev_type='CL'
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'The following fields require a cost greater than £0: '
            'advance payment required, payment due date',
            str(form.errors['cost'])
        )

        form = EventAdminForm(
            data=self.form_data(
                {
                    'payment_time_allowed': 4,
                    'advance_payment_required': True,
                    'cost': ''
                },
            ),
            ev_type='CL'
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'The following fields require a cost greater than £0: '
            'advance payment required, payment time allowed',
            str(form.errors['cost'])
        )

    def test_disallow_booking_cancellation_requires_adv_payment_required(self):
        form = EventAdminForm(
            data=self.form_data(
                {'allow_booking_cancellation': False, 'cost': 1}),
            ev_type='CL'
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'Advance payment must be required in order to make booking '
            'cancellation disallowed (i.e. non-refundable)',
            str(form.errors['allow_booking_cancellation'])
        )

    def test_disallow_booking_cancellation_requires_cost(self):
        form = EventAdminForm(
            data=self.form_data(
                {'allow_booking_cancellation': False, 'cost': 0}
            ),
            ev_type='CL'
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'Booking cancellation should be allowed for events/classes with '
            'no associated cost',
            str(form.errors['allow_booking_cancellation'])
        )

    def test_paypal_email_check_required_if_paypal_email_changed(self):
        form = EventAdminForm(
            data=self.form_data(
                {'paypal_email': 'newpaypal@test.com'}),
            ev_type='CL'
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'Please reenter paypal email to confirm changes',
            str(form.errors['paypal_email_check'])
        )

    def test_paypal_email_and_check_must_match(self):
        form = EventAdminForm(
            data=self.form_data(
                {
                    'paypal_email': 'newpaypal@test.com',
                    'paypal_email_check': 'newpaypal1@test.com'
                },
            ),
            ev_type='CL'
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

        form = EventAdminForm(
            data=self.form_data(
                {
                    'paypal_email': 'newpaypal@test.com',
                    'paypal_email_check': 'newpaypal@test.com'
                },
            ),
            ev_type='CL'
        )
        self.assertTrue(form.is_valid())

    def test_online_tutorial_form_initial(self):
        form = OnlineTutorialAdminForm(ev_type='OT')
        for field in [
            "video_link_available_after_class",
            "advance_payment_required",

        ]:
            assert form.fields[field].initial == True
        
        for field in [
            "allow_booking_cancellation",
            "email_studio_when_booked",

        ]:
            assert form.fields[field].initial == False
        
        for field in [
            "max_participants",
            "payment_due_date",

        ]:
            assert form.fields[field].initial is None

        assert form.fields["location"].initial == "Online"
        assert form.fields["payment_time_allowed"].initial == 4

    def test_online_tutorial_form_valid(self):
        data = {
            'name': 'test_tutorial',
            'event_type': self.event_type_ot.id,
            'date': '15 Jun 2015 18:00',
            'contact_email': 'test@test.com',
            'contact_person': 'test',
            'cancellation_period': 24,
            'location': "Online",
            'paypal_email': settings.DEFAULT_PAYPAL_EMAIL,
            'video_link': "http://foo.com"
        }
        form = OnlineTutorialAdminForm(data=data, ev_type='OT')
        assert form.is_valid()

    def test_online_tutorial_with_instance_form_valid(self):
        tutorial = baker.make_recipe("booking.future_OT", event_type=self.event_type_ot, cost=10)
        data = {
            'id': tutorial.id,
            'name': tutorial.name,
            'event_type': self.event_type_ot.id,
            'date': '15 Jun 2015 18:00',
            'contact_email': 'test@test.com',
            'contact_person': 'test',
            'cancellation_period': 24,
            'location': "Online",
            'paypal_email': settings.DEFAULT_PAYPAL_EMAIL,
            'video_link': "http://foo.com",
            "cost": 10,
            "advance_payment_required": True 
        }
        form = OnlineTutorialAdminForm(instance=tutorial, data=data, ev_type='OT')
        assert form.is_valid()
    
    def test_online_tutorial_with_instance_no_cost_form_valid(self):
        data = {
            'name': "tutorial",
            'event_type': self.event_type_ot.id,
            'date': '15 Jun 2015 18:00',
            'contact_email': 'test@test.com',
            'contact_person': 'test',
            'cancellation_period': 24,
            'location': "Online",
            'paypal_email': settings.DEFAULT_PAYPAL_EMAIL,
            'video_link': "http://foo.com",
            # these will be reset in the form clean method because cost is 0
            "allow_booking_cancellation": False,
            "advance_payment_required": True,
            "payment_due_date": '14 Jun 2015',
            "payment_time_allowed": 4,

        }
        
        def assert_non_cost(form_data):
            form = OnlineTutorialAdminForm(data=data, ev_type='OT')
            assert form.is_valid()
            assert form.cleaned_data["advance_payment_required"] == False
            assert form.cleaned_data["allow_booking_cancellation"] == True
            assert form.cleaned_data["payment_due_date"] == None
            assert form.cleaned_data["payment_time_allowed"] == None
            assert form.cleaned_data["cost"] == 0
        
        # no cost in posted data
        assert_non_cost(data)

        # non-cost values
        for cost in [None, -1, 0]:
            assert_non_cost(data)
