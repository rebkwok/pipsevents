import os

from mock import patch

from model_mommy import mommy
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

from django.core.urlresolvers import reverse
from django.test import TestCase, RequestFactory, override_settings
from django.contrib.auth.models import Permission
from django.utils import timezone

from accounts.models import PrintDisclaimer, OnlineDisclaimer

from booking.models import Event, Booking
from booking.views import EventListView, EventDetailView
from booking.tests.helpers import TestSetupMixin, format_content


class EventListViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(EventListViewTests, cls).setUpTestData()
        mommy.make_recipe('booking.future_EV', _quantity=3)
        mommy.make_recipe('booking.future_PC', _quantity=3)
        mommy.make_recipe('booking.future_CL', _quantity=3)

    def _get_response(self, user, ev_type):
        url = reverse('booking:events')
        request = self.factory.get(url)
        request.user = user
        view = EventListView.as_view()
        return view(request, ev_type=ev_type)

    def test_event_list(self):
        """
        Test that only events are listed (workshops and other events)
        """
        url = reverse('booking:events')
        resp = self.client.get(url)

        self.assertEquals(Event.objects.all().count(), 9)
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context['events'].count(), 3)

    def test_event_list_past_event(self):
        """
        Test that past events is not listed
        """
        mommy.make_recipe('booking.past_event')
        # check there are now 4 events
        self.assertEquals(Event.objects.all().count(), 10)
        url = reverse('booking:events')
        resp = self.client.get(url)

        # event listing should still only show future events
        self.assertEquals(resp.context['events'].count(), 3)

    def test_event_list_with_anonymous_user(self):
        """
        Test that no booked_events in context
        """
        url = reverse('booking:events')
        resp = self.client.get(url)

        # event listing should still only show future events
        self.assertFalse('booked_events' in resp.context)

    def test_event_list_with_logged_in_user(self):
        """
        Test that booked_events in context
        """
        resp = self._get_response(self.user, 'events')
        self.assertTrue('booked_events' in resp.context_data)

    def test_event_list_with_booked_events(self):
        """
        test that booked events are shown on listing
        """
        resp = self._get_response(self.user, 'events')
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(len(resp.context_data['booked_events']), 0)

        # create a booking for this user
        booked_event = Event.objects.all()[0]
        mommy.make_recipe('booking.booking', user=self.user, event=booked_event)
        resp = self._get_response(self.user, 'events')
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(len(booked_events), 1)
        self.assertTrue(booked_event.id in booked_events)

    def test_event_list_shows_only_current_user_bookings(self):
        """
        Test that only user's booked events are shown as booked
        """
        events = Event.objects.all()
        event1 = events[0]
        event2 = events[1]

        resp = self._get_response(self.user, 'events')
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(len(resp.context_data['booked_events']), 0)

        # create booking for this user
        mommy.make_recipe('booking.booking', user=self.user, event=event1)
        # create booking for another user
        user1 = mommy.make_recipe('booking.user')
        mommy.make_recipe('booking.booking', user=user1, event=event2)

        # check only event1 shows in the booked events
        resp = self._get_response(self.user, 'events')
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(Booking.objects.all().count(), 2)
        self.assertEquals(len(booked_events), 1)
        self.assertTrue(event1.id in booked_events)

    def test_filter_events(self):
        """
        Test that we can filter the classes by name
        """
        mommy.make_recipe('booking.future_EV', name='test_name', _quantity=3)
        mommy.make_recipe('booking.future_EV', name='test_name1', _quantity=4)

        url = reverse('booking:events')
        resp = self.client.get(url, {'name': 'test_name'})
        self.assertEquals(resp.context['events'].count(), 3)

    def test_pole_practice_context_without_permission(self):
        Event.objects.all().delete()
        pp_event_type = mommy.make_recipe('booking.event_type_OC', subtype="Pole practice")
        pole_practice = mommy.make_recipe('booking.future_CL', event_type=pp_event_type)

        user = mommy.make_recipe('booking.user')
        mommy.make(PrintDisclaimer, user=user)

        response = self._get_response(user, 'lessons')
        response.render()
        self.assertIn('N/A - see details', str(response.content))
        self.assertNotIn('book_button', str(response.content))
        self.assertNotIn('join_waiting_list_button', str(response.content))
        self.assertNotIn('leave_waiting_list_button', str(response.content))

    def test_pole_practice_context_with_permission(self):
        Event.objects.all().delete()
        pp_event_type = mommy.make_recipe('booking.event_type_OC', subtype="Pole practice")
        pole_practice = mommy.make_recipe('booking.future_CL', event_type=pp_event_type)

        user = mommy.make_recipe('booking.user')
        perm = Permission.objects.get(codename='is_regular_student')
        user.user_permissions.add(perm)
        user.save()
        mommy.make(PrintDisclaimer, user=user)
        
        response = self._get_response(user, 'lessons')
        response.render()
        self.assertIn('book_button', str(response.content))
        self.assertNotIn('join_waiting_list_button', str(response.content))
        self.assertNotIn('leave_waiting_list_button', str(response.content))

    def test_cancelled_events_are_not_listed(self):
        Event.objects.all().delete()
        cancelled_event = mommy.make_recipe('booking.future_CL', cancelled=True)
        response = self._get_response(self.user, 'lessons')
        self.assertEquals(Event.objects.count(), 1)
        self.assertEquals(response.context_data['events'].count(), 0)

    @patch('booking.templatetags.bookingtags.timezone')
    def test_sale_message_template_tag(self, mock_tz):
        mock_tz.now.return_value = datetime(2015, 1, 3, tzinfo=timezone.utc)
        mock_tz.utc = timezone.utc

        os.environ['SALE_ON'] = '01-Jan-2015'
        os.environ['SALE_OFF'] = '15-Jan-2015'
        resp = self.client.get(reverse('booking:events'))

        self.assertIn('JANUARY SALE NOW ON', resp.rendered_content)

    def test_users_disclaimer_status_in_context(self):
        user = mommy.make_recipe('booking.user')

        resp = self._get_response(user, 'events')
        # user has no disclaimer
        self.assertIsNone(resp.context_data.get('disclaimer'))
        self.assertIn(
            'Please note that you will need to complete a disclaimer form '
            'before booking',
            format_content(resp.rendered_content)
        )

        mommy.make_recipe('booking.online_disclaimer', user=user)
        resp = self._get_response(user, 'events')
        self.assertTrue(resp.context_data.get('disclaimer'))
        self.assertNotIn(
            'Please note that you will need to complete a disclaimer form '
            'before booking',
            format_content(resp.rendered_content)
        )

        OnlineDisclaimer.objects.all().delete()
        mommy.make(PrintDisclaimer, user=user)
        resp = self._get_response(user, 'events')
        self.assertTrue(resp.context_data.get('disclaimer'))
        self.assertNotIn(
            'Please note that you will need to complete a disclaimer form '
            'before booking',
            format_content(resp.rendered_content)
        )


class EventDetailViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(EventDetailViewTests, cls).setUpTestData()
        mommy.make_recipe('booking.future_PC', _quantity=3)
        mommy.make_recipe('booking.future_CL', _quantity=3)

    def setUp(self):
        self.event = mommy.make_recipe('booking.future_EV')

    def _get_response(self, user, event, ev_type):
        url = reverse('booking:event_detail', args=[event.slug])
        request = self.factory.get(url)
        request.user = user
        view = EventDetailView.as_view()
        return view(request, slug=event.slug, ev_type=ev_type)

    def test_login_required(self):
        """
        test that page redirects if there is no user logged in
        """
        url = reverse('booking:event_detail', kwargs={'slug': self.event.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

    def test_with_logged_in_user(self):
        """
        test that page loads if there user is available
        """
        resp = self._get_response(self.user, self.event, 'event')
        self.assertEqual(resp.status_code, 200)
        self.assertEquals(resp.context_data['type'], 'event')

    def test_with_booked_event(self):
        """
        Test that booked event is shown as booked
        """
        #create a booking for this event and user
        mommy.make_recipe('booking.booking', user=self.user, event=self.event)
        resp = self._get_response(self.user, self.event, 'event')
        self.assertTrue(resp.context_data['booked'])
        self.assertEquals(resp.context_data['booking_info_text'],
                          'You have booked for this event.')

    def test_with_booked_event_for_different_user(self):
        """
        Test that the event is not shown as booked if the current user has
        not booked it
        """
        user1 = mommy.make_recipe('booking.user')
        #create a booking for this event and a different user
        mommy.make_recipe('booking.booking', user=user1, event=self.event)

        resp = self._get_response(self.user, self.event,'event')
        self.assertFalse('booked' in resp.context_data)
        self.assertEquals(resp.context_data['booking_info_text'], '')

    def test_pole_practice_context_without_permission(self):
        pp_event_type = mommy.make_recipe('booking.event_type_OC', subtype="Pole practice")
        pole_practice = mommy.make_recipe('booking.future_CL', event_type=pp_event_type)

        user = mommy.make_recipe('booking.user')
        mommy.make(PrintDisclaimer, user=user)

        response = self._get_response(user, pole_practice, 'lesson')
        response.render()
        self.assertIn('unbookable_pole_practice', response.context_data)
        self.assertTrue(response.context_data['unbookable_pole_practice'])
        self.assertFalse(response.context_data['bookable'])
        self.assertNotIn('book_button_disabled', str(response.content))
        self.assertNotIn('book_button', str(response.content))
        self.assertNotIn('join_waiting_list_button', str(response.content))
        self.assertNotIn('leave_waiting_list_button', str(response.content))

    def test_pole_practice_context_with_permission(self):
        pp_event_type = mommy.make_recipe('booking.event_type_OC', subtype="Pole practice")
        pole_practice = mommy.make_recipe('booking.future_CL', event_type=pp_event_type)

        user = mommy.make_recipe('booking.user')
        perm = Permission.objects.get(codename='is_regular_student')
        user.user_permissions.add(perm)
        user.save()
        mommy.make(PrintDisclaimer, user=user)

        response = self._get_response(user, pole_practice, 'lesson')
        response.render()
        self.assertNotIn('unbookable_pole_practice', response.context_data)
        self.assertTrue(response.context_data['bookable'])
        self.assertNotIn('book_button_disabled', str(response.content))
        self.assertIn('book_button', str(response.content))
        self.assertNotIn('join_waiting_list_button', str(response.content))
        self.assertNotIn('leave_waiting_list_button', str(response.content))

    def test_payment_due_information_displayed_payment_due_date(self):
        """
        For not cancelled future events, show payment due date/time
        Payment open and payment due date --> show payment due date
        Payment open and time allowed --> show hours allowed
        """
        self.event.cost = 10
        self.event.advance_payment_required = True
        self.event.payment_due_date = timezone.now() + timedelta(15)
        self.event.payment_open = True
        self.event.save()

        self.assertTrue(self.event.allow_booking_cancellation)
        self.assertTrue(self.event.can_cancel())

        resp = self._get_response(self.user, self.event, 'event')
        soup = BeautifulSoup(resp.rendered_content, 'html.parser')
        content = soup.text

        # show text for payment due date, but not any for payment time allowed
        # or cancellation due date
        self.assertIn('Payment is due by', content)
        self.assertNotIn(
            'Once booked, your space will be held for', content
        )
        self.assertNotIn('(payment due ', content)

        self.event.payment_time_allowed = 4
        self.event.save()
        # payment due date overrides payment time allowed; if both are set, use
        # the due date
        resp = self._get_response(self.user, self.event, 'event')
        soup = BeautifulSoup(resp.rendered_content, 'html.parser')
        content = soup.text

        self.assertIn('Payment is due by', content)
        self.assertNotIn(
            'Once booked, your space will be held for', content
        )
        self.assertNotIn('(payment due ', content)

    def test_payment_due_information_displayed_payment_time(self):
        """
        For not cancelled future events, show payment due date/time
        Payment open and payment due date --> show payment due date
        Payment open and time allowed --> show hours allowed
        """
        self.event.cost = 10
        self.event.advance_payment_required = True
        self.event.payment_time_allowed = 6
        self.event.payment_open = True
        self.event.save()

        self.assertTrue(self.event.allow_booking_cancellation)
        self.assertTrue(self.event.can_cancel())

        resp = self._get_response(self.user, self.event, 'event')
        soup = BeautifulSoup(resp.rendered_content, 'html.parser')
        content = soup.text

        # show text for payment time allowed, but not any for payment due date
        # or cancellation due date
        self.assertNotIn('Payment is due by', content)
        self.assertIn(
            'Once booked, your space will be held for 6 hours', content
        )
        self.assertNotIn('(payment due ', content)

    def test_payment_due_information_displayed_cancellation_period(self):
        """
        For not cancelled future events, show payment due date/time
        Payment open and payment due date --> show payment due date
        Payment open and time allowed --> show hours allowed
        """
        self.event.cost = 10
        self.event.payment_open = True
        self.event.advance_payment_required = True
        self.event.save()

        self.assertTrue(self.event.allow_booking_cancellation)
        self.assertTrue(self.event.can_cancel())

        resp = self._get_response(self.user, self.event, 'event')
        soup = BeautifulSoup(resp.rendered_content, 'html.parser')
        content = soup.text

        # show text for cancellation due date, but not any for payment due date
        # or payment time allowed
        self.assertNotIn('Payment is due by', content)
        self.assertNotIn( 'Once booked, your space will be held for', content)
        self.assertIn('(payment due ', content)

    def test_cancellation_information_displayed_cancellation_period(self):
        """
        For not cancelled future events, show cancellation info
        If booking cancellation allowed, show cancellation period if there
        is one
        No payment_due_date or payment_time_allowed --> show due date with
        cancellation period
        If booking cancellation not allowed, show nonrefundable message
        """
        self.event.cost = 10
        self.event.advance_payment_required = True
        self.event.payment_open = True
        self.event.save()

        self.assertTrue(self.event.allow_booking_cancellation)
        self.assertEqual(self.event.cancellation_period, 24)

        resp = self._get_response(self.user, self.event, 'event')
        soup = BeautifulSoup(resp.rendered_content, 'html.parser')
        content = soup.text
        # show cancellation period and due date text
        self.assertIn(
            'Cancellation is allowed up to 24 hours prior to the event',
            content
        )
        self.assertIn('(payment due ', content)

    def test_cancellation_information_displayed_cancellation_not_allowed(self):
        """
        For not cancelled future events, show cancellation info
        If booking cancellation allowed, show cancellation period if there
        is one
        No payment_due_date or payment_time_allowed --> show due date with
        cancellation period
        If booking cancellation not allowed, show nonrefundable message
        """
        self.event.cost = 10
        self.event.advance_payment_required = True
        self.event.payment_open = True
        self.event.allow_booking_cancellation = False
        self.event.save()

        self.assertEqual(self.event.cancellation_period, 24)

        resp = self._get_response(self.user, self.event, 'event')
        soup = BeautifulSoup(resp.rendered_content, 'html.parser')
        content = soup.text
        # don't show cancellation period and due date text
        self.assertNotIn(
            'Cancellation is allowed up to 24 hours prior to the event ',
            content
        )
        self.assertNotIn('(payment due ', content)
        self.assertIn(
            'Bookings are final and non-refundable; if you cancel your booking '
            'you will not be eligible for any refund or credit.', content
        )


class LessonListViewTests(TestSetupMixin, TestCase):
    """
    Test EventListView with lessons; reuses the event templates and context
    data helpers
    """
    @classmethod
    def setUpTestData(cls):
        super(LessonListViewTests, cls).setUpTestData()
        mommy.make_recipe('booking.future_EV', _quantity=1)
        mommy.make_recipe('booking.future_PC', _quantity=3)
        mommy.make_recipe('booking.future_CL', _quantity=3)
        mommy.make_recipe('booking.future_WS', _quantity=1)

    def _get_response(self, user, ev_type):
        url = reverse('booking:lessons')
        request = self.factory.get(url)
        request.user = user
        view = EventListView.as_view()
        return view(request, ev_type=ev_type)

    def test_with_logged_in_user(self):
        """
        test that page loads if there is a user is available
        """
        resp = self._get_response(self.user, 'lessons')
        self.assertEqual(resp.status_code, 200)
        self.assertEquals(resp.context_data['type'], 'lessons')
        self.assertTrue('booked_events' in resp.context_data)

    def test_lesson_list_with_anonymous_user(self):
        """
        Test that no booked_events in context
        """
        url = reverse('booking:lessons')
        resp = self.client.get(url)

        # event listing should still only show future events
        self.assertFalse('booked_events' in resp.context)

    def test_lesson_list(self):
        """
        Test that only classes are listed (pole classes and other classes)
        """
        url = reverse('booking:lessons')
        resp = self.client.get(url)

        self.assertEquals(Event.objects.all().count(), 8)
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context['events'].count(), 6)
        self.assertEquals(resp.context['type'], 'lessons')

    def test_filter_lessons(self):
        """
        Test that we can filter the classes by name
        """
        mommy.make_recipe('booking.future_PC', name='test_name', _quantity=3)
        mommy.make_recipe('booking.future_PC', name='test_name1', _quantity=4)

        url = reverse('booking:lessons')
        resp = self.client.get(url, {'name': 'test_name'})
        self.assertEquals(resp.context['events'].count(), 3)
        resp = self.client.get(url, {'name': 'test_name1'})
        self.assertEquals(resp.context['events'].count(), 4)

    def test_lesson_list_shows_only_current_user_bookings(self):
        """
        Test that only user's booked events are shown as booked
        """
        events = Event.objects.filter(event_type__event_type="CL")
        event1,  event2 = events[0:2]

        resp = self._get_response(self.user, 'lessons')
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(len(resp.context_data['booked_events']), 0)

        # create booking for this user
        mommy.make_recipe('booking.booking', user=self.user, event=event1)
        # create booking for another user
        user1 = mommy.make_recipe('booking.user')
        mommy.make_recipe('booking.booking', user=user1, event=event2)

        # check only event1 shows in the booked events
        resp = self._get_response(self.user, 'lessons')
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(Booking.objects.all().count(), 2)
        self.assertEquals(len(booked_events), 1)
        self.assertTrue(event1.id in booked_events)

    def test_lesson_list_only_shows_open_bookings(self):
        events = Event.objects.filter(event_type__event_type="CL")
        event1,  event2 = events[0:2]

        resp = self._get_response(self.user, 'lessons')
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(len(resp.context_data['booked_events']), 0)

        # create open and cancelled booking for this user
        mommy.make_recipe('booking.booking', user=self.user, event=event1)
        mommy.make_recipe(
            'booking.booking', user=self.user, event=event2, status='CANCELLED'
        )

        # check only event1 shows in the booked events
        resp = self._get_response(self.user, 'lessons')
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(Booking.objects.all().count(), 2)
        self.assertEquals(len(booked_events), 1)
        self.assertTrue(event1.id in booked_events)


class RoomHireListViewTests(TestSetupMixin, TestCase):
    """
    Test EventListView with room hires; reuses the event templates and context
    data helpers
    """
    @classmethod
    def setUpTestData(cls):
        super(RoomHireListViewTests, cls).setUpTestData()
        mommy.make_recipe('booking.future_RH', _quantity=4)
        mommy.make_recipe('booking.future_EV', _quantity=1)
        mommy.make_recipe('booking.future_PC', _quantity=3)
        mommy.make_recipe('booking.future_CL', _quantity=3)
        mommy.make_recipe('booking.future_WS', _quantity=1)

    def _get_response(self, user, ev_type):
        url = reverse('booking:room_hires')
        request = self.factory.get(url)
        request.user = user
        view = EventListView.as_view()
        return view(request, ev_type=ev_type)

    def test_with_logged_in_user(self):
        """
        test that page loads if there is a user is available
        """
        resp = self._get_response(self.user, 'room_hires')
        self.assertEqual(resp.status_code, 200)
        self.assertEquals(resp.context_data['type'], 'room_hires')
        self.assertTrue('booked_events' in resp.context_data)

    def test_lesson_list_with_anonymous_user(self):
        """
        Test that no booked_events in context
        """
        url = reverse('booking:room_hires')
        resp = self.client.get(url)

        # event listing should still only show future events
        self.assertFalse('booked_events' in resp.context)

    def test_lesson_list(self):
        """
        Test that only room hires are listed
        """
        url = reverse('booking:room_hires')
        resp = self.client.get(url)

        self.assertEquals(Event.objects.all().count(), 12)
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context['events'].count(), 4)
        self.assertEquals(resp.context['type'], 'room_hire')

    def test_filter_lessons(self):
        """
        Test that we can filter the room hires by name
        """
        mommy.make_recipe('booking.future_RH', name='test_name', _quantity=3)
        mommy.make_recipe('booking.future_RH', name='test_name1', _quantity=4)

        url = reverse('booking:room_hires')
        resp = self.client.get(url, {'name': 'test_name'})
        self.assertEquals(resp.context['events'].count(), 3)
        resp = self.client.get(url, {'name': 'test_name1'})
        self.assertEquals(resp.context['events'].count(), 4)

    def test_lesson_list_shows_only_current_user_bookings(self):
        """
        Test that only user's booked room hires are shown as booked
        """
        events = Event.objects.filter(event_type__event_type="RH")
        event1,  event2 = events[0:2]

        resp = self._get_response(self.user, 'room_hires')
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(len(resp.context_data['booked_events']), 0)

        # create booking for this user
        mommy.make_recipe('booking.booking', user=self.user, event=event1)
        # create booking for another user
        user1 = mommy.make_recipe('booking.user')
        mommy.make_recipe('booking.booking', user=user1, event=event2)

        # check only event1 shows in the booked events
        resp = self._get_response(self.user, 'room_hires')
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(Booking.objects.all().count(), 2)
        self.assertEquals(len(booked_events), 1)
        self.assertTrue(event1.id in booked_events)

    def test_lesson_list_only_shows_open_bookings(self):
        events = Event.objects.filter(event_type__event_type="RH")
        event1,  event2 = events[0:2]

        resp = self._get_response(self.user, 'room_hires')
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(len(resp.context_data['booked_events']), 0)

        # create open and cancelled booking for this user
        mommy.make_recipe('booking.booking', user=self.user, event=event1)
        mommy.make_recipe(
            'booking.booking', user=self.user, event=event2, status='CANCELLED'
        )

        # check only event1 shows in the booked events
        resp = self._get_response(self.user, 'room_hires')
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(Booking.objects.all().count(), 2)
        self.assertEquals(len(booked_events), 1)
        self.assertTrue(event1.id in booked_events)


