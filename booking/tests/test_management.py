from django.test import TestCase
from django.core import management
from allauth.socialaccount.models import SocialApp
from django.contrib.auth.models import User
from booking.models import Event, Booking


class ManagementCommandsTests(TestCase):

    def test_setup_fb(self):
        self.assertEquals(SocialApp.objects.all().count(), 0)
        management.call_command('setup_fb')
        self.assertEquals(SocialApp.objects.all().count(), 1)

    def test_load_users(self):
        self.assertEquals(User.objects.all().count(), 0)
        management.call_command('load_users')
        self.assertTrue(User.objects.all().count() >= 5)

    def test_create_events(self):
        self.assertEquals(Event.objects.all().count(), 0)
        management.call_command('create_events')
        self.assertTrue(Event.objects.all().count() >= 5)

    def test_create_classes(self):
        pass
        #TODO mock now, test classes created for this week and next

    def test_create_bookings(self):
        self.assertEquals(Event.objects.all().count(), 0)
        # management.call_command('create_events')
        # TODO add exception to create events to raise warning if there are
        # TODO no users yet. Test exception by running create events wihtou
        # TODO creating users
