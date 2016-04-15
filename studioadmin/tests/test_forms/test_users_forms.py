# -*- coding: utf-8 -*-

from datetime import timedelta
from model_mommy import mommy

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from booking.models import Event, BlockType
from studioadmin.forms import ChooseUsersFormSet, EmailUsersForm, \
    UserFilterForm, UserBookingFormSet, UserBlockFormSet


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

        # empty_label shows the "None"
        self.assertEquals(
            block.empty_label,
            "--------None--------",
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

        # empty_label shows the "Remove block" instruction
        self.assertEquals(
            block.empty_label,
            "---REMOVE BLOCK (TO CHANGE BLOCK, REMOVE AND SAVE FIRST)---",
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
                    "{}; exp {}; {} left".format(
                        active_user_block.block_type.event_type.subtype,
                        active_user_block.expiry_date.strftime('%d/%m'),
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
        self.block = mommy.make_recipe(
            'booking.block', block_type=self.block_type, user=self.user,
            paid=True
        )

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

    def test_delete_checkbox(self):
        """
        Delete checkbox should be active only for unpaid blocks, unused free
        blocks or unused transfer blocks
        """
        unpaid = mommy.make_recipe(
            'booking.block', user=self.user, paid=False
        )
        free_block_type = mommy.make_recipe('booking.free_blocktype')
        free = mommy.make(
            'booking.block', user=self.user, paid=True,
            block_type=free_block_type
        )
        free_used = mommy.make_recipe(
            'booking.block', user=self.user, paid=True,
            block_type=free_block_type
        )
        mommy.make_recipe('booking.booking', user=self.user, block=free_used)
        transfer = mommy.make_recipe(
            'booking.block', user=self.user, paid=True,
            block_type__identifier='transferred'
        )
        transfer_used = mommy.make_recipe(
            'booking.block', user=self.user, paid=True,
            block_type__identifier='transferred'
        )
        mommy.make_recipe(
            'booking.booking', user=self.user, block=transfer_used
        )

        cannot_delete = [self.block, free_used, transfer_used]
        formset = UserBlockFormSet(instance=self.user, user=self.user)

        self.assertEqual(len(formset.forms), 7)  # 6 blocks plus new form

        for form in formset.forms[:-1]:
            disabled = form.fields['DELETE'].widget.attrs.get('disabled', None)
            if form.instance in cannot_delete:
                self.assertEqual(disabled, 'disabled')
            else:
                self.assertIsNone(disabled)
