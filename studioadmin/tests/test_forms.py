from datetime import datetime, timedelta
from mock import patch
from model_mommy import mommy

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from booking.models import Event, EventType, Block, BlockType
from studioadmin.forms import (
    BlockStatusFilter,
    ChooseUsersFormSet,
    ConfirmPaymentForm,
    DAY_CHOICES,
    EmailUsersForm,
    EventFormSet,
    EventAdminForm,
    SimpleBookingRegisterFormSet,
    StatusFilter,
    TimetableSessionFormSet,
    SessionAdminForm,
    UploadTimetableForm,
    UserFilterForm,
    UserBookingFormSet,
    UserBlockFormSet
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
            'form-0-max-participants': '10',
            'form-0-booking_open': 'on',
            'form-0-payment_open': 'on',
            'form-0-advance_payment_required': 'on',
            }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_event_formset_valid(self):
        formset = EventFormSet(data=self.formset_data())
        self.assertTrue(formset.is_valid())

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
                {'date': '15 Jun 2015 20:00',
                 'payment_due_date': '10 Jun 2015'},
            ), ev_type='CL')
        self.assertTrue(form.is_valid())

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
        form = ConfirmPaymentForm(data={'paid': 'true'})
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

    def form_data(self, extra_data={}):
        data = {
            'start_date': 'Mon 08 Jun 2015',
            'end_date': 'Mon 15 Jun 2015',
        }

        for key, value in extra_data.items():
            data[key] = value

        return data

    @patch('studioadmin.forms.timezone')
    def test_form_valid(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 6, 6, 12, 0, tzinfo=timezone.utc
            )
        form = UploadTimetableForm(data=self.form_data())
        self.assertTrue(form.is_valid())

    @patch('studioadmin.forms.timezone')
    def test_start_and_end_date_required(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 6, 6, 12, 0, tzinfo=timezone.utc
            )
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

    @patch('studioadmin.forms.timezone')
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

    @patch('studioadmin.forms.timezone')
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

    @patch('studioadmin.forms.timezone')
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

    @patch('studioadmin.forms.timezone')
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


class ChooseUsersFormSetTests(TestCase):

    def setUp(self):
        self.user = mommy.make_recipe('booking.user')

    def formset_data(self, extra_data={}):

        data = {
            'form-TOTAL_FORMS': 1,
            'form-INITIAL_FORMS': 1,
            'form-0-id': str(self.user.id),
            }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_choose_users_formset_valid(self):
        formset = ChooseUsersFormSet(data=self.formset_data())
        self.assertTrue(formset.is_valid())


class EmailUsersFormTests(TestCase):

    def setUp(self):
        pass

    def form_data(self, extra_data={}):
        data = {
            'subject': 'Test subject',
            'from_address': settings.DEFAULT_FROM_EMAIL,
            'message': 'Test message'
        }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_form_valid(self):
        form = EmailUsersForm(data=self.form_data())
        self.assertTrue(form.is_valid())

    def test_missing_from_address(self):
        form = EmailUsersForm(
            data=self.form_data({'from_address': ''})
        )
        self.assertFalse(form.is_valid())
        self.assertEquals(
            form.errors['from_address'],
            ['This field is required.']
        )

    def test_missing_message(self):
        form = EmailUsersForm(
            data=self.form_data({'message': ''})
        )
        self.assertFalse(form.is_valid())
        self.assertEquals(
            form.errors['message'],
            ['This field is required.']
        )


class UserFilterFormTests(TestCase):

    def setUp(self):
        events = mommy.make_recipe(
            'booking.future_EV',
            _quantity=3
            )
        classes = mommy.make_recipe(
            'booking.future_PC',
            _quantity=4)

    def test_events_dropdown(self):
        form = UserFilterForm()
        event_field = form.fields['events']
        event_choices = [
            choice for choice in event_field.widget.choices
            ]
        # number of choices is one more than number of events, to account
        # for the placeholder for None Selected
        self.assertEquals(len(event_choices), 4)
        # first id will be ('', '---None selected---')
        event_ids = [id for (id, name) in event_choices][1:]
        event_type = set([
            event.event_type.event_type
            for event in Event.objects.filter(id__in=event_ids)
            ])
        self.assertEquals(event_type, set(['EV']))

    def test_lessons_dropdown(self):
        form = UserFilterForm()
        lesson_field = form.fields['lessons']
        lesson_choices = [
            choice for choice in lesson_field.widget.choices
            ]
        # number of choices is one more than number of events, to account
        # for the placeholder for None Selected
        self.assertEquals(len(lesson_choices), 5)
        # first id will be ('', '---None selected---')
        lesson_ids = [id for (id, name) in lesson_choices][1:]
        event_type = set([
            event.event_type.event_type
            for event in Event.objects.filter(id__in=lesson_ids)
            ])
        self.assertEquals(event_type, set(['CL']))


