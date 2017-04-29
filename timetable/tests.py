from django.test import TestCase
from django.core import management
from allauth.socialaccount.models import SocialApp
from model_mommy import mommy

from booking.models import EventType
from timetable.models import Session


class ManagementCommandsTests(TestCase):

    def test_setup_fb(self):
        self.assertEquals(SocialApp.objects.all().count(), 0)
        management.call_command('setup_fb')
        self.assertEquals(SocialApp.objects.all().count(), 1)

    def test_create_timetable_sessions(self):
        self.assertEquals(Session.objects.all().count(), 0)
        management.call_command('create_timetable')
        self.assertEquals(Session.objects.all().count(), 18)

    def test_create_timetable_sessions_also_creates_event_types(self):
        self.assertEquals(Session.objects.all().count(), 0)
        self.assertEquals(EventType.objects.all().count(), 0)
        management.call_command('create_timetable')
        self.assertEquals(Session.objects.all().count(), 18)
        self.assertEquals(EventType.objects.all().count(), 5)

    def test_create_sessions_does_not_make_duplicates(self):
        self.assertEquals(Session.objects.all().count(), 0)
        self.assertEquals(EventType.objects.all().count(), 0)
        management.call_command('create_timetable')
        self.assertEquals(Session.objects.all().count(), 18)
        self.assertEquals(EventType.objects.all().count(), 5)
        management.call_command('create_timetable')
        self.assertEquals(Session.objects.all().count(), 18)
        self.assertEquals(EventType.objects.all().count(), 5)

    def test_create_pip_room_hire_sessions(self):
        self.assertEquals(Session.objects.all().count(), 0)
        management.call_command('create_pip_hire_sessions')
        self.assertEquals(Session.objects.all().count(), 8)
        for session in Session.objects.all():
            self.assertEqual(session.name, "Pip Room Hire")
            self.assertEqual(session.event_type.event_type, "RH")

    def test_create_pip_room_hire_sessions_creates_RH_event_type(self):
        self.assertEquals(Session.objects.all().count(), 0)
        self.assertEquals(EventType.objects.all().count(), 0)
        management.call_command('create_pip_hire_sessions')
        self.assertEquals(Session.objects.all().count(), 8)
        self.assertEquals(EventType.objects.all().count(), 1)
        et = EventType.objects.first()
        self.assertEqual(et.event_type, "RH")
        self.assertEqual(et.subtype, 'Studio/room hire')

    def test_create_pip_room_hire_sessions_does_not_create_duplicates(self):
        self.assertEquals(Session.objects.all().count(), 0)
        self.assertEquals(EventType.objects.all().count(), 0)
        management.call_command('create_pip_hire_sessions')
        self.assertEquals(Session.objects.all().count(), 8)
        self.assertEquals(EventType.objects.all().count(), 1)
        management.call_command('create_pip_hire_sessions')
        self.assertEquals(Session.objects.all().count(), 8)
        self.assertEquals(EventType.objects.all().count(), 1)


class ModelTests(TestCase):

    def test_pre_save_without_cost(self):
        session = mommy.make(
            Session, cost=10, advance_payment_required=True,
            payment_open=True, payment_time_allowed=4
        )
        self.assertTrue(session.advance_payment_required)
        self.assertTrue(session.payment_open)
        self.assertEqual(session.payment_time_allowed, 4)

        session.cost = 0
        session.save()
        # pre save signal changes other fields
        self.assertFalse(session.advance_payment_required)
        self.assertFalse(session.payment_open)
        self.assertIsNone(session.payment_time_allowed)

    def test_pre_save_external_instructor(self):
        session = mommy.make(
            Session, external_instructor=True,
        )
        self.assertFalse(session.booking_open)
        self.assertFalse(session.payment_open)
        # we can't make these fields true
        session.booking_open = True
        session.payment_open = True
        session.save()
        self.assertFalse(session.booking_open)
        self.assertFalse(session.payment_open)

    def test_pre_save_payment_time_allowed(self):
        """
        payment_time_allowed automatically makes advance_payment_required true
        """
        session = mommy.make(
            Session, cost=10, advance_payment_required=False,
            payment_time_allowed=None
        )
        self.assertFalse(session.advance_payment_required)

        session.payment_time_allowed = 4
        session.save()
        self.assertTrue(session.advance_payment_required)
