from datetime import timedelta
from model_mommy import mommy

from django.test import TestCase
from django.utils import timezone

from booking.models import EventType, Block
from studioadmin.forms import (
    DAY_CHOICES,
    EventFormSet,
    EventAdminForm,
    SimpleBookingRegisterFormSet,
    StatusFilter,
    ConfirmPaymentForm,
    TimetableSessionFormSet,
    SessionAdminForm,
    UploadTimetableForm
)
from timetable.models import Session


class EventFormSetTests(TestCase):

    def setUp(self):
        self.event = mommy.make_recipe('booking.future_EV')
        self.event1 = mommy.make_recipe('booking.future_EV')
        mommy.make_recipe('booking.booking', event=self.event1)

    def formset_data(self, extra_data={}):

        data = {
            'form-TOTAL_FORMS': 1,
            'form-INITIAL_FORMS': 1,
            'form-0-id': str(self.event.id),
            'form-0-cost': '7',
            'form-0-max-participants': '10',
            'form-0-booking_open': 'on',
            'form-0-payment_open': 'on',
            }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_event_formset_valid(self):
        formset = EventFormSet(data=self.formset_data())
        self.assertTrue(formset.is_valid())

    def test_event_formset_not_valid(self):
        formset = EventFormSet(
            data=self.formset_data({'form-0-cost': 'seven'})
        )
        self.assertIn({'cost': ['Enter a number.']}, formset.errors)
        self.assertFalse(formset.is_valid())

    def test_event_formset_delete(self):
        extra_data = {
            'form-TOTAL_FORMS': 2,
            'form-INITIAL_FORMS': 2,
            'form-0-DELETE': 'on',
            'form-1-id': self.event1.id,
            'form-1-cost': '7',
            'form-1-max-participants': '10',
            'form-1-booking_open': 'on',
            'form-1-payment_open': 'on',
            }
        formset = EventFormSet(data=self.formset_data(extra_data))
        self.assertEqual(len(formset.deleted_forms), 1)
        deleted_form = formset.deleted_forms[0]
        self.assertEqual(deleted_form.cleaned_data['id'], self.event)

    def test_event_formset_delete_with_bookings(self):
        """
        Test delete widget is disabled if bookings made against event
        """
        extra_data = {
            'form-TOTAL_FORMS': 2,
            'form-INITIAL_FORMS': 2,
            'form-0-DELETE': 'on',
            'form-1-id': str(self.event1.id),
            'form-1-cost': '7',
            'form-1-max-participants': '10',
            'form-1-booking_open': 'on',
            'form-1-payment_open': 'on',
            'form-1-DELETE': 'on',
            }
        formset = EventFormSet(data=self.formset_data(extra_data))
        deleted_form_no_bookings = formset.deleted_forms[0]
        deleted_form_with_bookings = formset.deleted_forms[1]
        self.assertEqual(deleted_form_no_bookings.cleaned_data['id'], self.event)
        self.assertEqual(deleted_form_with_bookings.cleaned_data['id'], self.event1)

        delete_no_bookings_widget = deleted_form_no_bookings.fields['DELETE'].widget
        delete_with_bookings_widget = deleted_form_with_bookings.fields['DELETE'].widget
        self.assertEqual(
            delete_no_bookings_widget.attrs['class'],
            'delete-checkbox studioadmin-list'
        )
        self.assertEqual(
            delete_with_bookings_widget.attrs['class'],
            'delete-checkbox-disabled studioadmin-list'
        )


