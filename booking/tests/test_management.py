from django.test import TestCase
from django.core import management
from django.db.models import Q
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import datetime, timedelta
from allauth.socialaccount.models import SocialApp
from mock import patch
from model_mommy import mommy

from booking.models import Event, Booking
from booking.utils import create_classes


class ManagementCommandsTests(TestCase):

    def test_setup_fb(self):
        self.assertEquals(SocialApp.objects.all().count(), 0)
        management.call_command('setup_fb')
        self.assertEquals(SocialApp.objects.all().count(), 1)

    def test_load_users(self):
        self.assertEquals(User.objects.all().count(), 0)
        management.call_command('load_users')
        self.assertEquals(User.objects.all().count(), 5)

    def test_create_events(self):
        self.assertEquals(Event.objects.all().count(), 0)
        management.call_command('create_events')
        self.assertEquals(Event.objects.all().count(), 5)

    @patch('booking.utils.date')
    def test_create_classes_with_manage_command(self, mock_date):
        mock_date.today.return_value = datetime(2015, 2, 10)

        self.assertEquals(Event.objects.all().count(), 0)
        management.call_command('create_classes')
        # check that there are now classes on the Monday of the mocked week
        # (mocked now is Wed 10 Feb 2015)
        mon_classes = Event.objects.filter(
            Q(date__gte=datetime(2015, 2, 10, tzinfo=timezone.utc)) &
            Q(date__lte=datetime(2015, 2, 11, tzinfo=timezone.utc))
        )
        self.assertTrue(mon_classes)
        # check that there are now classes on the Monday of the following week
        # (mocked now is Wed 10 Feb 2015)
        next_mon_classes = Event.objects.filter(
            Q(date__gte=datetime(2015, 2, 17, tzinfo=timezone.utc)) &
            Q(date__lte=datetime(2015, 2, 18, tzinfo=timezone.utc))
        )
        self.assertTrue(next_mon_classes)

    def test_create_classes(self):
        # create classes for a given date (22/3/16 is a Tues)
        date = datetime(2016, 3, 22, tzinfo=timezone.utc)
        self.assertEquals(Event.objects.all().count(), 0)
        create_classes(input_date=date)
        # check that there are now classes on the Monday that week
        mon_classes = Event.objects.filter(date__gte=date,
                                           date__lte=date + timedelta(days=1))
        self.assertTrue(mon_classes)

    def test_create_bookings(self):
        """
        test that create_bookings creates 3 bookings per event
        """
        mommy.make_recipe('booking.user', _quantity=3)
        mommy.make_recipe('booking.future_EV', _quantity=2)
        self.assertEquals(Booking.objects.all().count(), 0)
        management.call_command('create_bookings')
        self.assertEquals(Booking.objects.all().count(), 6)

    def test_create_bookings_without_users(self):
        """
        test that create_bookings creates users if none exist
        """
        mommy.make_recipe('booking.future_EV')
        self.assertEquals(Booking.objects.all().count(), 0)
        self.assertEquals(User.objects.all().count(), 0)
        management.call_command('create_bookings')
        self.assertEquals(Booking.objects.all().count(), 3)
        self.assertEquals(User.objects.all().count(), 5)

    def test_create_bookings_without_events(self):
        """
        test that create_bookings handles being called when there are no events
        """
        self.assertEquals(Booking.objects.all().count(), 0)

        management.call_command('create_bookings')
        # confirm no errors, and no booking are created
        self.assertEquals(Booking.objects.all().count(), 0)
