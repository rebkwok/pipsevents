from datetime import datetime, timedelta
from model_mommy import mommy
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from django.core import management
from django.core.urlresolvers import reverse
from django.http.response import Http404
from django.test import TestCase, RequestFactory
from django.utils import timezone

from booking.models import TicketedEvent, TicketBooking, Ticket
from booking.views import TicketedEventListView, TicketCreateView, \
    TicketBookingListView, TicketBookingHistoryListView, TicketBookingView, \
    TicketBookingCancelView
from booking.tests.helpers import _create_session, format_content, \
    TestSetupMixin


class EventListViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(EventListViewTests, cls).setUpTestData()
        mommy.make_recipe('booking.ticketed_event_max10', _quantity=3)

    def setUp(self):
        super(EventListViewTests, self).setUp()
        self.staff_user = mommy.make_recipe('booking.user')
        self.staff_user.is_staff = True
        self.staff_user.save()

    def _get_response(self, user):
        url = reverse('booking:ticketed_events')
        request = self.factory.get(url)
        request.user = user
        view = TicketedEventListView.as_view()
        return view(request)

    def test_ticketed_event_list(self):
        """
        Test that only ticketed_events are listed
        """
        url = reverse('booking:ticketed_events')
        resp = self.client.get(url)

        self.assertEquals(TicketedEvent.objects.all().count(), 3)
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context['ticketed_events'].count(), 3)

    def test_event_list_past_event(self):
        """
        Test that past event is not listed
        """
        mommy.make_recipe('booking.ticketed_event_past_max10')
        # check there are now 4 events
        self.assertEquals(TicketedEvent.objects.all().count(), 4)
        url = reverse('booking:ticketed_events')
        resp = self.client.get(url)

        # event listing should still only show future events
        self.assertEquals(resp.context['ticketed_events'].count(), 3)

    def test_event_list_with_anonymous_user(self):
        """
        Test that no booked_events in context
        """
        url = reverse('booking:ticketed_events')
        resp = self.client.get(url)

        self.assertFalse('tickets_booked_events' in resp.context)

    def test_event_list_with_logged_in_user(self):
        """
        Test that booked_events in context
        """
        resp = self._get_response(self.user)
        self.assertTrue('tickets_booked_events' in resp.context_data)

    def test_event_list_with_ticket_booking_without_tickets(self):
        """
        test that booked events are shown on listing
        """
        resp = self._get_response(self.user)
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['tickets_booked_events']]
        self.assertEquals(len(resp.context_data['tickets_booked_events']), 0)

        # create a booking for this user with no tickets
        booked_event = TicketedEvent.objects.all()[0]
        mommy.make(
            TicketBooking, user=self.user,
            ticketed_event=booked_event
        )
        resp = self._get_response(self.user)
        booked_events = [event for event in resp.context_data['tickets_booked_events']]
        # ticket bookings without attached tickets are ignored
        self.assertEquals(len(booked_events), 0)

    def test_event_list_with_booked_events(self):
        """
        test that booked events are shown on listing
        """
        resp = self._get_response(self.user)
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['tickets_booked_events']]
        self.assertEquals(len(resp.context_data['tickets_booked_events']), 0)

        # create a booking for this user
        booked_event = TicketedEvent.objects.all()[0]
        mommy.make(
            Ticket, ticket_booking__user=self.user,
            ticket_booking__ticketed_event=booked_event,
            ticket_booking__purchase_confirmed=True
        )
        resp = self._get_response(self.user)
        booked_events = [event for event in resp.context_data['tickets_booked_events']]
        self.assertEquals(len(booked_events), 1)
        self.assertTrue(booked_event in booked_events)

    def test_event_list_only_shows_confirmed_bookings_events(self):
        """
        test that only confirmed bookings are shown on listing
        """
        resp = self._get_response(self.user)
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['tickets_booked_events']]
        self.assertEquals(len(resp.context_data['tickets_booked_events']), 0)

        # create a confirmed booking for this user
        booked_event = TicketedEvent.objects.all()[0]
        mommy.make(
            Ticket, ticket_booking__user=self.user,
            ticket_booking__ticketed_event=booked_event,
            ticket_booking__purchase_confirmed=True
        )
        # create an unconfirmed booking for this user
        unconfirmed = mommy.make(
            Ticket, ticket_booking__user=self.user,
            ticket_booking__ticketed_event=booked_event,
        )
        resp = self._get_response(self.user)
        booked_events = [event for event in resp.context_data['tickets_booked_events']]
        self.assertEquals(len(booked_events), 1)
        self.assertTrue(booked_event in booked_events)
        self.assertFalse(unconfirmed in booked_events)

    def test_event_list_shows_only_current_user_bookings(self):
        """
        Test that only user's booked events are shown as booked
        """
        events = TicketedEvent.objects.all()
        event1 = events[0]
        event2 = events[1]

        resp = self._get_response(self.user)
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['tickets_booked_events']]
        self.assertEquals(len(resp.context_data['tickets_booked_events']), 0)

        # create booking for this user
        mommy.make(
            Ticket, ticket_booking__user=self.user,
            ticket_booking__ticketed_event=event1,
            ticket_booking__purchase_confirmed=True
        )
        # create booking for another user
        user1 = mommy.make_recipe('booking.user')
        mommy.make(
            Ticket, ticket_booking__user=user1,
            ticket_booking__ticketed_event=event2,
            ticket_booking__purchase_confirmed=True
        )

        # check only event1 shows in the booked events
        resp = self._get_response(self.user)
        booked_events = [event for event in resp.context_data['tickets_booked_events']]
        self.assertEquals(TicketBooking.objects.all().count(), 2)
        self.assertEquals(len(booked_events), 1)
        self.assertTrue(event1 in booked_events)

    def test_events_not_listed_if_show_on_site_false(self):
        mommy.make_recipe(
            'booking.ticketed_event_max10', show_on_site=False
        )
        # check there are now 4 events
        self.assertEquals(TicketedEvent.objects.all().count(), 4)
        resp = self._get_response(self.user)
        # event listing should only show events ticked as show on site
        self.assertEquals(resp.context_data['ticketed_events'].count(), 3)

    def test_events_are_listed_for_staff_users_if_show_on_site_false(self):
        mommy.make_recipe(
            'booking.ticketed_event_max10', show_on_site=False
        )
        # check there are now 4 events
        self.assertEquals(TicketedEvent.objects.all().count(), 4)

        resp = self._get_response(self.user)
        # event listing should only show events ticked as show on site
        self.assertEquals(resp.context_data['ticketed_events'].count(), 3)
        self.assertNotIn('not_visible_events', resp.context_data)

        resp = self._get_response(self.staff_user)
        # event listing should show events ticked as show on site
        self.assertEquals(resp.context_data['ticketed_events'].count(), 3)
        # now also has the not_visible_events
        self.assertIn('not_visible_events', resp.context_data)
        self.assertEquals(resp.context_data['not_visible_events'].count(), 1)


