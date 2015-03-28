from django.core.urlresolvers import reverse
from django.test import TestCase, RequestFactory
from django.utils import timezone
from model_mommy import mommy
from datetime import datetime
from mock import patch
from booking.models import Event, Booking, Block
from booking.views import EventDetailView, BookingDetailView, LessonDetailView
from booking.tests.helpers import set_up_fb


class EventDetailContextTests(TestCase):
    """
    Test that context helpers are passing correct contexts
    """

    def setUp(self):
        set_up_fb()
        self.factory = RequestFactory()
        self.free_event = mommy.make_recipe('booking.future_EV')
        self.past_event = mommy.make_recipe('booking.past_event')
        self.paid_event = mommy.make_recipe('booking.future_EV', cost=10)

        self.user = mommy.make_recipe('booking.user')

        self.CONTEXT_OPTIONS = {
            'payment_text_no_cost':         "There is no cost associated with "
                                            "this event.",
            'payment_text_cost_not_open':   "Payments are not yet open. Payment "
                                            "information will be provided closer "
                                            "to the event date.",
            'payment_text_cost_open':       "###replace with "
                                            "event.payment_info###",
            'booking_info_text_not_booked': "",
            'booking_info_text_not_open':   "Bookings are not yet open for this "
                                            "event.",
            'booking_info_text_booked':     "You have booked for this event.",
            'booking_info_text_full':       "This event is now full.",
            'booking_info_payment_date_past': "Bookings for this event are now "
                                              "closed."
        }
        self.CONTEXT_FLAGS = {
            'booked': True,
            'past': True
        }

    def _get_response(self, user, event):
        url = reverse('booking:event_detail', args=[event.slug])
        request = self.factory.get(url)
        request.user = user
        view = EventDetailView.as_view()
        return view(request, slug=event.slug)

    def test_free_event(self):
        """
        Test correct context returned for a free event
        """
        # user not booked, event not full
        resp = self._get_response(self.user, self.free_event)

        flags_not_expected = ['booked', 'past']

        self.assertEquals(resp.context_data['payment_text'],
                          self.CONTEXT_OPTIONS['payment_text_no_cost'])
        self.assertEquals(resp.context_data['booking_info_text'],
                          self.CONTEXT_OPTIONS['booking_info_text_not_booked'])
        self.assertTrue(resp.context_data['bookable'])

        for key in flags_not_expected:
            self.assertFalse(key in resp.context_data.keys(),
                             '{} should not be in context_data'.format(key))

        # make the event full
        self.free_event.max_participants = 3
        self.free_event.save()

        users = mommy.make_recipe('booking.user', _quantity=3)
        for user in users:
            mommy.make_recipe('booking.booking',
                              user=user,
                              event=self.free_event)
        resp = self._get_response(self.user, self.free_event)

        flags_not_expected = ['booked', 'past']
        self.assertEquals(resp.context_data['payment_text'],
                          self.CONTEXT_OPTIONS['payment_text_no_cost'])
        self.assertEquals(resp.context_data['booking_info_text'],
                          self.CONTEXT_OPTIONS['booking_info_text_full'])
        for key in flags_not_expected:
            self.assertFalse(key in resp.context_data.keys(),
                             '{} should not be in context_data'.format(key))

        # remove one booking, check if user can now book
        Booking.objects.all()[0].delete()
        self.assertEquals(Booking.objects.all().count(), 2)
        resp = self._get_response(self.user, self.free_event)
        self.assertEquals(resp.context_data['booking_info_text'],
                          self.CONTEXT_OPTIONS['booking_info_text_not_booked'])
        self.assertTrue(resp.context_data['bookable'])

        # book the user
        mommy.make_recipe('booking.booking',
                          user=self.user,
                          event=self.free_event)
        self.assertEquals(Booking.objects.all().count(), 3)
        resp = self._get_response(self.user, self.free_event)
        self.assertEquals(resp.context_data['booking_info_text'],
                          self.CONTEXT_OPTIONS['booking_info_text_booked'])
        self.assertFalse(resp.context_data['bookable'])

    def test_past_event(self):
        """
        Test correct context returned for a past event
        """
        resp = self._get_response(self.user, self.past_event)

        # user is not booked; include book button, payment text etc is still in
        # context; template handles the display
        self.assertFalse('booked' in resp.context_data.keys())
        self.assertTrue('past' in resp.context_data.keys())
        self.assertEquals(resp.context_data['payment_text'],
                          self.CONTEXT_OPTIONS['payment_text_cost_not_open'])
        resp.render()
        # check the content for the past text
        self.assertIn("This event is now past.", str(resp.content))
        # and check that the payment_text is not there
        self.assertNotIn(resp.context_data['payment_text'], str(resp.content))

    def test_event_with_cost(self):
        """
        Test correct context returned for an event with associated cost
        """
        event = mommy.make_recipe(
            'booking.future_WS',
            cost=10,
        )

        #  payments not open yet (default)
        resp = self._get_response(self.user, event)
        flags_not_expected = ['booked', 'past']

        self.assertEquals(resp.context_data['payment_text'],
                          self.CONTEXT_OPTIONS['payment_text_cost_not_open'])
        self.assertEquals(resp.context_data['booking_info_text'],
                          self.CONTEXT_OPTIONS['booking_info_text_not_booked'])
        for key in flags_not_expected:
            self.assertFalse(key in resp.context_data.keys(),
                             '{} should not be in context_data'.format(key))

        # open payments
        event.payment_open = True
        event.save()
        resp = self._get_response(self.user, event)
        self.assertEquals(resp.context_data['payment_text'],
                          event.payment_info)

    def test_booking_not_open(self):
        event = mommy.make_recipe(
            'booking.future_WS',
            booking_open=False,
        )
        resp = self._get_response(self.user, event)
        self.assertEquals(resp.context_data['booking_info_text'],
                  self.CONTEXT_OPTIONS['booking_info_text_not_open'])
        self.assertFalse(resp.context_data['bookable'])

    @patch('booking.models.timezone')
    def test_event_with_payment_due_date(self, mock_tz):
        """
        Test correct context returned for an event with payment due date
        """
        mock_tz.now.return_value = datetime(2015, 2, 1, tzinfo=timezone.utc)
        event = mommy.make_recipe(
            'booking.future_WS',
            cost=10,
            payment_due_date=datetime(2015, 2, 2, tzinfo=timezone.utc)
        )
        resp = self._get_response(self.user, event)

        self.assertEquals(resp.context_data['booking_info_text'],
                          self.CONTEXT_OPTIONS['booking_info_text_not_booked'])
        self.assertTrue(resp.context_data['bookable'])

    @patch('booking.models.timezone')
    def test_event_with_past_payment_due_date(self, mock_tz):
        """
        Test correct context returned for an event with payment due date
        """
        mock_tz.now.return_value = datetime(2015, 2, 1, tzinfo=timezone.utc)
        event = mommy.make_recipe(
            'booking.future_WS',
            cost=10,
            payment_due_date=datetime(2015, 1, 31, tzinfo=timezone.utc)
        )
        resp = self._get_response(self.user, event)

        self.assertEquals(resp.context_data['booking_info_text'],
                          self.CONTEXT_OPTIONS['booking_info_payment_date_past'])
        self.assertFalse(resp.context_data['bookable'])

    def test_lesson_and_event_format(self):
        """
        Test correct context returned for lessons and events
        """
        event = mommy.make_recipe('booking.future_WS', cost=10)
        lesson = mommy.make_recipe('booking.future_PC', cost=10)

        resp = self._get_response(self.user, event)
        self.assertEquals(resp.context_data['type'], 'event')

        url = reverse('booking:lesson_detail', args=[lesson.slug])
        request = self.factory.get(url)
        request.user = self.user
        view = LessonDetailView.as_view()
        resp = view(request, slug=lesson.slug)
        self.assertEquals(resp.context_data['type'], 'lesson')