class UserBookingFormSetTests(TestCase):

    def setUp(self):
        self.event = mommy.make_recipe('booking.future_EV')
        self.user = mommy.make_recipe('booking.user')
        self.block_type = mommy.make_recipe('booking.blocktype',
                                       event_type=self.event.event_type)
        # 5 active blocks for other users
        mommy.make_recipe(
                    'booking.block',
                    block_type=self.block_type,
                    paid=True,
                    _quantity=5
                    )
        self.booking = mommy.make_recipe(
            'booking.booking', event=self.event, user=self.user
        )

    def formset_data(self, extra_data={}):

        data = {
            'bookings-TOTAL_FORMS': 1,
            'bookings-INITIAL_FORMS': 1,
            'bookings-0-id': self.booking.id,
            'bookings-0-event': self.event.id,
            'bookings-0-status': self.booking.status,
            }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_form_valid(self):
        formset = UserBookingFormSet(data=self.formset_data(),
                                     instance=self.user,
                                     user=self.user)
        self.assertTrue(formset.is_valid(), formset.errors)

    def test_additional_data_in_form(self):
        active_user_block = mommy.make_recipe('booking.block',
                                        block_type=self.block_type,
                                        user=self.user,
                                        paid=True)

        formset = UserBookingFormSet(data=self.formset_data(),
                                     instance=self.user,
                                     user=self.user)
        form = formset.forms[0]
        self.assertTrue(form.has_available_block)
        self.assertEquals(form.paid_id, 'paid_0')

    def test_block_queryset_with_new_form(self):
        """
        New form should show all active user blocks
        """
        active_user_block = mommy.make_recipe('booking.block',
                                        block_type=self.block_type,
                                        user=self.user,
                                        paid=True)
        active_user_block_diff_type = mommy.make_recipe('booking.block',
                                         user=self.user,
                                         paid=True)

        formset = UserBookingFormSet(instance=self.user,
                                     user=self.user)
        # get the last form, which will be the new empty one
        form = formset.forms[-1]
        block = form.fields['block']
        # queryset shows only the two active blocks for this user
        self.assertEquals(2, block.queryset.count())

    def test_block_queryset_with_existing_booking_with_active_user_block(self):
        """
        Existing booking should show only user's active blocks for the
        same event type.
        """
        active_user_block = mommy.make_recipe('booking.block',
                                        block_type=self.block_type,
                                        user=self.user,
                                        paid=True)
        active_user_block_diff_type = mommy.make_recipe('booking.block',
                                         user=self.user,
                                         paid=True)

        formset = UserBookingFormSet(data=self.formset_data(),
                                     instance=self.user,
                                     user=self.user)
        # get the first form
        form = formset.forms[0]
        block = form.fields['block']
        # queryset shows only the active blocks for this user and event type
        self.assertEquals(1, block.queryset.count())

        # empty_label shows the "choose block" instruction
        self.assertEquals(
            block.empty_label,
            "---Choose from user's available active blocks---",
             block.empty_label
             )

        # assign this block to the user's booking
        self.booking.block = active_user_block
        self.booking.save()

        formset = UserBookingFormSet(data=self.formset_data(),
                                     instance=self.user,
                                     user=self.user)
        # get the first form
        form = formset.forms[0]
        block = form.fields['block']
        # queryset still only shows active blocks for this user and event type
        self.assertEquals(1, block.queryset.count())

        # empty_label shows the "Unselect block" instruction
        self.assertEquals(
            block.empty_label,
            "---Unselect block (change booking to unpaid)---",
            block.empty_label
        )

    def test_block_queryset_with_existing_booking_no_active_user_block(self):

        active_user_block_diff_type = mommy.make_recipe('booking.block',
                                         user=self.user,
                                         paid=True)
        formset = UserBookingFormSet(data=self.formset_data(),
                                     instance=self.user,
                                     user=self.user)
        # get the first form
        form = formset.forms[0]
        block = form.fields['block']
        # no active blocks for this user and event type
        self.assertEquals(0, block.queryset.count())

    def test_block_choice_label_format(self):
        active_user_block = mommy.make_recipe('booking.block',
                                        block_type=self.block_type,
                                        user=self.user,
                                        paid=True)

        formset = UserBookingFormSet(data=self.formset_data(),
                                     instance=self.user,
                                     user=self.user)
        # get the first form
        form = formset.forms[0]
        block = form.fields['block']
        # queryset shows only the active blocks for this user and event type
        self.assertEquals(1, block.queryset.count())
        self.assertEquals(
                    "Block type: {}; {} left".format(
                        active_user_block.block_type.event_type,
                        active_user_block.block_type.size - active_user_block.bookings_made()),
                    block.label_from_instance(active_user_block)
                    )

    def test_event_choices_with_new_form(self):
        """
        New form should show all events the user is not booked for
        """

        events = mommy.make_recipe('booking.future_PC', _quantity=5)
        formset = UserBookingFormSet(instance=self.user,
                                     user=self.user)
        # get the last form, which will be the new empty one
        form = formset.forms[-1]
        event = form.fields['event']
        # queryset shows only the two active blocks for this user
        self.assertEquals(6, Event.objects.count())
        self.assertEquals(5, event.queryset.count())
        self.assertFalse(self.event in event.queryset)

    def test_event_choices_with_existing_booking(self):
        """
        Existing booking should show all events in event choices
        ).
        """
        events = mommy.make_recipe('booking.future_PC', _quantity=5)
        formset = UserBookingFormSet(data=self.formset_data(),
                                     instance=self.user,
                                     user=self.user)
        # get the first form
        form = formset.forms[0]
        event = form.fields['event']
        # queryset shows all events (will be hidden in the template)
        self.assertEquals(6, event.queryset.count())