class TicketCreateViewTests(TestSetupMixin, TestCase):

    def setUp(self):
        super(TicketCreateViewTests, self).setUp()
        self.ticketed_event = mommy.make_recipe('booking.ticketed_event_max10')
        self.staff_user = User.objects.create_user(
            username='staff', password='test'
        )
        self.staff_user.is_staff = True
        self.staff_user.save()

    def _post_response(self, user, ticketed_event, form_data={}):
        url = reverse(
            'booking:book_ticketed_event',
            kwargs={'event_slug': ticketed_event.slug}
        )
        store = _create_session()
        form_data['ticketed_event'] = ticketed_event.id
        request = self.factory.post(url, form_data)
        request.session = store
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        view = TicketCreateView.as_view()
        return view(request, event_slug=ticketed_event.slug)

    def _get_response(self, user, ticketed_event):
        url = reverse(
            'booking:book_ticketed_event',
            kwargs={'event_slug': ticketed_event.slug}
        )
        store = _create_session()
        request = self.factory.get(
            url, {'ticketed_event': ticketed_event.slug}
        )
        request.session = store
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        view = TicketCreateView.as_view()
        return view(request, event_slug=ticketed_event.slug)

    def test_login_required(self):
        """
        test that page redirects if there is no user logged in
        """
        url = reverse(
            'booking:book_ticketed_event',
            kwargs={'event_slug': self.ticketed_event.slug}
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

        resp = self._get_response(self.user, self.ticketed_event)
        self.assertEqual(resp.status_code, 200)

    def test_get_404s_if_show_on_site_false(self):
        self.ticketed_event.show_on_site = False
        self.ticketed_event.save()

        with self.assertRaises(Http404):
            resp = self._get_response(self.user, self.ticketed_event)
            self.assertEqual(resp.status_code, 404)

        # staff user can see non show-on-site events
        resp = self._get_response(self.staff_user, self.ticketed_event)
        self.assertEqual(resp.status_code, 200)

    def test_create_ticket_booking_on_get(self):
        self.assertEqual(TicketBooking.objects.count(), 0)
        self._get_response(self.user, self.ticketed_event)

        self.assertEqual(TicketBooking.objects.count(), 1)
        tb = TicketBooking.objects.first()
        self.assertEqual(tb.user, self.user)
        self.assertEqual(tb.ticketed_event, self.ticketed_event)

    def test_selecting_quantity_adds_tickets_to_booking(self):

        self.assertEqual(TicketBooking.objects.count(), 0)
        self._get_response(self.user, self.ticketed_event)

        tb = TicketBooking.objects.get(ticketed_event=self.ticketed_event)
        self.assertEqual(tb.tickets.count(), 0)

        self._post_response(
            self.user, self.ticketed_event,
            {'ticket_purchase_form-quantity': 2, 'ticket_booking_id': tb.id}
        )
        tb.refresh_from_db()
        self.assertEqual(tb.tickets.count(), 2)

    def test_create_ticket_booking_uses_existing_available_booking_ref(self):
        """
        If a user goes to the book ticket page, a ticket booking is created;
        if they leave the page before confirming the purchase, the
        booking will be reused on a subsequent attempt
        """
        # create an existing ticket booking for the user and event without
        # tickets
        tb = mommy.make(
            TicketBooking, user=self.user, ticketed_event=self.ticketed_event,
        )
        self.assertEqual(TicketBooking.objects.count(), 1)
        resp = self._get_response(self.user, self.ticketed_event)

        # no new ticket booking has been created as the existing one can be used
        self.assertEqual(TicketBooking.objects.count(), 1)
        self.assertEqual(resp.context_data['ticket_booking'], tb)


        # add tickets to the booking, but leave unconfirmed
        mommy.make(Ticket, ticket_booking=tb)
        self.assertEqual(TicketBooking.objects.count(), 1)
        resp = self._get_response(self.user, self.ticketed_event)

        # no new ticket booking has been created as the existing one can be used
        self.assertEqual(TicketBooking.objects.count(), 1)
        self.assertEqual(resp.context_data['ticket_booking'], tb)

    def test_expired_ticket_booking(self):
        """
        If we post to the create booking view with a ticket booking that doesn't
        exist, it's because a user left the ticket booking page open but didn't
        press the confirm purchase button.  After 1 hour the ticket booking gets
        deleted so the booking no longer exists and page should redirect
        :return:
        """
        # post to change ticket quantity with nonexistent booking
        resp = self._post_response(
            self.user, self.ticketed_event,
            {'ticket_purchase_form-quantity': 2, 'ticket_booking_id': 787283748}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url,
            reverse(
                'booking:ticket_purchase_expired',
                kwargs={'slug': self.ticketed_event.slug}
            )
        )

        # post to purchase tickets with nonexistent booking
        form_data = {
            'ticket_booking_id': 787283748,
            'ticket_formset-MIN_NUM_FORMS': 0,
            'ticket_formset-TOTAL_FORMS': 2,
            'ticket_formset-INITIAL_FORMS': 2,
            'ticket_formset-0-id': 1,
            'ticket_formset-1-id': 2,
            'ticket_formset-submit': 'Confirm purchase',
            }

        resp = self._post_response(self.user, self.ticketed_event, form_data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url,
            reverse(
                'booking:ticket_purchase_expired',
                kwargs={'slug': self.ticketed_event.slug}
            )
        )

    def test_expired_ticket_booking_view(self):
        self.assertTrue(
            self.client.login(username=self.user.username, password='test')
        )
        url = reverse(
                'booking:ticket_purchase_expired',
                kwargs={'slug': self.ticketed_event.slug}
            )
        resp = self.client.get(url)
        self.assertEqual(
            resp.context['ticketed_event'], self.ticketed_event
        )
        self.assertIn(
            'This ticket booking appears to have expired',
            format_content(str(resp.content))
        )


    @patch('booking.management.commands.delete_unconfirmed_ticket_bookings.timezone')
    def test_automatically_cancelled_ticket_booking(self, delete_job_mock_tz):
        delete_job_mock_tz.now.return_value = datetime(
            2015, 10, 1, 11, 30, tzinfo=timezone.utc
        )

        # create a ticket booking
        tb = mommy.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            date_booked=datetime(2015, 10, 1, 10, 0, tzinfo=timezone.utc)
        )
        #add some tickets
        self._post_response(
            self.user, self.ticketed_event,
            {'ticket_purchase_form-quantity': 2, 'ticket_booking_id': tb.id}
        )
        tb.refresh_from_db()
        self.assertEqual(tb.tickets.count(), 2)

        # run the delete unconfirmed job
        management.call_command('delete_unconfirmed_ticket_bookings')

        # try to change ticket quantity
        resp = self._post_response(
            self.user, self.ticketed_event,
            {'ticket_purchase_form-quantity': 4, 'ticket_booking_id': tb.id}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url,
            reverse(
                'booking:ticket_purchase_expired',
                kwargs={'slug': self.ticketed_event.slug}
            )
        )

    def test_create_booking_confirmed_purchase(self):

        tb = mommy.make(
            TicketBooking, user=self.user, ticketed_event=self.ticketed_event
        )
        # add tickets to the booking
        self._post_response(
            self.user, self.ticketed_event,
            {'ticket_purchase_form-quantity': 2, 'ticket_booking_id': tb.id}
        )
        tb.refresh_from_db()
        self.assertFalse(tb.purchase_confirmed)

        self._post_response(
            self.user, self.ticketed_event,
            {
                'ticket_booking_id': tb.id,
                'ticket_formset-MIN_NUM_FORMS': 0,
                'ticket_formset-TOTAL_FORMS': 2,
                'ticket_formset-INITIAL_FORMS': 2,
                'ticket_formset-0-id': tb.tickets.all()[0].id,
                'ticket_formset-1-id': tb.tickets.all()[1].id,
                'ticket_formset-submit': 'Confirm purchase',
            }
        )
        tb.refresh_from_db()
        self.assertTrue(tb.purchase_confirmed)

    def test_create_booking_already_confirmed_purchase(self):
        self.ticketed_event.max_tickets = 4
        self.ticketed_event.save()
        tb = mommy.make(
            TicketBooking, user=self.user, ticketed_event=self.ticketed_event
        )
        tb1 = mommy.make(
            TicketBooking, user=self.user, ticketed_event=self.ticketed_event
        )

        # add tickets to the booking
        self._post_response(
            self.user, self.ticketed_event,
            {'ticket_purchase_form-quantity': 2, 'ticket_booking_id': tb.id}
        )
        tb.refresh_from_db()
        tb.purchase_confirmed = True
        tb.save()

        # can change this quantity to 4 b/c tickets in current booking are not
        # counted against max
        resp = self._post_response(
            self.user, self.ticketed_event,
            {'ticket_purchase_form-quantity': 4, 'ticket_booking_id': tb.id}

        )
        tb.refresh_from_db()
        self.assertEqual(tb.tickets.count(), 4)

    def test_cannot_book_more_tickets_than_available(self):

        self.assertEqual(self.ticketed_event.tickets_left(), 10)
        tb = mommy.make(
            TicketBooking, user=self.user, ticketed_event=self.ticketed_event
        )
        # try to add more tickets to the booking than available
        resp = self._post_response(
            self.user, self.ticketed_event,
            {'ticket_purchase_form-quantity': 11, 'ticket_booking_id': tb.id}
        )
        tb.refresh_from_db()
        self.assertEqual(tb.tickets.count(), 0)
        self.assertIn(
            'Cannot purchase the number of tickets requested.  Only 10 tickets '
            'left',
            resp.rendered_content
        )

    def test_cancelling_during_ticket_booking_deletes_booking_and_tickets(self):
        tb = mommy.make(
            TicketBooking, user=self.user, ticketed_event=self.ticketed_event
        )
        self._post_response(
            self.user, self.ticketed_event,
            {'ticket_purchase_form-quantity': 5, 'ticket_booking_id': tb.id}
        )
        tb.refresh_from_db()
        self.assertEqual(tb.tickets.count(), 5)

        self._post_response(
            self.user, self.ticketed_event,
            {'cancel': 'Cancel', 'ticket_booking_id': tb.id}
        )
        with self.assertRaises(TicketBooking.DoesNotExist):
            TicketBooking.objects.get(id=tb.id)

        self.assertEqual(Ticket.objects.count(), 0)

    def test_can_change_ticket_quantity_during_process(self):
        tb = mommy.make(
            TicketBooking, user=self.user, ticketed_event=self.ticketed_event
        )
        # try to add more tickets to the booking than available
        self._post_response(
            self.user, self.ticketed_event,
            {'ticket_purchase_form-quantity': 4, 'ticket_booking_id': tb.id}
        )
        tb.refresh_from_db()
        self.assertEqual(tb.tickets.count(), 4)

        self._post_response(
            self.user, self.ticketed_event,
            {'ticket_purchase_form-quantity': 8, 'ticket_booking_id': tb.id}
        )
        tb.refresh_from_db()
        self.assertEqual(tb.tickets.count(), 8)

        self._post_response(
            self.user, self.ticketed_event,
            {'ticket_purchase_form-quantity': 4, 'ticket_booking_id': tb.id}
        )
        self.assertEqual(tb.tickets.count(), 4)

    def test_paypal_form_only_displayed_if_ticket_cost_and_payment_open(self):
        tb = mommy.make(
            TicketBooking, user=self.user, ticketed_event=self.ticketed_event
        )
        # add tickets to the booking
        self._post_response(
            self.user, self.ticketed_event,
            {'ticket_purchase_form-quantity': 1, 'ticket_booking_id': tb.id}
        )

        form_data = {
                'ticket_booking_id': tb.id,
                'ticket_formset-MIN_NUM_FORMS': 0,
                'ticket_formset-TOTAL_FORMS': 1,
                'ticket_formset-INITIAL_FORMS': 1,
                'ticket_formset-0-id': tb.tickets.all()[0].id,
                'ticket_formset-submit': 'Confirm purchase',
            }

        resp = self._post_response(self.user, self.ticketed_event, form_data)
        self.assertEqual(self.ticketed_event.ticket_cost, 10)
        self.assertTrue(self.ticketed_event.payment_open)
        self.assertIn('paypalform', resp.context_data)

        self.ticketed_event.ticket_cost = 0
        self.ticketed_event.save()
        resp = self._post_response(self.user, self.ticketed_event, form_data)
        self.assertEqual(self.ticketed_event.ticket_cost, 0)
        # setting ticket cost to 0 makes payment_open false
        self.assertFalse(self.ticketed_event.payment_open)
        self.assertNotIn('paypalform', resp.context_data)

        self.ticketed_event.ticket_cost = 10
        self.ticketed_event.payment_open = False
        self.ticketed_event.save()
        resp = self._post_response(self.user, self.ticketed_event, form_data)
        self.assertEqual(self.ticketed_event.ticket_cost, 10)
        self.assertFalse(self.ticketed_event.payment_open)
        self.assertNotIn('paypalform', resp.context_data)

    @patch('booking.views.ticketed_views.timezone')
    def test_date_booked_reset_when_purchase_confirmed(self, mock_tz):
        mock_tz.now.return_value = datetime(2015, 10, 10, tzinfo=timezone.utc)

        tb = mommy.make(
            TicketBooking, user=self.user, ticketed_event=self.ticketed_event,
            date_booked=datetime(2015, 10, 1, tzinfo=timezone.utc)
        )
        self.assertEqual(tb.tickets.count(), 0)
        # add tickets to the booking
        self._post_response(
            self.user, self.ticketed_event,
            {'ticket_purchase_form-quantity': 1, 'ticket_booking_id': tb.id}
        )
        tb.refresh_from_db()
        self.assertEqual(tb.tickets.count(), 1)
        # date booked is still the same
        self.assertEqual(tb.date_booked, datetime(2015, 10, 1, tzinfo=timezone.utc))

        form_data = {
                'ticket_booking_id': tb.id,
                'ticket_formset-MIN_NUM_FORMS': 0,
                'ticket_formset-TOTAL_FORMS': 1,
                'ticket_formset-INITIAL_FORMS': 1,
                'ticket_formset-0-id': tb.tickets.all()[0].id,
                'ticket_formset-submit': 'Confirm purchase',
            }
        self._post_response(self.user, self.ticketed_event, form_data)
        tb.refresh_from_db()
        self.assertTrue(tb.purchase_confirmed)
        # date booked has been update to now
        self.assertEqual(tb.date_booked, datetime(2015, 10, 10, tzinfo=timezone.utc))

    def test_email_sent_to_user_when_booked(self):
        tb = mommy.make(
            TicketBooking, user=self.user, ticketed_event=self.ticketed_event
        )
        # add tickets to the booking
        self._post_response(
            self.user, self.ticketed_event,
            {'ticket_purchase_form-quantity': 1, 'ticket_booking_id': tb.id}
        )

        form_data = {
                'ticket_booking_id': tb.id,
                'ticket_formset-MIN_NUM_FORMS': 0,
                'ticket_formset-TOTAL_FORMS': 1,
                'ticket_formset-INITIAL_FORMS': 1,
                'ticket_formset-0-id': tb.tickets.all()[0].id,
                'ticket_formset-submit': 'Confirm purchase',
            }

        self._post_response(self.user, self.ticketed_event, form_data)

        self.assertEqual(len(mail.outbox), 1)
        user_email = mail.outbox[0]
        self.assertEqual(
            user_email.subject,
            '{} Ticket booking confirmed for {}: ref {}'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                self.ticketed_event,
                tb.booking_reference
            )
        )
        self.assertEqual(user_email.to, [tb.user.email])

    @patch('booking.views.ticketed_views.send_mail')
    def test_error_sending_user_email(self, mock_send):
        mock_send.side_effect = Exception('Error sending email')
        tb = mommy.make(
            TicketBooking, user=self.user, ticketed_event=self.ticketed_event
        )
        # add tickets to the booking
        self._post_response(
            self.user, self.ticketed_event,
            {'ticket_purchase_form-quantity': 1, 'ticket_booking_id': tb.id}
        )

        form_data = {
                'ticket_booking_id': tb.id,
                'ticket_formset-MIN_NUM_FORMS': 0,
                'ticket_formset-TOTAL_FORMS': 1,
                'ticket_formset-INITIAL_FORMS': 1,
                'ticket_formset-0-id': tb.tickets.all()[0].id,
                'ticket_formset-submit': 'Confirm purchase',
            }

        self._post_response(self.user, self.ticketed_event, form_data)

        self.assertEqual(len(mail.outbox), 1)

        self.assertEqual(mail.outbox[0].to, [settings.SUPPORT_EMAIL])

    def test_email_sent_studio_when_booked_only_if_flag_set(self):
        self.ticketed_event.email_studio_when_purchased = True
        self.ticketed_event.save()
        tb = mommy.make(
            TicketBooking, user=self.user, ticketed_event=self.ticketed_event
        )
        # add tickets to the booking
        self._post_response(
            self.user, self.ticketed_event,
            {'ticket_purchase_form-quantity': 1, 'ticket_booking_id': tb.id}
        )

        form_data = {
                'ticket_booking_id': tb.id,
                'ticket_formset-MIN_NUM_FORMS': 0,
                'ticket_formset-TOTAL_FORMS': 1,
                'ticket_formset-INITIAL_FORMS': 1,
                'ticket_formset-0-id': tb.tickets.all()[0].id,
                'ticket_formset-submit': 'Confirm purchase',
            }

        self._post_response(self.user, self.ticketed_event, form_data)

        self.assertEqual(len(mail.outbox), 2)
        user_email = mail.outbox[0]
        self.assertEqual(
            user_email.subject,
            '{} Ticket booking confirmed for {}: ref {}'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                self.ticketed_event,
                tb.booking_reference
            )
        )
        self.assertEqual(user_email.to, [tb.user.email])
        studio_email = mail.outbox[1]
        self.assertEqual(
            studio_email.subject,
            '{} Ticket booking confirmed for {}: ref {}'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                self.ticketed_event,
                tb.booking_reference
            )
        )
        self.assertEqual(studio_email.to, [settings.DEFAULT_STUDIO_EMAIL])

    @patch('booking.views.ticketed_views.send_mail')
    def test_error_sending_user__and_studio_email(self, mock_send):
        mock_send.side_effect = Exception('Error sending email')
        self.ticketed_event.email_studio_when_purchased = True
        self.ticketed_event.save()
        tb = mommy.make(
            TicketBooking, user=self.user, ticketed_event=self.ticketed_event
        )
        # add tickets to the booking
        self._post_response(
            self.user, self.ticketed_event,
            {'ticket_purchase_form-quantity': 1, 'ticket_booking_id': tb.id}
        )

        form_data = {
                'ticket_booking_id': tb.id,
                'ticket_formset-MIN_NUM_FORMS': 0,
                'ticket_formset-TOTAL_FORMS': 1,
                'ticket_formset-INITIAL_FORMS': 1,
                'ticket_formset-0-id': tb.tickets.all()[0].id,
                'ticket_formset-submit': 'Confirm purchase',
            }

        self._post_response(self.user, self.ticketed_event, form_data)

        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, [settings.SUPPORT_EMAIL])
        self.assertEqual(mail.outbox[1].to, [settings.SUPPORT_EMAIL])

    def test_submit_with_form_errors(self):
        self.ticketed_event.extra_ticket_info_label = "Extra info"
        self.ticketed_event.extra_ticket_info_required = True
        self.ticketed_event.save()

        tb = mommy.make(
            TicketBooking, user=self.user, ticketed_event=self.ticketed_event
        )
        # add tickets to the booking
        self._post_response(
            self.user, self.ticketed_event,
            {'ticket_purchase_form-quantity': 1, 'ticket_booking_id': tb.id}
        )

        form_data = {
                'ticket_booking_id': tb.id,
                'ticket_formset-MIN_NUM_FORMS': 0,
                'ticket_formset-TOTAL_FORMS': 1,
                'ticket_formset-INITIAL_FORMS': 1,
                'ticket_formset-0-id': tb.tickets.all()[0].id,
                'ticket_formset-submit': 'Confirm purchase',
            }

        resp = self._post_response(self.user, self.ticketed_event, form_data)

        self.assertIn(
            'Please correct errors in the form below',
            format_content(resp.rendered_content)
        )
        self.assertIn(
            'Extra info * This field is required',
            format_content(resp.rendered_content)
        )


class TicketBookingListViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(TicketBookingListViewTests, cls).setUpTestData()
        cls.ticketed_event = mommy.make_recipe('booking.ticketed_event_max10')

    def _get_response(self, user):
        url = reverse('booking:ticket_bookings')
        request = self.factory.get(url)
        request.user = user
        view = TicketBookingListView.as_view()
        return view(request)

    def test_login_required(self):
        """
        test that page redirects if there is no user logged in
        """
        url = reverse('booking:ticket_bookings')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

    def test_booking_list(self):
        """
        Test that only bookings for future events are listed)
        """
        past_bookings = mommy.make(
            TicketBooking,
            purchase_confirmed=True,
            ticketed_event__date=timezone.now() - timedelta(10),
            user=self.user,
            _quantity=2
        )
        future_bookings = mommy.make(
            TicketBooking,
            purchase_confirmed=True,
            ticketed_event__date=timezone.now() + timedelta(10),
            user=self.user,
            _quantity=2
        )
        for booking in TicketBooking.objects.all():
            mommy.make(Ticket, ticket_booking=booking)

        resp = self._get_response(self.user)
        self.assertEqual(
            len(resp.context_data['ticketbookinglist']), 2
        )
        for tb in resp.context_data['ticketbookinglist']:
            self.assertIn(tb['ticket_booking'], future_bookings)
            self.assertNotIn(tb['ticket_booking'], past_bookings)

    def test_booking_list_by_user(self):
        """
        Test that only ticket bookings for this user are listed
        """
        user_bookings = mommy.make(
            TicketBooking,
            purchase_confirmed=True,
            ticketed_event__date=timezone.now() + timedelta(10),
            user=self.user,
            _quantity=2
        )
        other_bookings = mommy.make(
            TicketBooking,
            purchase_confirmed=True,
            ticketed_event__date=timezone.now() + timedelta(10),
            _quantity=2
        )
        for booking in TicketBooking.objects.all():
            mommy.make(Ticket, ticket_booking=booking)

        resp = self._get_response(self.user)
        self.assertEqual(
            len(resp.context_data['ticketbookinglist']), 2
        )
        for tb in resp.context_data['ticketbookinglist']:
            self.assertIn(tb['ticket_booking'], user_bookings)
            self.assertNotIn(tb['ticket_booking'], other_bookings)

    def test_cancelled_events_shown_in_booking_list(self):
        """
        Test that all future ticket bookings for cancelled events for this
        user are listed
        """
        open_bookings = mommy.make(
            TicketBooking,
            purchase_confirmed=True,
            ticketed_event__date=timezone.now() + timedelta(10),
            user=self.user,
            _quantity=2
        )
        cancelled_bookings = mommy.make(
            TicketBooking,
            purchase_confirmed=True,
            ticketed_event__date=timezone.now() + timedelta(10),
            user=self.user,
            cancelled=True,
            _quantity=2
        )
        for booking in TicketBooking.objects.all():
            mommy.make(Ticket, ticket_booking=booking)

        resp = self._get_response(self.user)
        self.assertEqual(
            len(resp.context_data['ticketbookinglist']), 4
        )

    def test_paypal_form_only_shown_for_open_bookings(self):

        open_bookings = mommy.make(
            TicketBooking,
            ticketed_event=self.ticketed_event,
            purchase_confirmed=True,
            user=self.user,
            _quantity=2
        )
        cancelled_bookings = mommy.make(
            TicketBooking,
            ticketed_event=self.ticketed_event,
            purchase_confirmed=True,
            user=self.user,
            cancelled=True,
            _quantity=2
        )
        for booking in TicketBooking.objects.all():
            mommy.make(Ticket, ticket_booking=booking)

        resp = self._get_response(self.user)
        self.assertEqual(
            len(resp.context_data['ticketbookinglist']), 4
        )

        for tb in resp.context_data['ticketbookinglist']:
            if tb['ticket_booking'] in open_bookings:
                self.assertIsNotNone(tb['paypalform'])
            else:
                self.assertIsNone(tb['paypalform'])

    def test_paypal_form_only_shown_for_unpaid_bookings(self):

        paid_bookings = mommy.make(
            TicketBooking,
            ticketed_event=self.ticketed_event,
            purchase_confirmed=True,
            user=self.user,
            paid=True,
            _quantity=2
        )
        unpaid_bookings = mommy.make(
            TicketBooking,
            ticketed_event=self.ticketed_event,
            purchase_confirmed=True,
            user=self.user,
            paid=False,
            _quantity=2
        )
        for booking in TicketBooking.objects.all():
            mommy.make(Ticket, ticket_booking=booking)

        resp = self._get_response(self.user)
        self.assertEqual(
            len(resp.context_data['ticketbookinglist']), 4
        )

        for tb in resp.context_data['ticketbookinglist']:
            if tb['ticket_booking'] in unpaid_bookings:
                self.assertIsNotNone(tb['paypalform'])
            else:
                self.assertIsNone(tb['paypalform'])

    def test_paypal_form_not_shown_for_event_with_payment_not_open(self):

        event_not_open = mommy.make_recipe(
            'booking.ticketed_event_max10', payment_open=False
        )
        bookings_open_event = mommy.make(
            TicketBooking,
            ticketed_event=self.ticketed_event,
            purchase_confirmed=True,
            user=self.user,
            _quantity=2
        )
        bookings_not_open_event = mommy.make(
            TicketBooking,
            ticketed_event=event_not_open,
            purchase_confirmed=True,
            user=self.user,
            _quantity=2
        )
        for booking in TicketBooking.objects.all():
            mommy.make(Ticket, ticket_booking=booking)

        resp = self._get_response(self.user)
        self.assertEqual(
            len(resp.context_data['ticketbookinglist']), 4
        )

        for tb in resp.context_data['ticketbookinglist']:
            if tb['ticket_booking'] in bookings_open_event:
                self.assertIsNotNone(tb['paypalform'])
            else:
                self.assertIsNone(tb['paypalform'])

    def test_payment_and_booking_status_display_in_template(self):
        """
        event cancelled: "EVENT CANCELLED"
        booking cancelled: "BOOKING CANCELLED"
        payment_open False: Online payments not open
        paid: PAID
        :return:
        """

        tb = mommy.make(
            TicketBooking,
            ticketed_event=self.ticketed_event,
            purchase_confirmed=True,
            user=self.user,
            paid=True
        )
        mommy.make(Ticket, ticket_booking=tb)

        resp = self._get_response(self.user)
        self.assertIn('PAID', resp.rendered_content)

        tb.cancelled = True
        tb.save()
        resp = self._get_response(self.user)
        self.assertIn('BOOKING CANCELLED', resp.rendered_content)

        tb.cancelled = False
        tb.save()
        self.ticketed_event.cancelled = True
        self.ticketed_event.save()
        resp = self._get_response(self.user)
        self.assertIn('EVENT CANCELLED', resp.rendered_content)

        self.ticketed_event.payment_open = False
        self.ticketed_event.cancelled = False
        self.ticketed_event.save()
        tb.paid = False
        tb.save()
        resp = self._get_response(self.user)
        self.assertIn('Online payments not open', resp.rendered_content)


class TicketBookingHistoryListViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(TicketBookingHistoryListViewTests, cls).setUpTestData()
        cls.ticketed_event = mommy.make_recipe('booking.ticketed_event_max10')

    def _get_response(self, user):
        url = reverse('booking:ticket_booking_history')
        request = self.factory.get(url)
        request.user = user
        view = TicketBookingHistoryListView.as_view()
        return view(request)

    def test_login_required(self):
        """
        test that page redirects if there is no user logged in
        """
        url = reverse('booking:ticket_booking_history')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

    def test_booking_history_list(self):
        """
        Test that only past bookings are listed)
        """
        past_bookings = mommy.make(
            TicketBooking,
            purchase_confirmed=True,
            ticketed_event__date=timezone.now() - timedelta(10),
            user=self.user,
            _quantity=2
        )
        future_bookings = mommy.make(
            TicketBooking,
            purchase_confirmed=True,
            ticketed_event__date=timezone.now() + timedelta(10),
            user=self.user,
            _quantity=2
        )
        for booking in TicketBooking.objects.all():
            mommy.make(Ticket, ticket_booking=booking)

        resp = self._get_response(self.user)
        self.assertEqual(
            len(resp.context_data['ticketbookinglist']), 2
        )
        for tb in resp.context_data['ticketbookinglist']:
            self.assertIn(tb['ticket_booking'], past_bookings)
            self.assertNotIn(tb['ticket_booking'], future_bookings)

    def test_booking_history_list_by_user(self):
        """
        Test that only past booking for this user are listed
        """
        user_bookings = mommy.make(
            TicketBooking,
            purchase_confirmed=True,
            ticketed_event__date=timezone.now() - timedelta(10),
            user=self.user,
            _quantity=2
        )
        future_user_bookings = mommy.make(
            TicketBooking,
            purchase_confirmed=True,
            ticketed_event__date=timezone.now() + timedelta(10),
            user=self.user,
            _quantity=2
        )
        other_bookings = mommy.make(
            TicketBooking,
            purchase_confirmed=True,
            ticketed_event__date=timezone.now() - timedelta(10),
            _quantity=2
        )
        for booking in TicketBooking.objects.all():
            mommy.make(Ticket, ticket_booking=booking)

        resp = self._get_response(self.user)
        self.assertEqual(
            len(resp.context_data['ticketbookinglist']), 2
        )
        for tb in resp.context_data['ticketbookinglist']:
            self.assertIn(tb['ticket_booking'], user_bookings)
            self.assertNotIn(tb['ticket_booking'], other_bookings)
            self.assertNotIn(tb['ticket_booking'], future_user_bookings)

    def test_cancelled_booking_shown_in_booking_history(self):
        """
        Test that cancelled bookings are listed in booking history
        """
        open_bookings = mommy.make(
            TicketBooking,
            purchase_confirmed=True,
            ticketed_event__date=timezone.now() - timedelta(10),
            user=self.user,
            _quantity=2
        )
        cancelled_bookings = mommy.make(
            TicketBooking,
            purchase_confirmed=True,
            ticketed_event__date=timezone.now() - timedelta(10),
            user=self.user,
            cancelled=True,
            _quantity=2
        )
        for booking in TicketBooking.objects.all():
            mommy.make(Ticket, ticket_booking=booking)

        resp = self._get_response(self.user)
        self.assertEqual(
            len(resp.context_data['ticketbookinglist']), 4
        )


class TicketBookingViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(TicketBookingViewTests, cls).setUpTestData()
        cls.ticketed_event = mommy.make_recipe(
            'booking.ticketed_event_max10',
            extra_ticket_info_label="Name",
        )

    def setUp(self):
        super(TicketBookingViewTests, self).setUp()
        self.ticket_booking = mommy.make(
            TicketBooking, user=self.user, purchase_confirmed=True,
            ticketed_event=self.ticketed_event
        )
        mommy.make(Ticket, ticket_booking=self.ticket_booking)

    def _get_response(self, user, ticket_booking):
        url = reverse(
            'booking:ticket_booking',
            kwargs={'ref': ticket_booking.booking_reference}
        )
        request = self.factory.get(url)
        request.user = user
        view = TicketBookingView.as_view()
        return view(request, ref=ticket_booking.booking_reference)

    def _post_response(self, user, ticket_booking, form_data={}):
        url = reverse(
            'booking:ticket_booking',
            kwargs={'ref': ticket_booking.booking_reference}
        )
        store = _create_session()
        request = self.factory.post(url, form_data)
        request.user = user
        request.session = store
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        view = TicketBookingView.as_view()
        return view(request, ref=ticket_booking.booking_reference)

    def test_login_required(self):
        """
        test that page redirects if there is no user logged in
        """
        url = reverse(
            'booking:ticket_booking',
            kwargs={'ref': self.ticket_booking.booking_reference}
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

    def test_tickets_displayed(self):
        resp = self._get_response(self.user, self.ticket_booking)
        self.assertEqual(
            resp.context_data['ticketed_event'],
            self.ticket_booking.ticketed_event
        )
        self.assertEqual(
            resp.context_data['ticket_booking'], self.ticket_booking
        )
        self.assertEqual(
            [tk.id for tk in resp.context_data['tickets']],
            [tk.id for tk in self.ticket_booking.tickets.all()]
        )
        self.assertEqual(
            len(resp.context_data['ticket_formset'].forms), 1
        )

    def test_can_update_ticket_info(self):
        ticket = self.ticket_booking.tickets.first()
        self.assertEqual(ticket.extra_ticket_info, '')
        form_data = {
            'ticket_formset-MIN_NUM_FORMS': 0,
            'ticket_formset-TOTAL_FORMS': 1,
            'ticket_formset-INITIAL_FORMS': 1,
            'ticket_formset-0-id': ticket.id,
            'ticket_formset-submit': 'Save',
            'ticket_formset-0-extra_ticket_info': "test name"
        }
        self._post_response(self.user, self.ticket_booking, form_data)
        ticket.refresh_from_db()
        self.assertEqual(ticket.extra_ticket_info, 'test name')

    def test_submit_without_changes(self):
        ticket = self.ticket_booking.tickets.first()
        form_data = {
            'ticket_formset-MIN_NUM_FORMS': 0,
            'ticket_formset-TOTAL_FORMS': 1,
            'ticket_formset-INITIAL_FORMS': 1,
            'ticket_formset-0-id': ticket.id,
            'ticket_formset-submit': 'Save',
        }
        url = reverse(
            'booking:ticket_booking',
            kwargs={'ref': self.ticket_booking.booking_reference}
        )
        self.assertTrue(
            self.client.login(username=self.user.username, password='test')
        )
        resp = self.client.post(url, form_data, follow=True)
        self.assertIn('No changes made', format_content(resp.rendered_content))

    def test_submit_with_form_errors(self):
        self.ticketed_event.extra_ticket_info_required = True
        self.ticketed_event.save()
        ticket = self.ticket_booking.tickets.first()
        form_data = {
            'ticket_formset-MIN_NUM_FORMS': 0,
            'ticket_formset-TOTAL_FORMS': 1,
            'ticket_formset-INITIAL_FORMS': 1,
            'ticket_formset-0-id': ticket.id,
            'ticket_formset-0-extra_ticket_info': '',
            'ticket_formset-submit': 'Save',
        }
        url = reverse(
            'booking:ticket_booking',
            kwargs={'ref': self.ticket_booking.booking_reference}
        )
        self.assertTrue(
            self.client.login(username=self.user.username, password='test')
        )
        resp = self.client.post(url, form_data, follow=True)
        self.assertIn(
            'Please correct errors in the form below',
            format_content(resp.rendered_content)
        )
        self.assertIn(
            'Additional ticket information '
            'Ticket # 1 Name * This field is required',
            format_content(resp.rendered_content)
        )


class TicketBookingCancelViewTests(TestSetupMixin, TestCase):

    def setUp(self):
        super(TicketBookingCancelViewTests, self).setUp()
        self.ticketed_event = mommy.make_recipe(
            'booking.ticketed_event_max10'
        )
        self.ticket_booking = mommy.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            purchase_confirmed=True
        )
        mommy.make(Ticket, ticket_booking=self.ticket_booking)

    def _get_response(self, user, ticket_booking):
        url = reverse(
            'booking:cancel_ticket_booking', args=[ticket_booking.id]
        )
        request = self.factory.get(url)
        request.user = user
        view = TicketBookingCancelView.as_view()
        return view(request, pk=ticket_booking.id)

    def _post_response(self, user, ticket_booking, form_data={}):
        url = reverse(
            'booking:cancel_ticket_booking', args=[ticket_booking.id]
        )
        store = _create_session()
        request = self.factory.post(url, form_data)
        request.user = user
        request.session = store
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        view = TicketBookingCancelView.as_view()
        return view(request, pk=ticket_booking.id)

    def test_login_required(self):
        """
        test that page redirects if there is no user logged in
        """
        url = reverse(
            'booking:cancel_ticket_booking', args=[self.ticket_booking.id]
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

    def test_can_access_if_logged_in(self):
        resp = self._get_response(self.user, self.ticket_booking)
        self.assertEqual(resp.status_code, 200)

    def test_can_cancel_unpaid_ticket_booking(self):
        self.assertFalse(self.ticket_booking.cancelled)
        resp = self._post_response(
            self.user, self.ticket_booking,
            {
                'id': self.ticket_booking.id,
                'confirm_cancel': 'Yes, cancel my ticket booking'
            }
        )
        self.ticket_booking.refresh_from_db()
        self.assertTrue(self.ticket_booking.cancelled)

    def test_cannot_cancel_paid_ticket_booking(self):
        self.ticket_booking.paid = True
        self.ticket_booking.save()
        self.assertFalse(self.ticket_booking.cancelled)
        resp = self._post_response(
            self.user, self.ticket_booking,
            {
                'id': self.ticket_booking.id,
                'confirm_cancel': 'Yes, cancel my ticket booking'
            }
        )
        self.ticket_booking.refresh_from_db()
        self.assertFalse(self.ticket_booking.cancelled)

    def test_cannot_cancel_ticket_booking_for_cancelled_event(self):
        self.ticketed_event.cancelled = True
        self.ticketed_event.save()
        self.assertFalse(self.ticket_booking.cancelled)
        resp = self._post_response(
            self.user, self.ticket_booking,
            {
                'id': self.ticket_booking.id,
                'confirm_cancel': 'Yes, cancel my ticket booking'
            }
        )
        self.ticket_booking.refresh_from_db()
        self.assertFalse(self.ticket_booking.cancelled)

    def test_cancel_email_is_sent_to_user(self):
        self.assertFalse(self.ticket_booking.cancelled)
        resp = self._post_response(
            self.user, self.ticket_booking,
            {
                'id': self.ticket_booking.id,
                'confirm_cancel': 'Yes, cancel my ticket booking'
            }
        )
        self.ticket_booking.refresh_from_db()
        self.assertTrue(self.ticket_booking.cancelled)
        self.assertEqual(len(mail.outbox), 1)
        user_email = mail.outbox[0]
        self.assertEqual(user_email.to, [self.user.email])
        self.assertEqual(
            user_email.subject,
            '{} Ticket booking ref {} cancelled'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                self.ticket_booking.booking_reference
            )
        )

    @patch('booking.views.ticketed_views.send_mail')
    def test_errors_sending_cancel_email(self, mock_send):
        mock_send.side_effect = Exception('Error sending email')
        self.assertFalse(self.ticket_booking.cancelled)
        self._post_response(
            self.user, self.ticket_booking,
            {
                'id': self.ticket_booking.id,
                'confirm_cancel': 'Yes, cancel my ticket booking'
            }
        )
        self.ticket_booking.refresh_from_db()
        self.assertTrue(self.ticket_booking.cancelled)
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [settings.SUPPORT_EMAIL])
        self.assertEqual(
            email.subject,
            '{} An error occurred! '
            '(TicketBookingCancelView - user email)'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
            )
        )

    def test_cannot_cancel_already_cancelled_ticket_booking(self):
        self.ticket_booking.cancelled = True
        self.ticket_booking.save()
        resp = self._post_response(
            self.user, self.ticket_booking,
            {
                'id': self.ticket_booking.id,
                'confirm_cancel': 'Yes, cancel my ticket booking'
            }
        )
        self.ticket_booking.refresh_from_db()
        self.assertTrue(self.ticket_booking.cancelled)
        self.assertEqual(len(mail.outbox), 0)
