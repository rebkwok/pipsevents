# -*- coding: utf-8 -*-

from datetime import datetime
from datetime import timezone as dt_timezone

from model_bakery import baker

from django.test import TestCase

from studioadmin.forms import RegisterDayForm


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
        events = baker.make_recipe(
            'booking.future_PC',
            date=datetime(year=2015, month=9, day=7, tzinfo=dt_timezone.utc), _quantity=3)
        form = RegisterDayForm({'register_date': 'Mon 07 Sep 2015'}, events=events)

        eventfield = form.fields['select_events']
        choices_ids = [choice[0] for choice in eventfield.choices]
        events_ids = [event.id for event in events]
        self.assertEqual(events_ids, choices_ids)

    def test_event_choices_only_show_selected_date(self):
        events = baker.make_recipe(
            'booking.future_PC',
            date=datetime(
                year=2015, month=9, day=7, tzinfo=dt_timezone.utc
            ), _quantity=3
        )
        baker.make_recipe(
            'booking.future_PC',
            date=datetime(
                year=2015, month=9, day=6, tzinfo=dt_timezone.utc
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
        events = baker.make_recipe(
            'booking.future_PC',
            date=datetime(
                year=2015, month=9, day=7, tzinfo=dt_timezone.utc), _quantity=3
        )
        ext_instructor_event = baker.make_recipe(
            'booking.future_PC',
            external_instructor=True,
            date=datetime(
                year=2015, month=9, day=7, tzinfo=dt_timezone.utc)
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
