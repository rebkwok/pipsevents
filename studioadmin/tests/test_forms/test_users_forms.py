# -*- coding: utf-8 -*-

from datetime import timedelta
from model_bakery import baker

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from booking.models import Event, BlockType
from common.tests.helpers import PatchRequestMixin
from studioadmin.forms import AddBookingForm, ChooseUsersFormSet, \
    EditBookingForm, EditPastBookingForm, \
    EmailUsersForm, UserFilterForm, UserBookingFormSet, UserBlockFormSet


class ChooseUsersFormSetTests(TestCase):

    def setUp(self):
        self.user = baker.make_recipe('booking.user')

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
        self.assertEqual(
            form.errors['from_address'],
            ['This field is required.']
        )

    def test_missing_message(self):
        form = EmailUsersForm(
            data=self.form_data({'message': ''})
        )
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors['message'],
            ['This field is required.']
        )


class UserFilterFormTests(TestCase):

    def setUp(self):
        events = baker.make_recipe(
            'booking.future_EV',
            _quantity=3
            )
        classes = baker.make_recipe(
            'booking.future_PC',
            _quantity=4)

    def test_events_dropdown(self):
        form = UserFilterForm()
        event_field = form.fields['events']
        event_choices = [
            choice for choice in event_field.widget.choices
            ]
        self.assertEqual(len(event_choices), 3)
        event_ids = [id for (id, name) in event_choices]
        event_type = set([
            event.event_type.event_type
            for event in Event.objects.filter(id__in=event_ids)
            ])
        self.assertEqual(event_type, set(['EV']))

    def test_lessons_dropdown(self):
        form = UserFilterForm()
        lesson_field = form.fields['lessons']
        lesson_choices = [
            choice for choice in lesson_field.widget.choices
            ]
        self.assertEqual(len(lesson_choices), 4)
        lesson_ids = [id for (id, name) in lesson_choices]
        event_type = set([
            event.event_type.event_type
            for event in Event.objects.filter(id__in=lesson_ids)
            ])
        self.assertEqual(event_type, set(['CL']))