class EventAdminFormTests(TestCase):

    def setUp(self):
        self.event_type = mommy.make_recipe('booking.event_type_PC')
        self.event_type_ev = mommy.make_recipe('booking.event_type_OE')
        self.event_type_oc = mommy.make_recipe('booking.event_type_OC')

    def form_data(self, extra_data={}):
        data = {
            'name': 'test_event',
            'event_type': self.event_type.id,
            'date': '15 Jun 2015 18:00',
            'contact_email': 'test@test.com',
            'contact_person': 'test',
            'cancellation_period': 24,
            'location': 'Watermelon Studio'
        }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_form_valid(self):

        form = EventAdminForm(data=self.form_data(), ev_type='CL')
        self.assertTrue(form.is_valid())

    def test_form_with_invalid_contact_person(self):
        form = EventAdminForm(
            data=self.form_data({'contact_person': ''}), ev_type='CL')
        self.assertFalse(form.is_valid())
        self.assertEquals(len(form.errors), 1)
        self.assertIn('contact_person', form.errors.keys())
        self.assertIn(['This field is required.'], form.errors.values())

    def test_form_with_invalid_contact_email(self):
        form = EventAdminForm(
            data=self.form_data({'contact_email': ''}), ev_type='CL')
        self.assertFalse(form.is_valid())
        self.assertEquals(len(form.errors), 1)
        self.assertIn('contact_email', form.errors.keys())
        self.assertIn(['This field is required.'], form.errors.values())

        form = EventAdminForm(
            data=self.form_data({'contact_email': 'test_email'}), ev_type='CL')
        self.assertFalse(form.is_valid())
        self.assertEquals(len(form.errors), 1)
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
        self.assertEquals(len(ev_type_field.queryset), 1)

        form = EventAdminForm(
            data=self.form_data(), ev_type='CL')
        ev_type_field = form.fields['event_type']
        self.assertEqual(
            set(EventType.objects.filter(
                id__in=[self.event_type.id, self.event_type_oc.id]
            )),
            set(ev_type_field.queryset)
        )
        self.assertEquals(len(ev_type_field.queryset), 2)

    def test_invalid_date(self):
        form = EventAdminForm(
            data=self.form_data(
                {'date': '15 Jun 2015 25:00'}), ev_type='CL')
        self.assertFalse(form.is_valid())
        self.assertIn('Invalid date format', str(form.errors['date']))

    def test_invalid_payment_due_date(self):
        form = EventAdminForm(
            data=self.form_data(
                {'date': '15 Jun 2015 20:00',
                 'payment_due_date': '16 Jun 2015'},
            ), ev_type='CL')
        self.assertFalse(form.is_valid())
        self.assertIn('Payment due date must be before cancellation period '
                      'starts', str(form.errors['payment_due_date']))

    def test_name_placeholder(self):
        form = EventAdminForm(data=self.form_data(), ev_type='EV')
        name_field = form.fields['name']
        self.assertEquals(
            name_field.widget.attrs['placeholder'],
            'Name of event e.g. Workshop')

        form = EventAdminForm(data=self.form_data(), ev_type='CL')
        name_field = form.fields['name']
        self.assertEquals(
            name_field.widget.attrs['placeholder'],
            'Name of class e.g. Pole Level 1')

class SimpleBookingRegisterFormSetTests(TestCase):

    def setUp(self):
        self.event = mommy.make_recipe('booking.future_EV')
        self.user = mommy.make_recipe('booking.user')
        self.block_type = mommy.make_recipe('booking.blocktype',
                                       event_type=self.event.event_type,)
        self.active_block = mommy.make_recipe('booking.block',
                                       block_type=self.block_type,
                                       user=self.user,
                                       paid=True)
        self.booking = mommy.make_recipe(
            'booking.booking', event=self.event, user=self.user
        )

    def formset_data(self, extra_data={}):

        data = {
            'bookings-TOTAL_FORMS': 1,
            'bookings-INITIAL_FORMS': 1,
            'bookings-0-id': self.booking.id,
            'bookings-0-user': self.user.id,
            'bookings-0-block': self.active_block.id,
            'bookings-0-paid': 'on',
            'bookings-0-attended': 'off'
            }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_form_valid(self):
        formset = SimpleBookingRegisterFormSet(data=self.formset_data(),
                                               instance=self.event)
        self.assertTrue(formset.is_valid(), formset.errors)

    def test_additional_data_in_form(self):
        formset = SimpleBookingRegisterFormSet(data=self.formset_data(),
                                               instance=self.event)
        form = formset.forms[0]
        self.assertEquals(form.index, 1)
        self.assertEquals(form.available_block, self.active_block)
        self.assertEquals(form.checkbox_paid_id, 'checkbox_paid_0')
        self.assertEquals(form.checkbox_attended_id, 'checkbox_attended_0')

    def test_block_queryset_with_other_event_types(self):
        """
        Only blocks with the same event type as the event instance should
        appear in the block dropdown
        """
        mommy.make_recipe('booking.block', user=self.user, paid=True,
                          _quantity=5)
        formset = SimpleBookingRegisterFormSet(data=self.formset_data(),
                                               instance=self.event)
        form = formset.forms[0]
        self.assertEquals(Block.objects.filter(user=self.user).count(), 6)
        block_field = form.fields['block']
        self.assertEquals(set(block_field.queryset), {self.active_block})

    def test_block_queryset_with_other_user_blocks(self):
        """
        Only blocks for this user should appear in the block dropdown
        """
        users = mommy.make_recipe('booking.user', _quantity=5)
        for user in users:
            mommy.make_recipe('booking.block', user=user, paid=True,
                              block_type=self.block_type)
        formset = SimpleBookingRegisterFormSet(data=self.formset_data(),
                                               instance=self.event)
        form = formset.forms[0]
        self.assertEquals(Block.objects.filter(
            block_type=self.block_type
        ).count(), 6)
        block_field = form.fields['block']
        self.assertEquals(set(block_field.queryset), {self.active_block})

    def test_block_queryset_with_inactive_block(self):
        """
        Only active blocks for this user should appear in the block dropdown
        """
        self.active_block.paid = False
        self.active_block.save()

        formset = SimpleBookingRegisterFormSet(data=self.formset_data(),
                                               instance=self.event)
        form = formset.forms[0]
        self.assertEquals(Block.objects.filter(user=self.user).count(), 1)
        block_field = form.fields['block']
        self.assertFalse(block_field.queryset)

    def test_block_queryset_with_expired_block(self):
        """
        Only active blocks for this user should appear in the block dropdown
        """
        self.block_type.duration = 2
        self.block_type.save()
        expired_block = mommy.make_recipe(
            'booking.block', user=self.user, paid=True,
            block_type=self.block_type,
            start_date=timezone.now()-timedelta(365)
        )
        self.assertFalse(expired_block.active_block())

        formset = SimpleBookingRegisterFormSet(data=self.formset_data(),
                                               instance=self.event)
        form = formset.forms[0]
        self.assertEquals(Block.objects.filter(user=self.user).count(), 2)
        block_field = form.fields['block']
        self.assertEquals(set(block_field.queryset), {self.active_block})