class UserBlockFormSetTests(TestCase):

    def setUp(self):
        event_type = mommy.make_recipe('booking.event_type_PC')
        self.user = mommy.make_recipe('booking.user')
        self.block_type = mommy.make_recipe(
            'booking.blocktype', event_type=event_type)
        self.block = mommy.make_recipe('booking.block', block_type=self.block_type, user=self.user, paid=True)

    def formset_data(self, extra_data={}):

        data = {
            'blocks-TOTAL_FORMS': 1,
            'blocks-INITIAL_FORMS': 1,
            'blocks-0-id': self.block.id,
            'blocks-0-block_type': self.block.block_type.id,
            'blocks-0-start_date': self.block.start_date
            }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_form_valid(self):
        formset = UserBlockFormSet(data=self.formset_data(),
                                     instance=self.user,
                                     user=self.user)
        self.assertTrue(formset.is_valid(), formset.errors)

    def test_additional_data_in_form(self):
        event_type = mommy.make_recipe('booking.event_type_OE')
        available_block_type = mommy.make_recipe('booking.blocktype',
                                               event_type=event_type)
        formset = UserBlockFormSet(data=self.formset_data(),
                                     instance=self.user,
                                     user=self.user)
        form = formset.forms[0]
        self.assertTrue(form.can_buy_block)
        self.assertEquals(form.paid_id, 'paid_0')

    def test_block_type_queryset_for_new_form(self):
        """
        Block_type choices should not include blocktypes for which the user
        already has an active block
        """
        available_block_type = mommy.make_recipe('booking.blocktype',
                                               _quantity=5)
        self.assertEquals(BlockType.objects.all().count(), 6)
        formset = UserBlockFormSet(instance=self.user, user=self.user)
        form = formset.forms[-1]
        block_type_queryset = form.fields['block_type'].queryset
        self.assertEquals(block_type_queryset.count(), 5)
        self.assertFalse(self.block_type in block_type_queryset)

        # blocktypes of unpaid blocks which are otherwise active are also not
        # included in the choices
        self.block.paid = False
        self.block.save()
        formset = UserBlockFormSet(instance=self.user, user=self.user)
        form = formset.forms[-1]
        block_type_queryset = form.fields['block_type'].queryset
        self.assertEquals(block_type_queryset.count(), 5)
        self.assertFalse(self.block_type in block_type_queryset)
        # blocktypes of expired blocks are included in the choices
        self.block.start_date = timezone.now() - timedelta(100)
        self.block_type.duration = 2
        self.block_type.save()
        self.block.save()
        self.assertTrue(self.block.expired)
        formset = UserBlockFormSet(instance=self.user, user=self.user)
        form = formset.forms[-1]
        block_type_queryset = form.fields['block_type'].queryset
        self.assertEquals(block_type_queryset.count(), 6)
        self.assertIn(self.block_type, block_type_queryset)
