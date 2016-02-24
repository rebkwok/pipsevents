# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
from model_mommy import mommy

from django.test import TestCase
from django.utils import timezone

from booking.models import Block
from studioadmin.forms import RegisterDayForm,SimpleBookingRegisterFormSet


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
            'bookings-0-deposit_paid': 'off',
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
        self.assertEquals(form.checkbox_deposit_paid_id, 'checkbox_deposit_paid_0')
        self.assertEquals(form.checkbox_paid_id, 'checkbox_paid_0')
        self.assertEquals(form.checkbox_attended_id, 'checkbox_attended_0')
        self.assertEquals(form.checkbox_no_show_id, 'checkbox_no_show_0')

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

    def test_adding_more_bookings_than_max_participants(self):
        self.event.max_participants = 2
        self.event.save()
        user = mommy.make_recipe('booking.user')
        user1 = mommy.make_recipe('booking.user')
        data = self.formset_data({
            'bookings-TOTAL_FORMS': 3,
            'bookings-1-user': user.id,
            'bookings-2-user': user1.id,
        })
        formset = SimpleBookingRegisterFormSet(data=data, instance=self.event)
        self.assertFalse(formset.is_valid())
        self.assertEqual(
            formset.non_form_errors(),
            [
                'Too many bookings; a maximum of 2 bookings is allowed '
                '(excluding no-shows)'
            ]
        )

        self.event.max_participants = 1
        self.event.save()
        data = self.formset_data({
            'bookings-TOTAL_FORMS': 2,
            'bookings-1-user': user.id
        })
        formset = SimpleBookingRegisterFormSet(data=data, instance=self.event)
        self.assertFalse(formset.is_valid())
        self.assertEqual(
            formset.non_form_errors(),
            [
                'Too many bookings; a maximum of 1 booking is allowed '
                '(excluding no-shows)'
            ]
        )

        self.booking.no_show = True
        self.booking.save()
        data = self.formset_data({
            'bookings-TOTAL_FORMS': 2,
            'bookings-0-no_show': True,
            'bookings-0-attended': False,
            'bookings-1-user': user.id,
        })
        formset = SimpleBookingRegisterFormSet(data=data, instance=self.event)
        self.assertTrue(formset.is_valid())
        self.assertEqual(
            formset.non_form_errors(),
            []
        )


class RegisterDayFormTests(TestCase):

    def test_form_valid(self):
        form = RegisterDayForm({'register_date': 'Mon 07 Sep 2015'})
        self.assertTrue(form.is_valid())

    def test_invalid_date(self):
        form = RegisterDayForm({'register_date': 'Mon 31 Sep 2015'})
        self.assertFalse(form.is_valid())
        self.assertEqual(
            ['Invalid date format.  Select from the date picker or enter '
             'date in the format e.g. Mon 08 Jun 2015'],
            form.errors['register_date']
        )

    def test_events(self):
        events = mommy.make_recipe(
            'booking.future_PC',
            date=datetime(year=2015, month=9, day=7, tzinfo=timezone.utc), _quantity=3)
        form = RegisterDayForm({'register_date': 'Mon 07 Sep 2015'}, events=events)

        eventfield = form.fields['select_events']
        choices_ids = [choice[0] for choice in eventfield.choices]
        events_ids = [event.id for event in events]
        self.assertEqual(events_ids, choices_ids)

    def test_event_choices_only_show_selected_date(self):
        events = mommy.make_recipe(
            'booking.future_PC',
            date=datetime(
                year=2015, month=9, day=7, tzinfo=timezone.utc
            ), _quantity=3
        )
        mommy.make_recipe(
            'booking.future_PC',
            date=datetime(
                year=2015, month=9, day=6, tzinfo=timezone.utc
            ), _quantity=3
        )
        form = RegisterDayForm(
            {'register_date': 'Mon 07 Sep 2015'}, events=events
        )

        eventfield = form.fields['select_events']
        choices_ids = [choice[0] for choice in eventfield.choices]
        events_ids = [event.id for event in events]
        self.assertEqual(events_ids, choices_ids)

    def test_event_choices_initial_data(self):
        events = mommy.make_recipe(
            'booking.future_PC',
            date=datetime(
                year=2015, month=9, day=7, tzinfo=timezone.utc), _quantity=3
        )
        ext_instructor_event = mommy.make_recipe(
            'booking.future_PC',
            external_instructor=True,
            date=datetime(
                year=2015, month=9, day=7, tzinfo=timezone.utc)
        )

        form = RegisterDayForm(
            initial= {
                'register_date': 'Mon 07 Sep 2015',
                'exclude_ext_instructor': True
            },
            events=events+[ext_instructor_event,]
        )

        eventfield = form.fields['select_events']
        choices_ids = [choice[0] for choice in eventfield.choices]
        events_ids = [event.id for event in events] + [ext_instructor_event.id]
        self.assertEqual(events_ids, choices_ids)
        self.assertEqual(eventfield.initial, [event.id for event in events])