class StatusFilterTests(TestCase):

    def test_form_valid(self):
        form = StatusFilter({'status_choice': 'OPEN'})
        self.assertTrue(form.is_valid())


class ConfirmPaymentFormTests(TestCase):

    def test_form_valid(self):
        user = mommy.make_recipe('booking.user')
        event = mommy.make_recipe('booking.future_PC')

        data = {
            'user': user.id,
            'event': event.id,
            'status': 'OPEN',
            'date_booked': timezone.now()

        }
        form = ConfirmPaymentForm(data=data)
        self.assertTrue(form.is_valid())


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

    def test_formset_not_valid(self):
        formset = TimetableSessionFormSet(
            data=self.formset_data({'form-0-cost': 'seven'},),
            queryset=Session.objects.all()
        )
        self.assertIn({'cost': ['Enter a number.']}, formset.errors)
        self.assertFalse(formset.is_valid())

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
            'location': 'Watermelon Studio'
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

    def test_event_type_queryset(self):
        form = SessionAdminForm(
            data=self.form_data())
        ev_type_field = form.fields['event_type']
        self.assertEqual(
            set(EventType.objects.filter(event_type='CL')),
            set(ev_type_field.queryset)
        )
        self.assertEquals(len(ev_type_field.queryset), 2)

        form = SessionAdminForm(
            data=self.form_data())
        ev_type_field = form.fields['event_type']
        self.assertEqual(
            set(EventType.objects.filter(
                id__in=[self.event_type.id, self.event_type_oc.id]
            )),
            set(ev_type_field.queryset)
        )
        self.assertEquals(len(ev_type_field.queryset), 2)

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


class UploadTimetableFormTests(TestCase):

    def setUp(self):
        pass

    def form_data(self, extra_data={}):
        data = {
            'start_date': 'Mon 08 Jun 2015',
            'end_date': 'Mon 15 Jun 2015',
        }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_form_valid(self):
        form = UploadTimetableForm(data=self.form_data())
        self.assertTrue(form.is_valid())

    def test_start_and_end_date_required(self):
        form = UploadTimetableForm(
            data={}
        )
        self.assertFalse(form.is_valid())
        self.assertEquals(len(form.errors), 2)
        self.assertEquals(
            form.errors.get('start_date'), ['This field is required.']
        )
        self.assertEquals(
            form.errors.get('end_date'), ['This field is required.']
        )

    def test_invalid_start_date_format(self):
        form = UploadTimetableForm(
            data=self.form_data({'start_date': 'Monday 08 June 2015'})
        )
        self.assertFalse(form.is_valid())
        self.assertEquals(len(form.errors), 1)
        self.assertIn('Invalid date format', str(form.errors['start_date']))

    def test_invalid_end_date_format(self):
        form = UploadTimetableForm(
            data=self.form_data({'end_date': 'Monday 15 June 2015'})
        )
        self.assertFalse(form.is_valid())
        self.assertEquals(len(form.errors), 1)
        self.assertIn('Invalid date format', str(form.errors['end_date']))

    def test_end_date_before_start_date(self):
        pass

class ChooseUsersFormSetTests(TestCase):

    pass


class EmailUsersFormTests(TestCase):

    pass


class UserBookingFormSetTests(TestCase):

    pass


class UserBlockFormSetTests(TestCase):

    pass