class UserBookingFormSetTests(PatchRequestMixin, TestCase):

    def setUp(self):
        super(UserBookingFormSetTests, self).setUp()
        self.event = baker.make_recipe('booking.future_EV')
        self.user = baker.make_recipe('booking.user')
        self.block_type = baker.make_recipe('booking.blocktype',
                                       event_type=self.event.event_type)
        # 5 active blocks for other users
        baker.make_recipe(
                    'booking.block',
                    block_type=self.block_type,
                    paid=True,
                    _quantity=5
                    )
        self.booking = baker.make_recipe(
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
        baker.make_recipe('booking.block',
                                        block_type=self.block_type,
                                        user=self.user,
                                        paid=True)

        formset = UserBookingFormSet(data=self.formset_data(),
                                     instance=self.user,
                                     user=self.user)
        form = formset.forms[0]
        self.assertTrue(form.has_available_block)
        self.assertEqual(form.paid_id, 'paid_0')

    def test_block_queryset_with_new_form(self):
        """
        New form should show all active user blocks
        """
        baker.make_recipe(
            'booking.block', block_type=self.block_type, user=self.user,
            paid=True
        )
        baker.make_recipe( 'booking.block', user=self.user, paid=True)

        formset = UserBookingFormSet(instance=self.user,
                                     user=self.user)
        # get the last form, which will be the new empty one
        form = formset.forms[-1]
        block = form.fields['block']
        # queryset shows only the two active blocks for this user
        self.assertEqual(2, block.queryset.count())

    def test_block_queryset_with_existing_booking_with_active_user_block(self):
        """
        Existing booking should show only user's active blocks for the
        same event type.
        """
        active_user_block = baker.make_recipe('booking.block',
                                        block_type=self.block_type,
                                        user=self.user,
                                        paid=True)
        active_user_block_diff_type = baker.make_recipe('booking.block',
                                         user=self.user,
                                         paid=True)

        formset = UserBookingFormSet(data=self.formset_data(),
                                     instance=self.user,
                                     user=self.user)
        # get the first form
        form = formset.forms[0]
        block = form.fields['block']
        # queryset shows only the active blocks for this user and event type
        self.assertEqual(1, block.queryset.count())

        # empty_label shows the "None"
        self.assertEqual(
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
        self.assertEqual(1, block.queryset.count())

        # empty_label shows the "Remove block" instruction
        self.assertEqual(
            block.empty_label,
            "---REMOVE BLOCK (TO CHANGE BLOCK, REMOVE AND SAVE FIRST)---",
        )

    def test_block_queryset_with_existing_booking_no_active_user_block(self):

        active_user_block_diff_type = baker.make_recipe('booking.block',
                                         user=self.user,
                                         paid=True)
        formset = UserBookingFormSet(data=self.formset_data(),
                                     instance=self.user,
                                     user=self.user)
        # get the first form
        form = formset.forms[0]
        block = form.fields['block']
        # no active blocks for this user and event type
        self.assertEqual(0, block.queryset.count())

    def test_block_choice_label_format(self):
        active_user_block = baker.make_recipe('booking.block',
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
        self.assertEqual(1, block.queryset.count())
        self.assertEqual(
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

        events = baker.make_recipe('booking.future_PC', _quantity=5)
        formset = UserBookingFormSet(instance=self.user,
                                     user=self.user)
        # get the last form, which will be the new empty one
        form = formset.forms[-1]
        event = form.fields['event']
        # queryset shows only the two active blocks for this user
        self.assertEqual(6, Event.objects.count())
        self.assertEqual(5, event.queryset.count())
        self.assertFalse(self.event in event.queryset)

    def test_event_choices_with_existing_booking(self):
        """
        Existing booking should show all events in event choices
        ).
        """
        events = baker.make_recipe('booking.future_PC', _quantity=5)
        formset = UserBookingFormSet(data=self.formset_data(),
                                     instance=self.user,
                                     user=self.user)
        # get the first form
        form = formset.forms[0]
        event = form.fields['event']
        # queryset shows all events (will be hidden in the template)
        self.assertEqual(6, event.queryset.count())

    def test_widgets_disabled(self):
        """
        Cancelled: no_show widget, paid, deposit_paid, free_class disabled
        Block: paid, deposit_paid, free_class disabled
        No-show: no_show widget, paid, deposit_paid, free_class enabled but
            greyed
        No-show with block: no_show widget enabled but greyed, paid,
            deposit_paid, free_class disabled
        """
        events = baker.make_recipe('booking.future_PC', _quantity=4)
        user = baker.make_recipe('booking.user')
        block = baker.make_recipe(
            'booking.block', user=user,
            block_type__event_type=events[1].event_type
        )
        cancelled_booking = baker.make_recipe(
            'booking.booking', user=user, event=events[0], paid=True,
            payment_confirmed=True, status='CANCELLED'
        )
        block_booking = baker.make_recipe(
            'booking.booking', user=user, event=events[1], paid=True,
            payment_confirmed=True, status='OPEN', block=block
        )
        no_show_booking = baker.make_recipe(
            'booking.booking', user=user, event=events[2], paid=True,
            payment_confirmed=True, status='OPEN', no_show=True
        )
        no_show_block_booking = baker.make_recipe(
            'booking.booking', user=user, event=events[3], paid=True,
            payment_confirmed=True, status='OPEN', block=block, no_show=True
        )
        data = {
            'bookings-TOTAL_FORMS': 4,
            'bookings-INITIAL_FORMS': 4,
            'bookings-0-id': cancelled_booking.id,
            'bookings-0-event': cancelled_booking.event.id,
            'bookings-0-status': cancelled_booking.status,
            'bookings-1-id': block_booking.id,
            'bookings-1-event': block_booking.event.id,
            'bookings-1-status': block_booking.status,
            'bookings-2-id': no_show_booking.id,
            'bookings-2-event': no_show_booking.event.id,
            'bookings-2-status': no_show_booking.status,
            'bookings-3-id': no_show_block_booking.id,
            'bookings-3-event': no_show_block_booking.event.id,
            'bookings-3-status': no_show_block_booking.status,
            }

        formset = UserBookingFormSet(
            data=data, instance=user, user=self.user
        )
        cancelled_form = formset.forms[0]
        for field in ['no_show', 'paid', 'deposit_paid', 'free_class']:
            self.assertEqual(
                cancelled_form.fields[field].widget.attrs['class'],
                'regular-checkbox regular-checkbox-disabled'
            )
            self.assertEqual(
                cancelled_form.fields[field].widget.attrs['OnClick'],
                'javascript:return ReadOnlyCheckBox()'
            )

        block_form = formset.forms[1]
        for field in ['paid', 'deposit_paid', 'free_class']:
            self.assertEqual(
                block_form.fields[field].widget.attrs['class'],
                'regular-checkbox regular-checkbox-disabled'
            )
            self.assertEqual(
                block_form.fields[field].widget.attrs['OnClick'],
                'javascript:return ReadOnlyCheckBox()'
            )
        self.assertEqual(
            block_form.fields['no_show'].widget.attrs['class'], 'form-check-input'
        )

        no_show_form = formset.forms[2]
        for field in ['no_show', 'paid', 'deposit_paid', 'free_class']:
            self.assertEqual(
                no_show_form.fields[field].widget.attrs['class'],
                'regular-checkbox regular-checkbox-disabled'
            )
            self.assertIsNone(
                no_show_form.fields[field].widget.attrs.get('OnClick', None)
            )

        no_show_block_form = formset.forms[3]
        for field in ['paid', 'deposit_paid', 'free_class']:
            self.assertEqual(
                no_show_block_form.fields[field].widget.attrs['class'],
                'regular-checkbox regular-checkbox-disabled'
            )
            self.assertEqual(
                no_show_block_form.fields[field].widget.attrs['OnClick'],
                'javascript:return ReadOnlyCheckBox()'
            )
        self.assertEqual(
            block_form.fields['no_show'].widget.attrs['class'], 'form-check-input'
        )
        self.assertIsNone(
                no_show_form.fields['no_show'].widget.attrs.get('OnClick', None)
            )


class UserBlockFormSetTests(PatchRequestMixin, TestCase):

    def setUp(self):
        super(UserBlockFormSetTests, self).setUp()
        event_type = baker.make_recipe('booking.event_type_PC')
        self.user = baker.make_recipe('booking.user')
        self.block_type = baker.make_recipe(
            'booking.blocktype', event_type=event_type)
        self.block = baker.make_recipe(
            'booking.block', block_type=self.block_type, user=self.user,
            paid=True
        )

    def formset_data(self, extra_data={}):

        data = {
            'blocks-TOTAL_FORMS': 1,
            'blocks-INITIAL_FORMS': 1,
            'blocks-0-id': self.block.id,
            'blocks-0-block_type': self.block.block_type.id,
            'blocks-0-start_date': self.block.start_date.strftime('%d %b %Y')
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
        event_type = baker.make_recipe('booking.event_type_OE')
        available_block_type = baker.make_recipe('booking.blocktype',
                                               event_type=event_type)
        formset = UserBlockFormSet(data=self.formset_data(),
                                     instance=self.user,
                                     user=self.user)
        form = formset.forms[0]
        self.assertTrue(form.can_buy_block)
        self.assertEqual(form.paid_id, 'paid_0')

    def test_block_type_queryset_for_new_form(self):
        """
        Block_type choices should not include blocktypes for which the user
        already has an active block
        """
        available_block_type = baker.make_recipe('booking.blocktype',
                                               _quantity=5)
        self.assertEqual(BlockType.objects.all().count(), 6)
        formset = UserBlockFormSet(instance=self.user, user=self.user)
        form = formset.forms[-1]
        block_type_queryset = form.fields['block_type'].queryset
        self.assertEqual(block_type_queryset.count(), 5)
        self.assertFalse(self.block_type in block_type_queryset)

        # blocktypes of unpaid blocks which are otherwise active are also not
        # included in the choices
        self.block.paid = False
        self.block.save()
        formset = UserBlockFormSet(instance=self.user, user=self.user)
        form = formset.forms[-1]
        block_type_queryset = form.fields['block_type'].queryset
        self.assertEqual(block_type_queryset.count(), 5)
        self.assertFalse(self.block_type in block_type_queryset)
        # blocktypes of expired blocks are included in the choices
        self.block_type.duration = 2
        self.block_type.save()
        self.block.paid = True
        self.block.save()
        self.block.start_date = timezone.now() - timedelta(100)
        self.block.save()
        self.assertTrue(self.block.expired)
        formset = UserBlockFormSet(instance=self.user, user=self.user)
        form = formset.forms[-1]
        block_type_queryset = form.fields['block_type'].queryset
        self.assertEqual(block_type_queryset.count(), 6)
        self.assertIn(self.block_type, block_type_queryset)

    def test_delete_checkbox(self):
        """
        Delete checkbox should be active only for unpaid blocks, unused free
        blocks or unused transfer blocks
        """
        unpaid = baker.make_recipe(
            'booking.block', user=self.user, paid=False
        )
        free_block_type = baker.make_recipe('booking.free_blocktype')
        free = baker.make(
            'booking.block', user=self.user, paid=True,
            block_type=free_block_type
        )
        free_used = baker.make_recipe(
            'booking.block', user=self.user, paid=True,
            block_type=free_block_type
        )
        baker.make_recipe('booking.booking', user=self.user, block=free_used)
        transfer = baker.make_recipe(
            'booking.block', user=self.user, paid=True,
            block_type__identifier='transferred'
        )
        transfer_used = baker.make_recipe(
            'booking.block', user=self.user, paid=True,
            block_type__identifier='transferred'
        )
        baker.make_recipe(
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


class EditPastBookingFormTests(PatchRequestMixin, TestCase):

    def setUp(self):
        super(EditPastBookingFormTests, self).setUp()
        self.event = baker.make_recipe('booking.past_event')
        self.cancelled_event = baker.make_recipe(
            'booking.past_event', cancelled=True
        )
        self.user = baker.make_recipe('booking.user')
        self.block_type = baker.make_recipe(
            'booking.blocktype5', event_type=self.event.event_type
        )
        # 5 active blocks for other users
        baker.make_recipe(
                    'booking.block',
                    block_type=self.block_type,
                    paid=True,
                    _quantity=5
                    )
        self.booking = baker.make_recipe(
            'booking.booking', event=self.event, user=self.user
        )
        self.booking_for_cancelled = baker.make_recipe(
            'booking.booking', event=self.cancelled_event, user=self.user,
            status='CANCELLED'
        )

    def test_block_choices(self):
        # block drop down lists all blocks for event type with spaces
        # if booking is already assigned to a block that's full, still list
        # block in options
        # includes expired blocks for past events

        # user block, not expired, not full
        block1 = baker.make_recipe(
            'booking.block', block_type=self.block_type, paid=True,
            user=self.user
        )
        baker.make_recipe(
            'booking.booking', user=self.user, block=block1, _quantity=4
        )
        # user block, not expired, full
        block2 = baker.make_recipe(
            'booking.block', block_type=self.block_type, paid=True,
            user=self.user
        )
        baker.make_recipe(
            'booking.booking', user=self.user, block=block2, _quantity=5
        )
        # user block, expired, not full
        block3 = baker.make_recipe(
            'booking.block', block_type=self.block_type, paid=True,
            user=self.user, start_date=timezone.now() - timedelta(days=90)
        )
        baker.make_recipe(
            'booking.booking', user=self.user, block=block3, _quantity=4
        )
        # user block, expired, full
        block4 = baker.make_recipe(
            'booking.block', block_type=self.block_type, paid=True,
            user=self.user, start_date=timezone.now() - timedelta(days=90)
        )
        baker.make_recipe(
            'booking.booking', user=self.user, block=block4, _quantity=5
        )

        form = EditPastBookingForm(instance=self.booking)
        self.assertCountEqual(
            form.fields['block'].queryset, [block1, block3]
        )

        # Add booking to block 1; block 1 is now full, but is included in
        # queryset
        self.booking.block = block1
        self.booking.save()
        form = EditPastBookingForm(instance=self.booking)
        self.assertCountEqual(
            form.fields['block'].queryset, [block1, block3]
        )

        # A different booking does NOT include full block 1
        booking = baker.make_recipe(
            'booking.booking', user=self.user,
            event__event_type=self.block_type.event_type
        )
        form = EditPastBookingForm(instance=booking)
        self.assertCountEqual(
            form.fields['block'].queryset, [block3]
        )

    def test_disabled_checkboxes(self):
        fields_to_disable = [
            'attended', 'paid', 'deposit_paid', 'free_class', 'no_show'
        ]

        # checkboxes made readonly with JS for cancelled bookings
        form = EditPastBookingForm(instance=self.booking_for_cancelled)
        for field in fields_to_disable:
            assert form.fields[field].disabled

        # checkboxes still usable for no-shows
        self.booking.no_show = True
        self.booking.save()
        form = EditPastBookingForm(instance=self.booking)
        for field in fields_to_disable:
            assert not form.fields[field].disabled

    def test_changing_status_to_cancelled(self):
        # sets paid to False and block to None
        block1 = baker.make_recipe(
            'booking.block', block_type=self.block_type, paid=True,
            user=self.user
        )
        self.booking.block = block1
        self.booking.paid = True
        self.booking.save()

        data = {
            'id': self.booking.id,
            'paid': self.booking.paid,
            'status': 'CANCELLED',
            'block': self.booking.block.id
        }
        form = EditPastBookingForm(instance=self.booking, data=data)
        self.assertTrue(form.is_valid())
        self.assertFalse(form.cleaned_data['paid'])
        self.assertIsNone(form.cleaned_data['block'])

    def test_error_messages_for_cancelled_event(self):
        # can't assign booking for cancelled event to block
        block1 = baker.make_recipe(
            'booking.block', block_type=self.block_type, paid=True,
            user=self.user
        )
        data = {
            'id': self.booking_for_cancelled.id,
            'paid': self.booking_for_cancelled.paid,
            'status': self.booking_for_cancelled.status,
            'block': block1.id
        }
        form = EditPastBookingForm(instance=self.booking_for_cancelled, data=data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {
                'block': [
                    '{} is cancelled. Cannot assign booking to a '
                    'block.'.format(self.cancelled_event)
                ]
             }
        )

        # can't change status to open
        data.update(status='OPEN', block=None)
        form = EditPastBookingForm(instance=self.booking_for_cancelled, data=data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {
                'status': [
                    '{} is cancelled. Cannot reopen booking for cancelled '
                    'event.'.format(self.cancelled_event)
                ]
             }
        )

        # can't change status to free
        data.update(status=self.booking_for_cancelled.status, free_class=True)
        form = EditBookingForm(instance=self.booking_for_cancelled, data=data)
        assert form.is_valid()
        assert not form.cleaned_data["free_class"]
        

        # can't change to paid
        data.update(paid=True, free_class=False)
        form = EditBookingForm(instance=self.booking_for_cancelled, data=data)
        assert form.is_valid()
        assert not form.cleaned_data["paid"]
        
        # can't change to attended
        data.update(paid=False, attended=True)
        form = EditBookingForm(instance=self.booking_for_cancelled, data=data)
        assert form.is_valid()
        assert not form.cleaned_data["attended"]

        # can't change to no-show
        data.update(no_show=True, attended=False)
        form = EditBookingForm(instance=self.booking_for_cancelled, data=data)
        assert form.is_valid()
        assert not form.cleaned_data["no_show"]

    def test_cannot_assign_free_class_to_block(self):
        block1 = baker.make_recipe(
            'booking.block', block_type=self.block_type, paid=True,
            user=self.user
        )
        self.booking.free_class = True
        self.booking.save()

        data = {
            'id': self.booking.id,
            'paid': self.booking.paid,
            'status': self.booking.status,
            'free_class': self.booking.free_class,
            'block': block1.id
        }
        form = EditBookingForm(instance=self.booking, data=data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'free_class': ['Free class cannot be assigned to a block.']}
        )

    def test_cannot_assign_cancelled_class_to_block(self):
        block1 = baker.make_recipe(
            'booking.block', block_type=self.block_type, paid=True,
            user=self.user
        )
        self.booking.status = 'CANCELLED'
        self.booking.save()

        data = {
            'id': self.booking.id,
            'paid': self.booking.paid,
            'status': self.booking.status,
            'block': block1.id
        }
        form = EditBookingForm(instance=self.booking, data=data)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {
                'block': [
                    'Cannot assign cancelled booking to a block. To assign '
                    'to block, please also change booking status to OPEN.'
                ]
            }
        )

    def test_cannot_make_block_booking_unpaid(self):
        block1 = baker.make_recipe(
            'booking.block', block_type=self.block_type, paid=True,
            user=self.user
        )
        self.booking.block = block1
        self.booking.save()

        data = {
            'id': self.booking.id,
            'paid': False,
            'status': self.booking.status,
            'block': self.booking.block.id
        }
        form = EditBookingForm(instance=self.booking, data=data)
        assert form.is_valid()
        # paid field in posted data is ignored
        assert form.cleaned_data["paid"]

    def test_cannot_make_both_attended_and_no_show(self):
        data = {
            'id': self.booking.id,
            'paid': self.booking.paid,
            'status': self.booking.status,
            'attended': True,
            'no_show': True
        }
        form = EditBookingForm(instance=self.booking, data=data)
        self.assertFalse(form.is_valid())
        self.assertCountEqual(
            form.errors,
            {
                'attended': ['Booking cannot be both attended and no-show.'],
                'no_show': ['Booking cannot be both attended and no-show.']
            }
        )


class EditBookingFormTests(PatchRequestMixin, TestCase):

    def setUp(self):
        super(EditBookingFormTests, self).setUp()
        self.event = baker.make_recipe('booking.future_PC')
        self.cancelled_event = baker.make_recipe(
            'booking.future_PC', cancelled=True
        )
        self.user = baker.make_recipe('booking.user')
        self.block_type = baker.make_recipe(
            'booking.blocktype5', event_type=self.event.event_type
        )
        # 5 active blocks for other users
        baker.make_recipe(
                    'booking.block',
                    block_type=self.block_type,
                    paid=True,
                    _quantity=5
                    )
        self.booking = baker.make_recipe(
            'booking.booking', event=self.event, user=self.user
        )
        self.booking_for_cancelled = baker.make_recipe(
            'booking.booking', event=self.cancelled_event, user=self.user,
            status='CANCELLED'
        )

    def test_block_choices(self):
        # EditBookingForm is identical to EditPastBookingForm except for
        # block choice options
        # block drop down lists all blocks for event type with spaces
        # if booking is already assigned to a block that's full, still list
        # block in options
        # excludes expired blocks for past events

        # user block, not expired, not full
        block1 = baker.make_recipe(
            'booking.block', block_type=self.block_type, paid=True,
            user=self.user
        )
        baker.make_recipe(
            'booking.booking', user=self.user, block=block1, _quantity=4
        )
        # user block, not expired, full
        block2 = baker.make_recipe(
            'booking.block', block_type=self.block_type, paid=True,
            user=self.user
        )
        baker.make_recipe(
            'booking.booking', user=self.user, block=block2, _quantity=5
        )
        # user block, expired, not full
        block3 = baker.make_recipe(
            'booking.block', block_type=self.block_type, paid=True,
            user=self.user, start_date=timezone.now() - timedelta(days=90)
        )
        baker.make_recipe(
            'booking.booking', user=self.user, block=block3, _quantity=4
        )
        # user block, expired, full
        block4 = baker.make_recipe(
            'booking.block', block_type=self.block_type, paid=True,
            user=self.user, start_date=timezone.now() - timedelta(days=90)
        )
        baker.make_recipe(
            'booking.booking', user=self.user, block=block4, _quantity=5
        )

        # expired/full blocks are NOT included
        form = EditBookingForm(instance=self.booking)
        self.assertCountEqual(
            form.fields['block'].queryset, [block1]
        )

        # Add booking to block 1; block 1 is now full, but is still included
        # in queryset because it is the block on this booking
        self.booking.block = block1
        self.booking.save()
        form = EditBookingForm(instance=self.booking)
        self.assertCountEqual(
            form.fields['block'].queryset, [block1]
        )

        # A different booking does NOT include full block 1
        booking = baker.make_recipe(
            'booking.booking', user=self.user,
            event__event_type=self.block_type.event_type
        )
        form = EditBookingForm(instance=booking)
        self.assertCountEqual(
            form.fields['block'].queryset, []
        )


class AddBookingFormTests(PatchRequestMixin, TestCase):

    def setUp(self):
        super(AddBookingFormTests, self).setUp()
        self.event = baker.make_recipe('booking.future_EV', cost=10)
        self.poleclass = baker.make_recipe('booking.future_PC', cost=10)
        self.poleclass1 = baker.make_recipe('booking.future_PC', cost=10)
        self.past_event = baker.make_recipe('booking.past_event', cost=10)
        self.cancelled_event = baker.make_recipe(
            'booking.future_PC', cancelled=True, cost=10
        )
        self.user = baker.make_recipe('booking.user')
        self.block_type_pc = baker.make_recipe(
            'booking.blocktype5', event_type=self.poleclass.event_type
        )
        self.block_type_ev = baker.make_recipe(
            'booking.blocktype5', event_type=self.event.event_type
        )
        # 5 active blocks for other users
        baker.make_recipe(
                    'booking.block',
                    block_type=self.block_type_ev,
                    paid=True,
                    _quantity=5
                    )

    def test_event_choices(self):
        # only future, not cancelled events shown
        form = AddBookingForm(user=self.user)
        self.assertCountEqual(
            form.fields['event'].queryset,
            [self.event, self.poleclass, self.poleclass1]
        )

    def test_block_choices(self):
        # block drop down lists all blocks for event type with spaces
        # if booking is already assigned to a block that's full, still list
        # block in options
        # includes expired blocks for past events

        # user block, not expired, not full
        block1 = baker.make_recipe(
            'booking.block', block_type=self.block_type_ev, paid=True,
            user=self.user
        )
        baker.make_recipe(
            'booking.booking', user=self.user, block=block1, _quantity=4
        )
        # user block, not expired, full
        block2 = baker.make_recipe(
            'booking.block', block_type=self.block_type_ev, paid=True,
            user=self.user
        )
        baker.make_recipe(
            'booking.booking', user=self.user, block=block2, _quantity=5
        )
        # user block, expired, not full
        block3 = baker.make_recipe(
            'booking.block', block_type=self.block_type_ev, paid=True,
            user=self.user, start_date=timezone.now() - timedelta(days=90)
        )
        baker.make_recipe(
            'booking.booking', user=self.user, block=block3, _quantity=4
        )
        # user block, expired, full
        block4 = baker.make_recipe(
            'booking.block', block_type=self.block_type_ev, paid=True,
            user=self.user, start_date=timezone.now() - timedelta(days=90)
        )
        baker.make_recipe(
            'booking.booking', user=self.user, block=block4, _quantity=5
        )

        # only shows not full, not expired
        form = AddBookingForm(user=self.user)
        self.assertEqual(
            [block.id for block in form.fields['block'].queryset], [block1.id]
        )

    def test_cannot_assign_free_class_to_block(self):
        block1 = baker.make_recipe(
            'booking.block', block_type=self.block_type_ev, paid=True,
            user=self.user
        )

        data = {
            'user': self.user.id,
            'event': self.event.id,
            'paid': '',
            'status': 'OPEN',
            'free_class': True,
            'block': block1.id
        }
        form = AddBookingForm(data=data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {'free_class': ['"Free class" cannot be assigned to a block.']}
        )

    def test_cannot_assign_cancelled_class_to_block(self):
        block1 = baker.make_recipe(
            'booking.block', block_type=self.block_type_ev, paid=True,
            user=self.user
        )

        data = {
            'user': self.user.id,
            'event': self.event.id,
            'paid': True,
            'status': 'CANCELLED',
            'block': block1.id
        }
        form = AddBookingForm(data=data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {
                '__all__': [
                    'A cancelled booking cannot be assigned to a block.'
                ]
            }
        )

    def test_cannot_make_both_attended_and_no_show(self):
        data = {
            'user': self.user.id,
            'event': self.event.id,
            'paid': True,
            'status': 'OPEN',
            'attended': True,
            'no_show': True
        }
        form = AddBookingForm(data=data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {
                '__all__': ['Booking cannot be both attended and no-show'],
            }
        )

    def test_event_not_block_bookable(self):
        # poleclass1 has no associated blocktype
        # make user blocks for available blocktypes
        baker.make_recipe(
            'booking.block', user=self.user, block_type=self.block_type_ev,
            paid=True,
        )
        block_pc = baker.make_recipe(
            'booking.block', user=self.user, block_type=self.block_type_pc,
            paid=True,
        )

        data = {
            'user': self.user.id,
            'event': self.poleclass1.id,
            'paid': True,
            'status': 'OPEN',
            'block': block_pc.id
        }
        form = AddBookingForm(data=data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {
                'block': ['This class type cannot be block-booked'],
            }
        )

    def test_create_booking_with_wrong_blocktype(self):
        # make user blocks for available blocktypes
        block_ev = baker.make_recipe(
            'booking.block', user=self.user, block_type=self.block_type_ev,
            paid=True,
        )
        baker.make_recipe(
            'booking.block', user=self.user, block_type=self.block_type_pc,
            paid=True,
        )

        data = {
            'user': self.user.id,
            'event': self.poleclass.id,
            'paid': True,
            'status': 'OPEN',
            'block': block_ev.id
        }

        form = AddBookingForm(data=data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors,
            {
                'block': [
                    'This class can only be block-booked with a "{}" '
                    'block type.'.format(
                        self.poleclass.event_type
                    )
                ],
            },
        )
