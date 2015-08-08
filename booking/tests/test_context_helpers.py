from django.core.urlresolvers import reverse
from django.test import TestCase, RequestFactory
from django.utils import timezone
from django.contrib.messages.storage.fallback import FallbackStorage
from model_mommy import mommy
from datetime import datetime
from mock import patch
from booking.models import Event, Booking, Block
from booking.views import EventDetailView, BlockListView
from booking.tests.helpers import set_up_fb, _create_session


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
            'payment_text_cost_not_open':   "Online payments are not open. ",
            'payment_text_cost_open':       "Online payments are open. ",
            'booking_info_text_not_booked': "",
            'booking_info_text_not_open':   "Bookings are not open for this "
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

    def _get_response(self, user, event, ev_type):
        url = reverse('booking:event_detail', args=[event.slug])
        request = self.factory.get(url)
        request.user = user
        view = EventDetailView.as_view()
        return view(request, slug=event.slug, ev_type=ev_type)

    def test_free_event(self):
        """
        Test correct context returned for a free event
        """
        # user not booked, event not full
        resp = self._get_response(self.user, self.free_event, 'event')

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
        resp = self._get_response(self.user, self.free_event, 'event')

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
        resp = self._get_response(self.user, self.free_event, 'event')
        self.assertEquals(resp.context_data['booking_info_text'],
                          self.CONTEXT_OPTIONS['booking_info_text_not_booked'])
        self.assertTrue(resp.context_data['bookable'])

        # book the user
        mommy.make_recipe('booking.booking',
                          user=self.user,
                          event=self.free_event)
        self.assertEquals(Booking.objects.all().count(), 3)
        resp = self._get_response(self.user, self.free_event, 'event')
        self.assertEquals(resp.context_data['booking_info_text'],
                          self.CONTEXT_OPTIONS['booking_info_text_booked'])
        self.assertFalse(resp.context_data['bookable'])

    def test_past_event(self):
        """
        Test correct context returned for a past event
        """
        resp = self._get_response(self.user, self.past_event, 'event')
        self.past_event.save()
        # user is not booked; include book button, payment text etc is still in
        # context; template handles the display
        self.assertFalse('booked' in resp.context_data.keys())
        self.assertTrue('past' in resp.context_data.keys())
        self.assertEquals(
            resp.context_data['payment_text'],
            "Online payments are open. {}".format(self.past_event.payment_info)
        )

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

        #  payments closed
        event.payment_open = False
        event.save()
        resp = self._get_response(self.user, event, 'event')
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
        resp = self._get_response(self.user, event, 'event')
        self.assertEquals(
            resp.context_data['payment_text'],
            "Online payments are open. {}".format(self.past_event.payment_info)
        )

    def test_booking_not_open(self):
        event = mommy.make_recipe(
            'booking.future_WS',
            booking_open=False,
        )
        resp = self._get_response(self.user, event, 'event')
        self.assertEquals(resp.context_data['booking_info_text'],
                  self.CONTEXT_OPTIONS['booking_info_text_not_open'])
        self.assertFalse(resp.context_data['bookable'])

    @patch('booking.context_helpers.timezone')
    @patch('booking.models.timezone')
    def test_event_with_payment_due_date(self, models_mock_tz, helpers_mock_tz):
        """
        Test correct context returned for an event with payment due date
        """
        models_mock_tz.now.return_value = datetime(
            2015, 2, 1, tzinfo=timezone.utc
        )
        helpers_mock_tz.now.return_value = datetime(
            2015, 2, 1, tzinfo=timezone.utc
        )
        event = mommy.make_recipe(
            'booking.future_WS',
            cost=10,
            payment_due_date=datetime(2015, 2, 2, tzinfo=timezone.utc)
        )
        resp = self._get_response(self.user, event, 'event')

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
        resp = self._get_response(self.user, event, 'event')

        self.assertEquals(resp.context_data['booking_info_text'],
                          self.CONTEXT_OPTIONS['booking_info_payment_date_past'])
        self.assertFalse(resp.context_data['bookable'])

    def test_lesson_and_event_format(self):
        """
        Test correct context returned for lessons and events
        """
        event = mommy.make_recipe('booking.future_WS', name='Wshop', cost=10)
        lesson = mommy.make_recipe('booking.future_PC', name='Lesson', cost=10)

        resp = self._get_response(self.user, event, 'event')
        self.assertEquals(resp.context_data['type'], 'event')

        url = reverse('booking:lesson_detail', args=[lesson.slug])
        request = self.factory.get(url)
        request.user = self.user
        view = EventDetailView.as_view()
        resp = view(request, slug=lesson.slug, ev_type='lesson')
        self.assertEquals(resp.context_data['type'], 'lesson')


class BlockListContextTests(TestCase):
    """
    Test correct block types returned in BlockListView
    """
    def setUp(self):
        set_up_fb()
        self.factory = RequestFactory()
        self.user = mommy.make_recipe('booking.user')

    def _set_session(self, user, request):
        request.session = _create_session()
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

    def _get_response(self, user):
        url = reverse('booking:block_list')
        request = self.factory.get(url)
        self._set_session(user, request)
        view = BlockListView.as_view()
        return view(request)

    def test_with_no_blocktypes(self):
        """
        Test blocklist with no blocktypes does not allow block bookings and
        does not show any blocks in the listing
        """
        resp = self._get_response(self.user)
        self.assertEqual(resp.status_code, 200)

        self.assertNotIn('can_book_block', resp.context_data)
        self.assertEqual(resp.context_data['blockformlist'], [])

    def test_with_blocktypes(self):
        """
        Test with blocktypes but no booked blocks
        """
        mommy.make_recipe('booking.blocktype5')
        mommy.make_recipe('booking.blocktype10')
        mommy.make_recipe('booking.blocktype_other')
        resp = self._get_response(self.user)
        self.assertIn('can_book_block', resp.context_data)
        self.assertEqual(resp.context_data['blockformlist'], [])

    def test_with_booked_block(self):
        """
        Test that user cannot book if they have a block of each available
        type
        """
        # make 3 blocktypes, 2 with the same eventtype
        ev_type = mommy.make_recipe('booking.event_type_PC')
        blocktype_pc = mommy.make_recipe(
            'booking.blocktype5', event_type=ev_type
        )
        mommy.make_recipe('booking.blocktype10', event_type=ev_type)
        blocktype_other = mommy.make_recipe('booking.blocktype_other')

        mommy.make_recipe(
            'booking.block', user=self.user,
            block_type=blocktype_pc, start_date=timezone.now()
        )
        mommy.make_recipe(
            'booking.block', user=self.user,
            block_type=blocktype_other, start_date=timezone.now()
        )
        resp = self._get_response(self.user)
        self.assertNotIn('can_book_block', resp.context_data)
        self.assertEqual(len(resp.context_data['blockformlist']), 2)

    def test_with_available_block(self):
        """
        Test that user can book if there is a blocktype available
        """
        blocktype_pc = mommy.make_recipe('booking.blocktype5')
        mommy.make_recipe('booking.blocktype_other')

        mommy.make_recipe(
            'booking.block', user=self.user,
            block_type=blocktype_pc, start_date=timezone.now()
        )
        resp = self._get_response(self.user)
        self.assertIn('can_book_block', resp.context_data)
        self.assertEqual(len(resp.context_data['blockformlist']), 1)
