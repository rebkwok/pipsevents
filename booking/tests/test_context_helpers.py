from model_bakery import baker
from datetime import datetime
from datetime import timezone as dt_timezone

from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.urls import reverse
from django.test import TestCase
from django.utils import timezone

from accounts.models import  DisclaimerContent

from booking.models import Booking
from booking.views import EventDetailView, BlockListView
from common.tests.helpers import _create_session, format_content, \
    TestSetupMixin, make_data_privacy_agreement


class EventDetailContextTests(TestSetupMixin, TestCase):
    """
    Test that context helpers are passing correct contexts
    """

    @classmethod
    def setUpTestData(cls):
        super(EventDetailContextTests, cls).setUpTestData()
        cls.free_event = baker.make_recipe('booking.future_EV')
        cls.past_event = baker.make_recipe('booking.past_event')
        cls.paid_event = baker.make_recipe('booking.future_EV', cost=10)
        cls.online_tutorial = baker.make_recipe('booking.future_OT', cost=10)

        cls.CONTEXT_OPTIONS = {
            'payment_text_no_cost':         "There is no cost associated with "
                                            "this workshop/event.",
            'payment_text_cost_not_open':   "Online payments are not open. ",
            'payment_text_cost_open':       "Online payments are open. ",
            'booking_info_text_not_booked': "",
            'booking_info_text_not_open':   "Bookings are not open for this "
                                            "workshop/event.",
            'booking_info_text_booked':     "You have booked for this workshop/event.",
            'booking_info_text_full':       "This workshop/event is now full.",
            'booking_info_payment_date_past': "The payment due date has "
                                              "passed for this workshop/event.  Please "
                                              "make your payment as soon as "
                                              "possible to secure your place.",
            'booking_info_text_booked_tutorial': "You have purchased this online tutorial.",
        }
        cls.CONTEXT_FLAGS = {
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

        self.assertEqual(resp.context_data['payment_text'],
                          self.CONTEXT_OPTIONS['payment_text_no_cost'])
        self.assertEqual(resp.context_data['booking_info_text'],
                          self.CONTEXT_OPTIONS['booking_info_text_not_booked'])
        self.assertTrue(resp.context_data['bookable'])

        for key in flags_not_expected:
            self.assertFalse(key in resp.context_data.keys(),
                             '{} should not be in context_data'.format(key))

        # make the event full
        self.free_event.max_participants = 3
        self.free_event.save()

        users = baker.make_recipe('booking.user', _quantity=3)
        for user in users:
            baker.make_recipe('booking.booking',
                              user=user,
                              event=self.free_event)
        resp = self._get_response(self.user, self.free_event, 'event')

        flags_not_expected = ['booked', 'past']
        self.assertEqual(resp.context_data['payment_text'],
                          self.CONTEXT_OPTIONS['payment_text_no_cost'])
        self.assertEqual(resp.context_data['booking_info_text'],
                          self.CONTEXT_OPTIONS['booking_info_text_full'])
        for key in flags_not_expected:
            self.assertFalse(key in resp.context_data.keys(),
                             '{} should not be in context_data'.format(key))

        # remove one booking, check if user can now book
        Booking.objects.all()[0].delete()
        self.assertEqual(Booking.objects.all().count(), 2)
        resp = self._get_response(self.user, self.free_event, 'event')
        self.assertEqual(resp.context_data['booking_info_text'],
                          self.CONTEXT_OPTIONS['booking_info_text_not_booked'])
        self.assertTrue(resp.context_data['bookable'])

        # book the user
        baker.make_recipe('booking.booking',
                          user=self.user,
                          event=self.free_event)
        self.assertEqual(Booking.objects.all().count(), 3)
        resp = self._get_response(self.user, self.free_event, 'event')
        self.assertEqual(resp.context_data['booking_info_text'],
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
        self.assertEqual(
            resp.context_data['payment_text'],
            "Online payments are open. {}".format(self.past_event.payment_info)
        )

        resp.render()
        # and check that the payment_text is not there
        self.assertNotIn(resp.context_data['payment_text'], str(resp.content))

    def test_online_tutorial(self):
        """
        Test correct context returned for an online tutorial with associated cost
        """
        self.client.login(username=self.user.username, password="test")
        resp = self.client.get(reverse("booking:tutorial_detail", args=(self.online_tutorial.slug,)))
        flags_not_expected = ['booked', 'past']

        self.assertEqual(resp.context_data['payment_text'],
                         self.CONTEXT_OPTIONS['payment_text_cost_open'])
        self.assertEqual(resp.context_data['booking_info_text'],
                         self.CONTEXT_OPTIONS['booking_info_text_not_booked'])
        for key in flags_not_expected:
            self.assertFalse(key in resp.context_data.keys(),
                             '{} should not be in context_data'.format(key))

        baker.make('booking.booking', user=self.user, paid=True, event=self.online_tutorial)

        resp = self.client.get(reverse("booking:tutorial_detail", args=(self.online_tutorial.slug,)))
        self.assertEqual(
            resp.context_data['booking_info_text'],
            self.CONTEXT_OPTIONS['booking_info_text_booked_tutorial']
        )

    def test_event_with_cost(self):
        """
        Test correct context returned for an event with associated cost
        """
        event = baker.make_recipe(
            'booking.future_WS',
            cost=10,
        )

        #  payments closed
        event.payment_open = False
        event.save()
        resp = self._get_response(self.user, event, 'event')
        flags_not_expected = ['booked', 'past']

        self.assertEqual(resp.context_data['payment_text'],
                          self.CONTEXT_OPTIONS['payment_text_cost_not_open'])
        self.assertEqual(resp.context_data['booking_info_text'],
                          self.CONTEXT_OPTIONS['booking_info_text_not_booked'])
        for key in flags_not_expected:
            self.assertFalse(key in resp.context_data.keys(),
                             '{} should not be in context_data'.format(key))

        # open payments
        event.payment_open = True
        event.save()
        resp = self._get_response(self.user, event, 'event')
        self.assertEqual(
            resp.context_data['payment_text'],
            "Online payments are open. {}".format(self.past_event.payment_info)
        )

    def test_booking_not_open(self):
        event = baker.make_recipe(
            'booking.future_WS',
            booking_open=False,
        )
        resp = self._get_response(self.user, event, 'event')
        self.assertEqual(resp.context_data['booking_info_text'],
                  self.CONTEXT_OPTIONS['booking_info_text_not_open'])
        self.assertFalse(resp.context_data['bookable'])

    @patch('booking.context_helpers.timezone')
    @patch('booking.models.booking_models.timezone')
    def test_event_with_payment_due_date(self, models_mock_tz, helpers_mock_tz):
        """
        Test correct context returned for an event with payment due date
        """
        models_mock_tz.now.return_value = datetime(
            2015, 2, 1, tzinfo=dt_timezone.utc
        )
        helpers_mock_tz.now.return_value = datetime(
            2015, 2, 1, tzinfo=dt_timezone.utc
        )
        event = baker.make_recipe(
            'booking.future_WS',
            cost=10,
            payment_due_date=datetime(2015, 2, 2, tzinfo=dt_timezone.utc)
        )
        resp = self._get_response(self.user, event, 'event')

        self.assertEqual(resp.context_data['booking_info_text'],
                          self.CONTEXT_OPTIONS['booking_info_text_not_booked'])
        self.assertTrue(resp.context_data['bookable'])

    @patch('booking.models.booking_models.timezone')
    def test_event_with_past_payment_due_date_is_still_bookable(self, mock_tz):
        """
        Test correct context returned for an event with payment due date
        """
        mock_tz.now.return_value = datetime(2015, 2, 1, tzinfo=dt_timezone.utc)
        event = baker.make_recipe(
            'booking.future_WS',
            cost=10,
            payment_due_date=datetime(2015, 1, 31, tzinfo=dt_timezone.utc)
        )
        resp = self._get_response(self.user, event, 'event')

        self.assertEqual(resp.context_data['booking_info_text'],
                          self.CONTEXT_OPTIONS['booking_info_payment_date_past'])
        self.assertTrue(resp.context_data['bookable'])

    def test_lesson_and_event_format(self):
        """
        Test correct context returned for lessons and events
        """
        event = baker.make_recipe('booking.future_WS', name='Wshop', cost=10)
        lesson = baker.make_recipe('booking.future_PC', name='Lesson', cost=10)

        resp = self._get_response(self.user, event, 'event')
        assert resp.context_data['ev_type_str'] == 'workshop/event'
        assert resp.context_data['ev_type_for_url'] == 'events'
        assert resp.context_data['ev_type_code'] == 'EV'

        url = reverse('booking:lesson_detail', args=[lesson.slug])
        request = self.factory.get(url)
        request.user = self.user
        view = EventDetailView.as_view()
        resp = view(request, slug=lesson.slug, ev_type='lesson')
        assert resp.context_data['ev_type_str'] == 'class'
        assert resp.context_data['ev_type_for_url'] == 'lessons'
        assert resp.context_data['ev_type_code'] == 'CL'
        
    def test_cancelled_booking(self):
        """
        Test correct context returned for a cancelled booking
        """
        event = baker.make_recipe(
            'booking.future_PC', name='Pole', cost=10, booking_open=True,
        )
        baker.make_recipe(
            'booking.booking', user=self.user, event=event, status='CANCELLED'
        )

        resp = self._get_response(self.user, event, 'lesson')

        self.assertTrue('cancelled' in resp.context_data.keys())
        self.assertEqual(
            resp.context_data['booking_info_text_cancelled'],
            "You have previously booked for this class and your booking has "
            "been cancelled."
        )

    def test_auto_cancelled_booking(self):
        """
        Test correct context returned for an auto_cancelled booking
        """
        event = baker.make_recipe(
            'booking.future_PC', name='Pole', cost=10, booking_open=True,
            contact_email='staff@test.com'
        )
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event, status='CANCELLED',
            auto_cancelled=True
        )

        resp = self._get_response(self.user, event, 'lesson')

        self.assertTrue('auto_cancelled' in resp.context_data.keys())
        self.assertEqual(
            resp.context_data['booking_info_text_cancelled'],
            "To rebook this class please contact staff@test.com directly."
        )

        # if we somehow have a booking that's OPEN but still has auto_cancelled
        # set, it should still show booked event context
        booking.status = 'OPEN'
        booking.save()
        booking.auto_cancelled = True
        booking.save()
        self.assertTrue(booking.auto_cancelled)
        resp = self._get_response(self.user, event, 'lesson')
        self.assertFalse('auto_cancelled' in resp.context_data.keys())
        self.assertFalse('cancelled' in resp.context_data.keys())
        self.assertTrue('booked' in resp.context_data.keys())


    def test_external_instructor_class(self):
        """
        Test correct context returned for a cancelled event
        """
        event = baker.make_recipe(
            'booking.future_PC', name='Pole', cost=10, booking_open=True,
            external_instructor=True,
            event_type__subtype='External instructor class'

        )

        resp = self._get_response(self.user, event, 'lesson')

        self.assertEqual(
            resp.context_data['booking_info_text'],
            "Please contact {} directly to book".format(event.contact_person)
        )

    def test_disclaimer_in_context(self):
        """
        Test correct context returned for user disclaimer
        """
        event = baker.make_recipe(
            'booking.future_PC', name='Pole', cost=10, booking_open=True,
        )
        user_no_disclaimer = baker.make_recipe('booking.user')
        make_data_privacy_agreement(user_no_disclaimer)
        user_online_disclaimer = baker.make_recipe('booking.user')
        make_data_privacy_agreement(user_online_disclaimer)
        baker.make_recipe(
            'booking.online_disclaimer', user=user_online_disclaimer,
            version=DisclaimerContent.current_version()
        )

        resp = self._get_response(user_no_disclaimer, event, 'lesson')
        self.assertFalse(resp.context_data['disclaimer'])
        self.assertIn(
            'Please note that you will need to complete a disclaimer form '
            'before booking',
            format_content(resp.rendered_content)
        )
        self.assertEqual(
            "<strong>Please complete a <a href='{}' "
            "target=_blank>disclaimer form</a> before "
            "booking.</strong>".format(reverse('disclaimer_form')),
            resp.context_data['booking_info_text'],
        )

        resp = self._get_response(user_online_disclaimer, event, 'lesson')
        self.assertTrue(resp.context_data['disclaimer'])
        self.assertNotIn(
            'Please note that you will need to complete a disclaimer form '
            'before booking',
            format_content(resp.rendered_content)
        )

    def test_expired_disclaimer(self):
        """
        Test correct context returned for user disclaimer
        """
        event = baker.make_recipe(
            'booking.future_PC', name='Pole', cost=10, booking_open=True,
        )
        user = baker.make_recipe('booking.user')
        make_data_privacy_agreement(user)
        disclaimer = baker.make_recipe(
           'booking.online_disclaimer', user=user,
            date=datetime(2015, 2, 10, 19, 0, tzinfo=dt_timezone.utc)
        )
        self.assertFalse(disclaimer.is_active)

        resp = self._get_response(user, event, 'lesson')
        self.assertEqual(
            resp.context_data['booking_info_text'],
            "<strong>Please update your <a href='{}' target=_blank>"
            "disclaimer form</a> before booking.</strong>".format(
                reverse('disclaimer_form')
            )
        )


class BlockListContextTests(TestSetupMixin, TestCase):
    """
    Test correct block types returned in BlockListView
    """

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
        baker.make_recipe('booking.blocktype5')
        baker.make_recipe('booking.blocktype10')
        baker.make_recipe('booking.blocktype_other')
        resp = self._get_response(self.user)
        self.assertIn('can_book_block', resp.context_data)
        self.assertEqual(resp.context_data['blockformlist'], [])

    def test_with_booked_block(self):
        """
        Test that user cannot book if they have a block of each available
        type
        """
        # make 3 blocktypes, 2 with the same eventtype
        ev_type = baker.make_recipe('booking.event_type_PC')
        blocktype_pc = baker.make_recipe(
            'booking.blocktype5', event_type=ev_type
        )
        baker.make_recipe('booking.blocktype10', event_type=ev_type)
        blocktype_other = baker.make_recipe('booking.blocktype_other')

        baker.make_recipe(
            'booking.block', user=self.user,
            block_type=blocktype_pc, start_date=timezone.now()
        )
        baker.make_recipe(
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
        blocktype_pc = baker.make_recipe('booking.blocktype5')
        baker.make_recipe('booking.blocktype_other')

        baker.make_recipe(
            'booking.block', user=self.user,
            block_type=blocktype_pc, start_date=timezone.now()
        )
        resp = self._get_response(self.user)
        self.assertIn('can_book_block', resp.context_data)
        self.assertEqual(len(resp.context_data['blockformlist']), 1)
