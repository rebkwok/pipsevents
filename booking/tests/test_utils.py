from django.test import TestCase

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from model_bakery import baker

from booking.models import Event
from booking.utils import create_classes, upload_timetable
from timetable.models import Session


class UtilsTests(TestCase):

    def test_create_classes(self):
        # create classes for a given date (22/3/16 is a Tues)
        date = datetime(2016, 3, 22, tzinfo=dt_timezone.utc)
        self.assertEqual(Event.objects.all().count(), 0)

        # create some timetabled sessions for mondays
        baker.make_recipe('booking.mon_session', _quantity=3)

        create_classes(input_date=date)
        # check that there are now classes on the Monday that week (21st Mar)
        mon_classes = Event.objects.filter(date__gte=date - timedelta(days=1),
                                           date__lte=date)
        self.assertTrue(mon_classes.count(), 3)

    def test_create_classes_with_existing_classes(self):
        # create classes for a given date (22/3/16 is a Tues)
        date = datetime(2016, 3, 22, tzinfo=dt_timezone.utc)
        self.assertEqual(Event.objects.all().count(), 0)

        # create some timetabled sessions for mondays
        baker.make_recipe('booking.mon_session', _quantity=3)

        create_classes(input_date=date)
        # check that there are now classes on the Monday that week (21st Mar)
        mon_classes = Event.objects.filter(date__gte=date - timedelta(days=1),
                                           date__lte=date)
        self.assertTrue(mon_classes.count(), 3)

        baker.make_recipe('booking.mon_session', _quantity=1)
        create_classes(input_date=date)
        # check that there are now classes on the Monday that week (21st Mar)
        mon_classes = Event.objects.filter(date__gte=date - timedelta(days=1),
                                           date__lte=date)
        # check that only one more class is created
        self.assertTrue(mon_classes.count(), 4)

    def test_upload_timetable(self):
        """
        create classes between given dates
        """
        start_date = datetime(2016, 3, 22, tzinfo=dt_timezone.utc) # tues
        end_date = datetime(2016, 3, 23, tzinfo=dt_timezone.utc) # wed
        self.assertEqual(Event.objects.all().count(), 0)

        # create some timetabled sessions for mondays, tuesdays and Wednesdays
        baker.make_recipe('booking.mon_session', _quantity=3)
        baker.make_recipe('booking.tue_session', _quantity=3)
        baker.make_recipe('booking.wed_session', _quantity=3)

        session_ids = [session.id for session in Session.objects.all()]

        upload_timetable(start_date, end_date, session_ids)
        # check that there are now classes on the dates specified
        tue_classes = Event.objects.filter(
            date__gte=self._start_of_day(start_date),
            date__lte=self._end_of_day(start_date)
            )
        wed_classes = Event.objects.filter(
            date__gte=self._start_of_day(end_date),
            date__lte=self._end_of_day(end_date)
            )
        # total number of classes created is 6, as no monday classes created
        self.assertEqual(tue_classes.count(), 3)
        self.assertEqual(wed_classes.count(), 3)
        self.assertEqual(Event.objects.count(), 6)

    def test_upload_timetable_with_existing_classes(self):
        """
        create classes between given dates
        """
        start_date = datetime(2016, 3, 21, tzinfo=dt_timezone.utc) # monday
        end_date = datetime(2016, 3, 22, tzinfo=dt_timezone.utc) # tuesday
        self.assertEqual(Event.objects.all().count(), 0)

        # create some timetabled sessions for mondays, tuesdays and Wednesdays
        baker.make_recipe('booking.mon_session', _quantity=3)
        baker.make_recipe('booking.tue_session', _quantity=3)
        baker.make_recipe('booking.wed_session', _quantity=3)

        session_ids = [session.id for session in Session.objects.all()]

        upload_timetable(start_date, end_date, session_ids)
        # check that there are now classes on the dates specified
        mon_classes = Event.objects.filter(
            date__gte=self._start_of_day(start_date),
            date__lte=self._end_of_day(start_date)
            )
        tue_classes = Event.objects.filter(
            date__gte=self._start_of_day(end_date),
            date__lte=self._end_of_day(end_date)
            )
        self.assertEqual(mon_classes.count(), 3)
        self.assertEqual(tue_classes.count(), 3)

        # upload timetable with overlapping dates
        start_date = datetime(2016, 3, 22, tzinfo=dt_timezone.utc) # tuesday
        end_date = datetime(2016, 3, 23, tzinfo=dt_timezone.utc) # Wednesday
        upload_timetable(start_date, end_date, session_ids)
        tue_classes = Event.objects.filter(
            date__gte=self._start_of_day(start_date),
            date__lte=self._end_of_day(start_date)
            )
        wed_classes = Event.objects.filter(
            date__gte=self._start_of_day(end_date),
            date__lte=self._end_of_day(end_date)
            )
        # tue classes is still 3
        self.assertEqual(tue_classes.count(), 3)
        self.assertEqual(wed_classes.count(), 3)

        # total number of classes created is now 9
        self.assertEqual(Event.objects.all().count(), 9)

    def test_upload_timetable_only_matches_main_fields(self):
        """
        Test that uploading timetable only checks name, event type, date and
        location on existing classes and doesn't create duplicates if the
        same class exists with a minor difference
        """
        start_date = datetime(2016, 3, 21, tzinfo=dt_timezone.utc) # monday
        end_date = datetime(2016, 3, 22, tzinfo=dt_timezone.utc) # tuesday
        self.assertEqual(Event.objects.all().count(), 0)

        # create some timetabled sessions for mondays, tuesdays and Wednesdays
        baker.make_recipe('booking.mon_session', _quantity=3)
        baker.make_recipe('booking.tue_session', _quantity=3)
        baker.make_recipe('booking.wed_session', _quantity=3)

        session_ids = [session.id for session in Session.objects.all()]

        upload_timetable(start_date, end_date, session_ids)
        # check that there are now classes on the dates specified
        mon_classes = Event.objects.filter(
            date__gte=self._start_of_day(start_date),
            date__lte=self._end_of_day(start_date)
            )
        tue_classes = Event.objects.filter(
            date__gte=self._start_of_day(end_date),
            date__lte=self._end_of_day(end_date)
            )
        self.assertEqual(mon_classes.count(), 3)
        self.assertEqual(tue_classes.count(), 3)

        # make some minor changes to one of the newly uploaded classes
        # should NOT cause a new class to be uploaded
        tue_class = tue_classes[0]
        tue_class.description = "A new description"
        tue_class.save()

        # upload timetable with overlapping dates
        start_date = datetime(2016, 3, 22, tzinfo=dt_timezone.utc) # tuesday
        end_date = datetime(2016, 3, 23, tzinfo=dt_timezone.utc) # Wednesday
        upload_timetable(start_date, end_date, session_ids)
        tue_classes = Event.objects.filter(
            date__gte=self._start_of_day(start_date),
            date__lte=self._end_of_day(start_date)
            )
        wed_classes = Event.objects.filter(
            date__gte=self._start_of_day(end_date),
            date__lte=self._end_of_day(end_date)
            )
        # tue classes is still 3
        self.assertEqual(tue_classes.count(), 3)
        self.assertEqual(wed_classes.count(), 3)

        # total number of classes created is now 9
        self.assertEqual(Event.objects.all().count(), 9)

        # make some major changes to one of the newly uploaded classes
        # SHOULD cause a new class to be uploaded
        tue_class = tue_classes[0]
        tue_class.name = "New Pole Class"
        tue_class.save()

        # upload timetable with overlapping dates
        start_date = datetime(2016, 3, 22, tzinfo=dt_timezone.utc) # tuesday
        end_date = datetime(2016, 3, 23, tzinfo=dt_timezone.utc) # Wednesday
        upload_timetable(start_date, end_date, session_ids)
        tue_classes = Event.objects.filter(
            date__gte=self._start_of_day(start_date),
            date__lte=self._end_of_day(start_date)
            )
        wed_classes = Event.objects.filter(
            date__gte=self._start_of_day(end_date),
            date__lte=self._end_of_day(end_date)
            )
        # tue classes is now 4
        self.assertEqual(tue_classes.count(), 4)
        self.assertEqual(wed_classes.count(), 3)

        # total number of classes created is now 10
        self.assertEqual(Event.objects.all().count(), 10)

    def upload_timetable_specified_sessions_only(self):
        start_date = datetime(2016, 3, 22, tzinfo=dt_timezone.utc) # tues
        end_date = datetime(2016, 3, 23, tzinfo=dt_timezone.utc) # wed
        self.assertEqual(Event.objects.all().count(), 0)

        # create some timetabled sessions for mondays, tuesdays and Wednesdays
        tues_sessions = baker.make_recipe('booking.tue_session', _quantity=3)
        baker.make_recipe('booking.wed_session', _quantity=3)

        session_ids = [
            session.id for session in Session.objects.all() if
            session in tues_sessions
            ]
        # choose tues-wed as date range, but specify the tues sessions only
        upload_timetable(start_date, end_date, session_ids)
        # check that there are now classes on the dates specified
        tue_classes = Event.objects.filter(
            date__gte=self._start_of_day(start_date),
            date__lte=self._end_of_day(start_date)
            )
        wed_classes = Event.objects.filter(
            date__gte=self._start_of_day(end_date),
            date__lte=self._end_of_day(end_date)
            )
        # total number of classes created is 3, as no wed classes created
        self.assertEqual(tue_classes.count(), 3)
        self.assertEqual(wed_classes.count(), 0)
        self.assertEqual(Event.objects.count(), 3)

    def _start_of_day(self, date):
        return date.replace(hour=0, minute=0, second=0, microsecond=0)

    def _end_of_day(self, date):
        return date.replace(hour=23, minute=59, second=59, microsecond=99999)