class BookingDetailContextTests(TestCase):
    """
    Test that context helpers are passing correct contexts
    """

    def setUp(self):
        set_up_fb()
        self.factory = RequestFactory()
        self.user = mommy.make_recipe('booking.user')

        self.CONTEXT_OPTIONS = {
            'payment_text_no_cost':         "There is no cost associated with "
                                            "this event.",
            'payment_text_cost_not_open':   "Payments are not yet open. Payment "
                                            "information will be provided closer "
                                            "to the event date.",
            'payment_text_cost_open':       "###replace with "
                                            "event.payment_info###",
        }
        self.CONTEXT_FLAGS = {
            'include_confirm_payment_button': True,
            'past': True
        }


    def _get_response(self, user, booking):
        url = reverse('booking:booking_detail', args=[booking.id])
        request = self.factory.get(url)
        request.user = user
        view = BookingDetailView.as_view()
        return view(request, pk=booking.id)

    def test_free_event(self):
        """
        Test correct context returned for a booking for a free event
        """
        free_event = mommy.make_recipe('booking.future_EV')
        booking = mommy.make_recipe(
            'booking.booking', event=free_event, user=self.user
        )

        resp = self._get_response(self.user, booking)
        flags_not_expected = ['past', 'include_confirm_payment_button']
        self.assertEquals(resp.context_data['payment_text'],
                          self.CONTEXT_OPTIONS['payment_text_no_cost'])
        for key in flags_not_expected:
            self.assertFalse(key in resp.context_data.keys(),
                             '{} should not be in context_data'.format(key))

    def test_past_event(self):
        """
        Test correct context returned for a booking for a past event
        """
        past_event = mommy.make_recipe('booking.past_event')
        booking = mommy.make_recipe(
            'booking.booking', event=past_event, user=self.user
        )
        resp = self._get_response(self.user, booking)

        # user is not booked; include confirm payment button, payment text etc is still in
        # context; template handles the display
        self.assertTrue('past' in resp.context_data.keys())
        self.assertEquals(resp.context_data['payment_text'],
                          self.CONTEXT_OPTIONS['payment_text_cost_not_open'])

    def test_event_with_cost(self):
        """
        Test correct context returned for a booking with associated cost
        """
        event = mommy.make_recipe('booking.future_WS', cost=10)
        booking = mommy.make_recipe(
            'booking.booking', event=event, user=self.user
        )
        #  payments not open yet (default)
        resp = self._get_response(self.user, booking)
        flags_not_expected = ['booked', 'include_confirm_payment_button']
        self.assertEquals(resp.context_data['payment_text'],
                          self.CONTEXT_OPTIONS['payment_text_cost_not_open'])
        for key in flags_not_expected:
            self.assertFalse(key in resp.context_data.keys(),
                             '{} should not be in context_data'.format(key))

        # open payments
        event.payment_open = True
        event.save()
        resp = self._get_response(self.user, booking)
        self.assertEquals(resp.context_data['payment_text'],
            "Payments are open. {}".format(event.payment_info))

    def test_lesson_and_event_format(self):
        """
        Test correct context returned for lessons and events
        """
        event = mommy.make_recipe('booking.future_WS', cost=10)
        lesson = mommy.make_recipe('booking.future_PC', cost=10)

        event_booking = mommy.make_recipe(
            'booking.booking', event=event, user=self.user
        )
        lesson_booking = mommy.make_recipe(
            'booking.booking', event=lesson, user=self.user
        )
        resp = self._get_response(self.user, event_booking)
        self.assertEquals(resp.context_data['type'], 'event')
        resp = self._get_response(self.user, lesson_booking)
        self.assertEquals(resp.context_data['type'], 'lesson')