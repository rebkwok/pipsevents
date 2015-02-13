from django.core.urlresolvers import reverse
from django.contrib.sites.models import Site
from django.test import TestCase, RequestFactory
from model_mommy import mommy
from booking.models import Event, Booking, Block
from booking.views import EventDetailView

class EventDetailContextTests(TestCase):
    """
    Test that context helpers are passing correct contexts
    """

    def setUp(self):
        self.factory = RequestFactory()
        fbapp = mommy.make_recipe('booking.fb_app')
        site = Site.objects.get_current()
        fbapp.sites.add(site.id)

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
            'booking_info_text_booked':     "You have booked for this event.",
            'booking_info_text_full':       "This event is now full.",
        }
        self.CONTEXT_FLAGS = {
            'include_book_button': True,
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
        self.assertEquals(resp.context_data['include_book_button'],
                          self.CONTEXT_FLAGS['include_book_button'])
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

        flags_not_expected = ['booked', 'past', 'include_book_button']
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
        self.assertTrue('include_book_button' in resp.context_data.keys())

        # book the user
        mommy.make_recipe('booking.booking',
                          user=self.user,
                          event=self.free_event)
        self.assertEquals(Booking.objects.all().count(), 3)
        resp = self._get_response(self.user, self.free_event)
        self.assertEquals(resp.context_data['booking_info_text'],
                          self.CONTEXT_OPTIONS['booking_info_text_booked'])
        self.assertFalse('include_book_button' in resp.context_data.keys())

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