class LessonDetailViewTests(TestSetupMixin, TestCase):
    """
    Test EventDetailView with lessons; reuses the event templates and
    context data helpers
    """
    @classmethod
    def setUpTestData(cls):
        super(LessonDetailViewTests, cls).setUpTestData()
        cls.lesson = mommy.make_recipe('booking.future_PC')
        mommy.make_recipe('booking.future_EV', _quantity=3)
        mommy.make_recipe('booking.future_PC', _quantity=3)

    def test_with_logged_in_user(self):
        """
        test that page loads if there user is available
        """
        url = reverse('booking:lesson_detail', args=[self.lesson.slug])
        request = self.factory.get(url)
        # Set the user on the request
        request.user = self.user
        view = EventDetailView.as_view()
        resp = view(request, slug=self.lesson.slug, ev_type='lesson')

        self.assertEqual(resp.status_code, 200)
        self.assertEquals(resp.context_data['type'], 'lesson')


class RoomHireDetailViewTests(TestSetupMixin, TestCase):
    """
    Test EventDetailView with room hires; reuses the event templates and
    context data helpers
    """
    @classmethod
    def setUpTestData(cls):
        super(RoomHireDetailViewTests, cls).setUpTestData()
        cls.room_hire = mommy.make_recipe('booking.future_RH')
        mommy.make_recipe('booking.future_EV', _quantity=3)
        mommy.make_recipe('booking.future_PC', _quantity=3)
        mommy.make_recipe('booking.future_RH', _quantity=3)

    def test_with_logged_in_user(self):
        """
        test that page loads if there user is available
        """
        url = reverse('booking:room_hire_detail', args=[self.room_hire.slug])
        request = self.factory.get(url)
        # Set the user on the request
        request.user = self.user
        view = EventDetailView.as_view()
        resp = view(request, slug=self.room_hire.slug, ev_type='room_hire')

        self.assertEqual(resp.status_code, 200)
        self.assertEquals(resp.context_data['type'], 'room_hire')
