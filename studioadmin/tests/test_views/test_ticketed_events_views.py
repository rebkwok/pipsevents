# -*- coding: utf-8 -*-
import pytz
from datetime import timedelta
from unittest.mock import patch
from model_bakery import baker

from django.conf import settings
from django.urls import reverse
from django.core import mail
from django.test import TestCase

from django.utils import timezone

from booking.models import TicketedEvent, TicketBooking, Ticket
from common.tests.helpers import (
    _add_user_email_addresses, format_content
)

from studioadmin.tests.test_views.helpers import TestPermissionMixin


class TicketedEventAdminListViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.ticketed_event = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=timezone.now() + timedelta(2)
        )
        self.past_ticketed_event = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=timezone.now() - timedelta(2)
        )
        self.url = reverse('studioadmin:ticketed_events')
        self.client.force_login(self.staff_user)

    def formset_data(self, extra_data={}):

        data = {
            'form-TOTAL_FORMS': 1,
            'form-INITIAL_FORMS': 1,
            'form-0-id': str(self.ticketed_event.id),
            }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_cannot_access_without_login(self):
        self.client.logout()
        resp = self.client.get(self.url)
        redirected_url = reverse('account_login') + "?next={}".format(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_unless_staff_user(self):
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

        self.client.force_login(self.staff_user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_get_shows_upcoming_events(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        formset = resp.context_data['ticketed_event_formset']
        self.assertEqual(
            [ev.id for ev in formset.queryset],
            [self.ticketed_event.id]
        )

    def test_side_nav_selection_in_context(self):
        resp = self.client.get(self.url)
        self.assertEqual(
            resp.context_data['sidenav_selection'], 'ticketed_evs'
        )

    def test_show_ticketed_events_by_past_or_upcoming(self):
        resp = self.client.post(self.url, {'past': 'Show past events'})
        self.assertEqual(resp.status_code, 200)
        formset = resp.context_data['ticketed_event_formset']
        self.assertEqual(
            [ev.id for ev in formset.queryset],
            [self.past_ticketed_event.id]
        )

        resp = self.client.post(self.url, {'upcoming': 'Show upcoming events'})
        self.assertEqual(resp.status_code, 200)
        formset = resp.context_data['ticketed_event_formset']
        self.assertEqual(
            [ev.id for ev in formset.queryset],
            [self.ticketed_event.id]
        )

    def test_include_cancelled_events(self):
        cancelled_future_event = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=timezone.now() + timedelta(2),
            cancelled=True
        )
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        formset = resp.context_data['ticketed_event_formset']
        self.assertEqual(formset.queryset.count(), 2)
        self.assertEqual(
            sorted([ev.id for ev in formset.queryset]),
            [self.ticketed_event.id, cancelled_future_event.id]
        )

    def test_can_delete(self):
        self.assertEqual(TicketedEvent.objects.all().count(), 2)
        formset_data = self.formset_data({
            'form-0-DELETE': 'on',
            'formset_submitted': 'Save changes'
            })
        resp = self.client.post(self.url, formset_data)
        self.assertEqual(TicketedEvent.objects.all().count(), 1)

    def test_cancel_button_shown_for_events_with_bookings(self):
        """
        Test delete checkbox is not shown for events with confirmed bookings;
        cancel button shown instead
        """
        ticketed_event = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=timezone.now() + timedelta(2)
        )
        baker.make(
            TicketBooking, ticketed_event=ticketed_event,
            purchase_confirmed=True
        )

        resp = self.client.get(self.url)
        self.assertIn(
            'form-0-DELETE', resp.rendered_content
        )
        self.assertNotIn(
            'form-1-DELETE', resp.rendered_content
        )
        self.assertIn('cancel_button', resp.rendered_content)

    def test_can_edit_event(self):
        self.assertTrue(self.ticketed_event.show_on_site)
        self.assertTrue(self.ticketed_event.payment_open)
        self.assertTrue(self.ticketed_event.advance_payment_required)

        formset_data = self.formset_data({
            'form-0-show_on_site': False,
            'form-0-payment_open': False,
            'form-0-advance_payment_required': False,
            'formset_submitted': 'Save changes'
            })
        resp = self.client.post(self.url, formset_data)
        self.ticketed_event.refresh_from_db()
        self.assertFalse(self.ticketed_event.show_on_site)
        self.assertFalse(self.ticketed_event.payment_open)
        self.assertFalse(self.ticketed_event.advance_payment_required)

    def test_save_with_no_changes(self):
        formset_data = self.formset_data(
            {
                'form-0-payment_open': self.ticketed_event.payment_open,
                'form-0-advance_payment_required':
                    self.ticketed_event.advance_payment_required,
                'form-0-show_on_site': self.ticketed_event.show_on_site,
                'formset_submitted': 'Save changes'
            }
        )
        resp = self.client.post(
            reverse('studioadmin:ticketed_events'),
            formset_data,
            follow=True
        )
        self.assertIn(
            'No changes were made', format_content(resp.rendered_content)
        )


class TicketedEventAdminUpdateViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(TicketedEventAdminUpdateViewTests, self).setUp()
        self.ticketed_event = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=timezone.now().replace(
                second=0, microsecond=0
            ) + timedelta(2)
        )
        self.past_ticketed_event = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=timezone.now() - timedelta(2)
        )
        self.url = reverse(
            'studioadmin:edit_ticketed_event', kwargs={'slug': self.ticketed_event.slug}
        )
        self.past_url = reverse(
            'studioadmin:edit_ticketed_event', kwargs={'slug': self.past_ticketed_event.slug}
        )
        self.client.force_login(self.staff_user)

    def form_data(self, extra_data={}):
        # make the date uk time before stringifying for form input
        uk = pytz.timezone('Europe/London')
        date = self.ticketed_event.date.astimezone(uk)
        data = {
            'name': self.ticketed_event.name,
            'date': date.strftime('%d %b %Y %H:%M'),
            'contact_email': self.ticketed_event.contact_email,
            'contact_person': self.ticketed_event.contact_person,
            'location': self.ticketed_event.location,
            'ticket_cost': self.ticketed_event.ticket_cost,
            'paypal_email': settings.DEFAULT_PAYPAL_EMAIL,
        }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_cannot_access_without_login(self):
        self.client.logout()
        resp = self.client.get(self.url)
        redirected_url = reverse('account_login') + "?next={}".format(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_unless_staff_user(self):
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

        self.client.force_login(self.staff_user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_can_edit_event(self):
        self.assertEqual(self.ticketed_event.ticket_cost, 10)
        self.assertEqual(
            self.ticketed_event.location, "Watermelon Studio"
        )
        self.assertEqual(
            self.ticketed_event.contact_email, settings.DEFAULT_STUDIO_EMAIL
        )
        resp = self.client.post(
            self.url,
            self.form_data(
                {
                    'ticket_cost': 5,
                    'location': 'Test location',
                    'contact_email': 'test@test.com'
                }
            )
        )
        self.ticketed_event.refresh_from_db()
        self.assertEqual(self.ticketed_event.ticket_cost, 5)
        self.assertEqual(
            self.ticketed_event.location, "Test location"
        )
        self.assertEqual(
            self.ticketed_event.contact_email, "test@test.com"
        )

    def test_submit_form_without_changes(self):
        self.ticketed_event.payment_time_allowed = 8
        self.ticketed_event.save()

        form_data = self.form_data(
            {
                'id': self.ticketed_event.id,
                'description': self.ticketed_event.description,
                'max_tickets': self.ticketed_event.max_tickets,
                'payment_open': self.ticketed_event.payment_open,
                'advance_payment_required':
                    self.ticketed_event.advance_payment_required,
                'payment_info': self.ticketed_event.payment_info,
                'payment_time_allowed':
                    self.ticketed_event.payment_time_allowed,
                'email_studio_when_purchased':
                    self.ticketed_event.email_studio_when_purchased,
                'show_on_site': self.ticketed_event.show_on_site,
                'cancelled': self.ticketed_event.cancelled,
                'paypal_email': settings.DEFAULT_PAYPAL_EMAIL,
            }
        )
        self.assertTrue(self.client.login(
            username=self.staff_user.username, password='test')
        )
        resp = self.client.post(
            self.url, form_data, follow=True
        )
        self.assertIn(
            'No changes made', format_content(resp.rendered_content)
        )

    def test_side_nav_selection_in_context(self):
        resp = self.client.get(self.url)
        self.assertEqual(
            resp.context_data['sidenav_selection'], 'ticketed_evs'
        )

    def test_update_paypal_email_to_non_default(self):
        form_data = self.form_data(
            {
                'id': self.ticketed_event.id,
                'paypal_email': 'testpaypal@test.com',
                'paypal_email_check': 'testpaypal@test.com'
            }
        )
        resp = self.client.post(
            self.url, form_data, follow=True
        )

        self.assertIn(
            "You have changed the paypal receiver email. If you haven't used "
            "this email before, it is strongly recommended that you test the "
            "email address <a href='/studioadmin/test-paypal-email?"
            "email=testpaypal@test.com'>here</a>",
            resp.rendered_content
        )

        self.ticketed_event.refresh_from_db()
        self.assertEqual(self.ticketed_event.paypal_email, 'testpaypal@test.com')

        form_data = self.form_data(
            {
                'id': self.ticketed_event.id,
                'paypal_email': settings.DEFAULT_PAYPAL_EMAIL,
                'paypal_email_check': settings.DEFAULT_PAYPAL_EMAIL
            }
        )
        resp = self.client.post(
            self.url, form_data, follow=True
        )
        self.assertNotIn(
            "You have changed the paypal receiver email.",
            resp.rendered_content
        )
        self.ticketed_event.refresh_from_db()
        self.assertEqual(
            self.ticketed_event.paypal_email, settings.DEFAULT_PAYPAL_EMAIL
        )


class TicketedEventAdminCreateViewTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.url = reverse('studioadmin:add_ticketed_event')

    def setUp(self):
        self.client.force_login(self.staff_user)

    def test_cannot_access_without_login(self):
        self.client.logout()
        resp = self.client.get(self.url)
        redirected_url = reverse('account_login') + "?next={}".format(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_unless_staff_user(self):
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

        self.client.force_login(self.staff_user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_side_nav_selection_in_context(self):
        resp = self.client.get(self.url)
        self.assertEqual(
            resp.context_data['sidenav_selection'], 'add_ticketed_ev'
        )

    def test_can_create_event(self):
        self.assertEqual(TicketedEvent.objects.count(), 0)
        data = {
            'name': "Test event",
            'date': (timezone.now() + timedelta(3)).strftime('%d %b %Y %H:%M'),
            'contact_email': 'test@test.com',
            'contact_person': 'test person',
            'location': 'Watermelon Studio',
            'ticket_cost': 5,
            'paypal_email': settings.DEFAULT_PAYPAL_EMAIL,
        }
        resp = self.client.post(self.url, data)
        self.assertEqual(TicketedEvent.objects.count(), 1)

    def test_create_ticketed_event_with_non_default_paypal_email(self):
        form_data = {
            'name': "Test event",
            'date': (timezone.now() + timedelta(3)).strftime('%d %b %Y %H:%M'),
            'contact_email': 'test@test.com',
            'contact_person': 'test person',
            'location': 'Watermelon Studio',
            'ticket_cost': 5,
            'paypal_email': 'testpaypal@test.com',
            'paypal_email_check': 'testpaypal@test.com'
            }
        resp = self.client.post(self.url, form_data, follow=True)

        self.assertIn(
            "You have changed the paypal receiver email from the default value. "
            "If you haven't used "
            "this email before, it is strongly recommended that you test the "
            "email address <a href='/studioadmin/test-paypal-email?"
            "email=testpaypal@test.com'>here</a>",
            resp.rendered_content
        )

        ticketed_event = TicketedEvent.objects.latest('id')
        self.assertEqual(ticketed_event.paypal_email, 'testpaypal@test.com')

        form_data.update(
            {
                'paypal_email': settings.DEFAULT_PAYPAL_EMAIL,
                'paypal_email_check': ''
            }
        )
        resp = self.client.post(self.url, form_data, follow=True)
        self.assertNotIn(
            "You have changed the paypal receiver email from the default value.",
            resp.rendered_content
        )
        ticketed_event1 = TicketedEvent.objects.latest('id')
        self.assertEqual(
            ticketed_event1.paypal_email, settings.DEFAULT_PAYPAL_EMAIL
        )


class TicketedEventBookingsListViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.ticketed_event = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=timezone.now() + timedelta(2)
        )
        self.ticket_booking = baker.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            purchase_confirmed=True, user=self.user
        )
        self.ticket_booking1 = baker.make(
            TicketBooking, purchase_confirmed=True, user=self.user
        )
        for tb in [self.ticket_booking, self.ticket_booking1]:
            baker.make(Ticket, ticket_booking=tb)
        self.client.force_login(self.staff_user)
        self.url = reverse(
            'studioadmin:ticketed_event_bookings',
            kwargs={'slug': self.ticketed_event.slug}
        )

    def formset_data(self, extra_data={}):

        data = {
            'ticket_bookings-TOTAL_FORMS': 1,
            'ticket_bookings-INITIAL_FORMS': 1,
            'ticket_bookings-0-id': self.ticket_booking.id,
            }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_cannot_access_without_login(self):
        self.client.logout()
        resp = self.client.get(self.url)
        redirected_url = reverse('account_login') + "?next={}".format(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_unless_staff_user(self):
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

        self.client.force_login(self.staff_user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_show_only_ticket_bookings_on_event(self):
        """
        confirmed bookings for other events are not shown
        """
        resp = self.client.get(self.url)
        formset = resp.context_data['ticket_booking_formset']
        self.assertEqual(
            [tb.id for tb in formset.queryset],
            [self.ticket_booking.id]
        )

    def test_does_not_show_unconfirmed_ticket_bookings(self):
        tb = baker.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            purchase_confirmed=False
        )
        baker.make(Ticket, ticket_booking=tb)

        self.assertEqual(self.ticketed_event.ticket_bookings.count(), 2)
        resp = self.client.get(self.url)
        formset = resp.context_data['ticket_booking_formset']

        # tb is not shown as not confirmed
        self.assertEqual(formset.queryset.count(), 1)
        self.assertEqual(
            [tb.id for tb in formset.queryset],
            [self.ticket_booking.id]
        )

    def test_does_not_show_ticket_bookings_with_no_tickets(self):
        tb = baker.make(TicketBooking, ticketed_event=self.ticketed_event)

        self.assertEqual(self.ticketed_event.ticket_bookings.count(), 2)
        resp = self.client.get(self.url)
        formset = resp.context_data['ticket_booking_formset']

        # tb is not shown as no tickets attached
        self.assertEqual(formset.queryset.count(), 1)
        self.assertEqual(
            [tb.id for tb in formset.queryset],
            [self.ticket_booking.id]
        )

    def test_exclude_cancelled_bookings(self):
        tb = baker.make(
             TicketBooking, ticketed_event=self.ticketed_event,
            purchase_confirmed=True, cancelled=True
        )
        baker.make(Ticket, ticket_booking=tb)
        self.assertEqual(self.ticketed_event.ticket_bookings.count(), 2)
        resp = self.client.get(self.url)
        formset = resp.context_data['ticket_booking_formset']

        # tb is not shown as cancelled
        self.assertEqual(formset.queryset.count(), 1)
        self.assertEqual(
            [tb.id for tb in formset.queryset],
            [self.ticket_booking.id]
        )

    def test_show_cancelled_if_ticked(self):
        tb = baker.make(
             TicketBooking, ticketed_event=self.ticketed_event,
            purchase_confirmed=True, cancelled=True
        )
        baker.make(Ticket, ticket_booking=tb)
        self.assertEqual(self.ticketed_event.ticket_bookings.count(), 2)
        resp = self.client.post(self.url, {'show_cancelled': True})
        formset = resp.context_data['ticket_booking_formset']

        # tb is not shown as cancelled
        self.assertEqual(formset.queryset.count(), 2)
        self.assertEqual(
            sorted([tb.id for tb in formset.queryset]),
            sorted([self.ticket_booking.id, tb.id])
        )
        self.assertTrue(resp.context_data['show_cancelled_ctx'])

    def test_side_nav_selection_in_context(self):
        resp = self.client.get(self.url)
        self.assertEqual(
            resp.context_data['sidenav_selection'], 'ticketed_evs'
        )

    def test_update_booking(self):
        self.assertFalse(self.ticket_booking.paid)
        resp = self.client.post(
            self.url, 
            self.formset_data(
                {

                    'formset_submitted': 'Save changes',
                    'ticket_bookings-0-paid': True
                }
            )
        )
        self.ticket_booking.refresh_from_db()
        self.assertTrue(self.ticket_booking.paid)

    def test_submit_form_without_changes(self):
        data = self.formset_data(
            {
                'ticket_bookings-0-paid': self.ticket_booking.paid,
                'formset_submitted': 'Save changes'
            }
        )
        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
        )
        resp = self.client.post(self.url, data, follow=True)

        self.assertIn(
            'No changes were made', format_content(resp.rendered_content)
        )


    def test_submit_form_without_changes_send_confirmation_ticked(self):
        data = self.formset_data(
            {
                'ticket_bookings-0-paid': self.ticket_booking.paid,
                'ticket_bookings-0-send_confirmation': True,
                'formset_submitted': 'Save changes'
            }
        )
        resp = self.client.post(self.url, data, follow=True)

        self.assertIn(
            "&#x27;Send confirmation&#x27; checked for &#x27;{}&#x27; but no "
            "changes were made; email has not been sent to user.".format(
                self.ticket_booking.booking_reference),
            format_content(resp.rendered_content)
        )

    def test_cancel_booking(self):
        self.assertFalse(self.ticket_booking.cancelled)
        resp = self.client.post(
            self.url, 
            self.formset_data(
                {

                    'formset_submitted': 'Save changes',
                    'ticket_bookings-0-cancel': True
                }
            )
        )
        self.ticket_booking.refresh_from_db()
        self.assertTrue(self.ticket_booking.cancelled)

    def test_reopen_booking(self):
        cancelled_tb = baker.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            purchase_confirmed=True, cancelled=True,
            user=self.user
        )
        baker.make(Ticket, ticket_booking=cancelled_tb)
        resp = self.client.post(
            self.url, 
            self.formset_data(
                {
                    'ticket_bookings-TOTAL_FORMS': 2,
                    'ticket_bookings-INITIAL_FORMS': 2,
                    'ticket_bookings-1-id': cancelled_tb.id,
                    'ticket_bookings-1-reopen': True,
                    'show_cancelled': True,
                    'formset_submitted': 'Save changes',
                }
            )

        )
        cancelled_tb.refresh_from_db()
        self.assertFalse(cancelled_tb.cancelled)

    def test_reopen_booking_not_enough_tickets_left(self):
        ticketed_event = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=timezone.now() + timedelta(2)
        )
        cancelled_tb = baker.make(
            TicketBooking, ticketed_event=ticketed_event,
            purchase_confirmed=True, cancelled=True,
            user=self.user
        )
        baker.make(Ticket, ticket_booking=cancelled_tb, _quantity=2)
        tb = baker.make(
            TicketBooking, ticketed_event=ticketed_event,
            purchase_confirmed=True,
            user=self.user
        )
        # make tickets for the event so there is only 1 left
        baker.make(
            Ticket, ticket_booking=tb, _quantity=9
        )
        self.assertEqual(ticketed_event.tickets_left(), 1)

        data = {
            'ticket_bookings-TOTAL_FORMS': 2,
            'ticket_bookings-INITIAL_FORMS': 2,
            'ticket_bookings-0-id': tb.id,
            'ticket_bookings-1-id': cancelled_tb.id,
            'ticket_bookings-1-reopen': True,
            'show_cancelled': True,
            'formset_submitted': 'Save changes',
        }
        url = reverse(
            'studioadmin:ticketed_event_bookings',
            kwargs={'slug': ticketed_event.slug}
        )
        resp = self.client.post(url, data, follow=True)
        content = format_content(resp.rendered_content)

        cancelled_tb.refresh_from_db()
        # still cancelled
        self.assertTrue(cancelled_tb.cancelled)

        self.assertIn(
            'Cannot reopen ticket booking {}; not enough tickets left for '
            'event (2 requested, 1 left)'.format(cancelled_tb.booking_reference),
            content
        )

    def test_send_confirmation_to_user_on_update(self):
        self.assertFalse(self.ticket_booking.paid)
        resp = self.client.post(
            self.url, 
            self.formset_data(
                {

                    'formset_submitted': 'Save changes',
                    'ticket_bookings-0-send_confirmation': True,
                    'ticket_bookings-0-paid': True
                }
            )
        )
        self.ticket_booking.refresh_from_db()
        self.assertTrue(self.ticket_booking.paid)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.ticket_booking.user.email])
        self.assertEqual(
            mail.outbox[0].subject,
            "{} Your ticket booking ref {} for {} has been updated".format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                self.ticket_booking.booking_reference,
                self.ticketed_event,
            )
        )

    @patch('studioadmin.views.ticketed_events.send_mail')
    def test_send_confirmation_email_errors(self, mock_send):
        mock_send.side_effect = Exception('Error sending email')
        self.assertFalse(self.ticket_booking.paid)
        resp = self.client.post(
            self.url, 
            self.formset_data(
                {

                    'formset_submitted': 'Save changes',
                    'ticket_bookings-0-send_confirmation': True,
                    'ticket_bookings-0-paid': True
                }
            )
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [settings.SUPPORT_EMAIL])
        self.assertEqual(
            mail.outbox[0].subject,
            '{} An error occurred! (ticketed_event_booking_list - send '
            'confirmation email)'.format(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX)
        )

        # no email but updates still made
        self.ticket_booking.refresh_from_db()
        self.assertTrue(self.ticket_booking.paid)

    def test_send_confirmation_to_user_on_cancel(self):
        self.assertFalse(self.ticket_booking.cancelled)
        resp = self.client.post(
            self.url, 
            self.formset_data(
                {

                    'formset_submitted': 'Save changes',
                    'ticket_bookings-0-cancel': True,
                    'ticket_bookings-0-paid': True,
                    'ticket_bookings-0-send_confirmation': True,
                }
            )
        )
        self.ticket_booking.refresh_from_db()
        self.assertTrue(self.ticket_booking.cancelled)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.ticket_booking.user.email])
        self.assertEqual(
            mail.outbox[0].subject,
            "{} Your ticket booking ref {} for {} has been cancelled".format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                self.ticket_booking.booking_reference,
                self.ticketed_event,
            )
        )

    def test_send_confirmation_to_user_on_reopen(self):
        cancelled_tb = baker.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            purchase_confirmed=True, cancelled=True,
            user=self.user
        )
        baker.make(Ticket, ticket_booking=cancelled_tb)
        resp = self.client.post(
            self.url, 
            self.formset_data(
                {
                    'ticket_bookings-TOTAL_FORMS': 2,
                    'ticket_bookings-INITIAL_FORMS': 2,
                    'ticket_bookings-1-id': cancelled_tb.id,
                    'ticket_bookings-1-reopen': True,
                    'ticket_bookings-1-send_confirmation': True,
                    'show_cancelled': True,
                    'formset_submitted': 'Save changes',
                }
            )
        )
        cancelled_tb.refresh_from_db()
        self.assertFalse(cancelled_tb.cancelled)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.ticket_booking.user.email])
        self.assertEqual(
            mail.outbox[0].subject,
            "{} Your ticket booking ref {} for {} has been reopened".format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                cancelled_tb.booking_reference,
                self.ticketed_event,
            )
        )


class CancelTicketedEventTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(CancelTicketedEventTests, self).setUp()
        self.ticketed_event_with_booking = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=timezone.now() + timedelta(2)
        )
        self.ticket_booking = baker.make(
            TicketBooking, ticketed_event=self.ticketed_event_with_booking,
            purchase_confirmed=True, user=self.user
        )
        baker.make(Ticket, ticket_booking=self.ticket_booking)

        self.ticketed_event_without_booking = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=timezone.now() + timedelta(2)
        )
        self.url_with_booking = reverse(
            'studioadmin:cancel_ticketed_event',
            kwargs={'slug': self.ticketed_event_with_booking.slug}
        )
        self.url_without_booking = reverse(
            'studioadmin:cancel_ticketed_event',
            kwargs={'slug': self.ticketed_event_without_booking.slug}
        )

        self.client.force_login(self.staff_user)

    def test_cannot_access_without_login(self):
        self.client.logout()
        resp = self.client.get(self.url_with_booking)
        redirected_url = reverse('account_login') + "?next={}".format(self.url_with_booking)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_unless_staff_user(self):
        self.client.force_login(self.user)
        resp = self.client.get(self.url_with_booking)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

        self.client.force_login(self.staff_user)
        resp = self.client.get(self.url_with_booking)
        self.assertEqual(resp.status_code, 200)

    def test_get_cancel_page_with_no_bookings(self):
        # no bookings displayed on page
        resp = self.client.get(self.url_without_booking)
        self.assertEqual(resp.context_data['open_paid_ticket_bookings'], [])
        self.assertEqual(resp.context_data['open_unpaid_ticket_bookings'], [])

    def test_get_cancel_page_with_cancelled_bookings_only(self):
        # no open bookings displayed on page
        ticketed_event_with_booking = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=timezone.now() + timedelta(2)
        )
        baker.make(
            TicketBooking, ticketed_event=self.ticketed_event_with_booking,
            purchase_confirmed=True, cancelled=True
        )
        baker.make(
            TicketBooking, ticketed_event=self.ticketed_event_with_booking,
            purchase_confirmed=True, cancelled=True, paid=True
        )
        for tb in TicketBooking.objects.all():
            baker.make(Ticket, ticket_booking=tb)

        resp = self.client.get(self.url_without_booking)
        self.assertEqual(resp.context_data['open_paid_ticket_bookings'], [])
        self.assertEqual(resp.context_data['open_unpaid_ticket_bookings'], [])

    def test_get_cancel_page_open_unpaid_bookings(self):
        # open bookings displayed on page, not in due_refunds list
        self.assertFalse(self.ticket_booking.paid)
        resp = self.client.get(self.url_with_booking)
        self.assertEqual(resp.context_data['open_paid_ticket_bookings'], [])
        self.assertEqual(
            resp.context_data['open_unpaid_ticket_bookings'],
            [self.ticket_booking]
        )

    def test_get_cancel_page_open_paid_bookings(self):
        self.ticket_booking.paid = True
        self.ticket_booking.save()
        resp = self.client.get(self.url_with_booking)
        self.assertEqual(
            resp.context_data['open_paid_ticket_bookings'],
            [self.ticket_booking]
        )
        self.assertEqual(
            resp.context_data['open_unpaid_ticket_bookings'],
            []
        )

    def test_get_cancel_page_multiple_bookings(self):
        # multiple bookings, cancelled not displayed at all; all open displayed
        # in open_bookings list, only paid displayed in due_refunds list

        # self.ticket_booking is unpaid, confirmed, open
        paid_tb = baker.make(
            TicketBooking, ticketed_event=self.ticketed_event_with_booking,
            purchase_confirmed=True, user=self.user, paid=True
        )
        cancelled_tb = baker.make(
                TicketBooking, ticketed_event=self.ticketed_event_with_booking,
            purchase_confirmed=True, user=self.user, paid=True,
            cancelled=True,
        )
        unconfirmed = baker.make(
            TicketBooking, ticketed_event=self.ticketed_event_with_booking,
            purchase_confirmed=False, user=self.user
        )
        for tb in TicketBooking.objects.all():
            baker.make(Ticket, ticket_booking=tb)

        resp = self.client.get(self.url_with_booking)
        self.assertEqual(
            resp.context_data['open_paid_ticket_bookings'],
            [paid_tb]
        )

        self.assertEqual(
            resp.context_data['open_unpaid_ticket_bookings'],
            [self.ticket_booking]
        )

    def test_cancelled_event_sets_attributes(self):
        """
        sets show_on_site, payment_open to False, cancelled to True
        """
        self.assertTrue(self.ticketed_event_with_booking.show_on_site)
        self.assertTrue(self.ticketed_event_with_booking.payment_open)
        self.assertFalse(self.ticketed_event_with_booking.cancelled)

        self.client.post(self.url_with_booking, {'confirm': 'Yes, cancel this event'})
        self.ticketed_event_with_booking.refresh_from_db()
        self.assertFalse(self.ticketed_event_with_booking.show_on_site)
        self.assertFalse(self.ticketed_event_with_booking.payment_open)
        self.assertTrue(self.ticketed_event_with_booking.cancelled)

    def test_all_bookings_on_event_cancelled(self):

        # make some more paid and unpaid bookings (3 unpaid incl
        # self.ticket_booking)
        baker.make(
            TicketBooking,
            ticketed_event=self.ticketed_event_with_booking,
            purchase_confirmed=True,
            paid=False,
            _quantity=2
        )
        baker.make(
            TicketBooking,
            ticketed_event=self.ticketed_event_with_booking,
            purchase_confirmed=True,
            paid=True,
            _quantity=2
        )
        for tb in TicketBooking.objects.all():
            baker.make(Ticket, ticket_booking=tb)

        self.assertEqual(
            TicketBooking.objects.filter(
                cancelled=False,
                ticketed_event=self.ticketed_event_with_booking
            ).count(), 5
        )
        self.client.post(self.url_with_booking, {'confirm': 'Yes, cancel this event'})
        self.ticketed_event_with_booking.refresh_from_db()
        self.assertEqual(
            TicketBooking.objects.filter(
                cancelled=True,
                ticketed_event=self.ticketed_event_with_booking
            ).count(), 5
        )
        # no open bookings on event any more
        self.assertEqual(
            TicketBooking.objects.filter(
                cancelled=False,
                ticketed_event=self.ticketed_event_with_booking
            ).count(), 0
        )

        # paid bookings are still marked paid
        self.assertEqual(
            TicketBooking.objects.filter(
                cancelled=True,
                ticketed_event=self.ticketed_event_with_booking,
                paid=True,
            ).count(), 2
        )

    def test_unconfirmed_bookings_cancelled(self):
        baker.make(
            TicketBooking,
            ticketed_event=self.ticketed_event_with_booking,
            purchase_confirmed=False,
        )
        self.assertEqual(
            self.ticketed_event_with_booking.ticket_bookings.count(), 2
        )
        self.client.post(self.url_with_booking, {'confirm': 'Yes, cancel this event'})

        self.ticketed_event_with_booking.refresh_from_db()
        self.ticket_booking.refresh_from_db()
        self.assertEqual(
            self.ticketed_event_with_booking.ticket_bookings.count(), 1
        )
        self.assertTrue(self.ticket_booking.cancelled)

    def test_emails_sent_to_all_users_for_open_bookings(self):
        # 1 paid, 1 unpaid booking
        baker.make(
            TicketBooking,
            ticketed_event=self.ticketed_event_with_booking,
            purchase_confirmed=True,
            paid=True
        )
        for tb in TicketBooking.objects.all():
            baker.make(Ticket, ticket_booking=tb)
        _add_user_email_addresses(TicketBooking)
        self.client.post(self.url_with_booking, {'confirm': 'Yes, cancel this event'})
        

        # send 1 email per booking, plus 1 to studio if there are open paid bkgs
        self.assertEqual(len(mail.outbox), 3)

    @patch('studioadmin.views.ticketed_events.send_mail')
    def test_send_email_errors(self, mock_send):
        mock_send.side_effect = Exception('Error sending email')
        baker.make(
            TicketBooking,
            ticketed_event=self.ticketed_event_with_booking,
            purchase_confirmed=True,
            paid=True
        )
        for tb in TicketBooking.objects.all():
            baker.make(Ticket, ticket_booking=tb)

        self.client.post(self.url_with_booking, {'confirm': 'Yes, cancel this event'})

        # send 1 email per booking, plus 1 to studio if there are open paid bkgs
        # 3 error emails
        self.assertEqual(len(mail.outbox), 3)
        for email in mail.outbox:
            self.assertEqual(email.to, [settings.SUPPORT_EMAIL])
        self.assertEqual(
            mail.outbox[0].subject,
            '{} An error occurred! (cancel ticketed event - send notification '
            'email to user)'.format(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX)
        )
        self.assertEqual(
            mail.outbox[2].subject,
            '{} An error occurred! (cancel ticketed event - send refund '
            'notification email to studio)'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
            )
        )

    def test_emails_not_sent_to_users_for_cancelled_bookings(self):
        # 1 paid, 1 unpaid booking
        baker.make(
            TicketBooking,
            ticketed_event=self.ticketed_event_with_booking,
            purchase_confirmed=True,
            paid=True,
            cancelled=True
        )
        for tb in TicketBooking.objects.all():
            baker.make(Ticket, ticket_booking=tb)

        self.client.post(self.url_with_booking, {'confirm': 'Yes, cancel this event'})

        # send 1 email per open booking(1); no email to studio as
        # self.ticket_booking is unpaid
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.ticket_booking.user.email])

    def test_emails_not_sent_to_users_for_unconfirmed_bookings(self):
        # 1 paid, 1 unpaid booking
        baker.make(
            TicketBooking,
            ticketed_event=self.ticketed_event_with_booking,
            purchase_confirmed=False,
            paid=True,
        )

        self.client.post(self.url_with_booking, {'confirm': 'Yes, cancel this event'})

        # send 1 email per confirmed booking(1); no email to studio as
        # self.ticket_booking is unpaid
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.ticket_booking.user.email])

    def test_email_only_sent_to_studio_for_open_bookings(self):
        self.ticket_booking.paid = True
        self.ticket_booking.save()

        self.client.post(self.url_with_booking, {'confirm': 'Yes, cancel this event'})
    
        # send 1 email per confirmed booking(1); 1 email to studio as
        # self.ticket_booking is paid
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, [self.ticket_booking.user.email])
        self.assertEqual(mail.outbox[1].to, [settings.DEFAULT_STUDIO_EMAIL])

        studio_email_content = mail.outbox[1].body
        self.assertIn(
            reverse(
                'studioadmin:confirm_ticket_booking_refund',
                args=[self.ticket_booking.id]
            )[:-1],  # remove trailing slash for the test
            studio_email_content
        )

    def test_can_abort_cancel_event_request(self):
        self.client.post(self.url_with_booking, {'cancel': 'No, take me back'})
        self.ticketed_event_with_booking.refresh_from_db()
        self.assertFalse(self.ticketed_event_with_booking.cancelled)
        for tb in self.ticketed_event_with_booking.ticket_bookings.all():
            self.assertFalse(tb.cancelled)


class ConfirmTicketBookingRefundViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(ConfirmTicketBookingRefundViewTests, self).setUp()
        self.ticketed_event = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=timezone.now() + timedelta(2)
        )
        self.ticket_booking = baker.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            purchase_confirmed=True, paid=True, user=self.user,
            cancelled=True
        )
        baker.make(Ticket, ticket_booking=self.ticket_booking)
        self.client.force_login(self.staff_user)
        self.url = reverse(
            'studioadmin:confirm_ticket_booking_refund',
            args=[self.ticket_booking.id]
        )

    def test_cannot_access_without_login(self):
        self.client.logout()
        resp = self.client.get(self.url)
        redirected_url = reverse('account_login') + "?next={}".format(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_unless_staff_user(self):
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

        self.client.force_login(self.staff_user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)


    def test_shows_already_confirmed_msg_for_already_refunded(self):
        self.ticket_booking.paid = False
        self.ticket_booking.save()
        resp = self.client.get(self.url)
        self.assertIn(
            'This ticket booking is unpaid or payment has already been '
            'refunded.',
            resp.rendered_content
        )

    def test_confirm_refund_for_paid_booking(self):
        self.assertTrue(self.ticket_booking.paid)
        self.client.post(self.url, {'confirmed': True})
        self.ticket_booking.refresh_from_db()
        self.assertFalse(self.ticket_booking.paid)

    def test_email_sent_to_user(self):
        self.assertTrue(self.ticket_booking.paid)
        self.client.post(self.url, {'confirmed': True})
        self.assertEqual(len(mail.outbox), 1)

    def test_cancel_confirm_form(self):
        self.assertTrue(self.ticket_booking.paid)
        self.client.post(self.url, {'cancelled': True})
        self.ticket_booking.refresh_from_db()
        self.assertTrue(self.ticket_booking.paid)
        self.assertEqual(len(mail.outbox), 0)


class PrintTicketsTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(PrintTicketsTests, self).setUp()

        self.ticketed_event = baker.make_recipe(
            'booking.ticketed_event_max10',
            date=timezone.now() + timedelta(2),
            extra_ticket_info_label="Extra info 1",
            extra_ticket_info1_label="Extra info 2"
        )

        # create bookings that will be in reverse order depending on whether
        # ordered by user name or date
        for i in range(5):
            baker.make(
                TicketBooking, ticketed_event=self.ticketed_event,
                purchase_confirmed=True,
                user=baker.make_recipe(
                    'booking.user', first_name='User_{}'.format(i)
                ),
                date_booked=timezone.now() + timedelta(10-i)
            )
        # create tickets with extra ticket info that will be orderd in opp dirns
        for i, tb in enumerate(TicketBooking.objects.all()):
            baker.make(
                Ticket, ticket_booking=tb,
                extra_ticket_info="Extra provided info1_{}".format(
                    tb.user.first_name
                ),
                extra_ticket_info1="Extra provided info2_{}{}".format(
                    10 - i, tb.user.first_name
                ),
            )
        self.client.force_login(self.staff_user)
        self.url = reverse('studioadmin:print_tickets_list')

    def test_cannot_access_without_login(self):
        self.client.logout()
        resp = self.client.get(self.url)
        redirected_url = reverse('account_login') + "?next={}".format(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_unless_staff_user(self):
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

        self.client.force_login(self.staff_user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_selecting_event_shows_its_extra_info_fields(self):
        """
        Selecting/changing the event dropdown posts the form with
        "ticketed_event" and updates the order_field and show_fields with the
         event's extra_ticket_info if available
        """
        resp = self.client.get(self.url)
        self.assertEqual(
            resp.context_data['form'].fields['show_fields'].widget.choices,
            [
                ('show_booking_user', 'User who made the booking'),
                ('show_date_booked', 'Date booked'),
                ('show_booking_reference', 'Booking reference'),
                ('show_paid', 'Paid status')
            ]
        )

        resp = self.client.post(
            self.url, 
            {
                'ticketed_event': self.ticketed_event.id,
                'show_fields': ['show_booking_user', 'show_date_booked',
                'show_booking_reference'],
                'order_field': 'ticket_booking__user__first_name'
            }
        )
        self.assertEqual(
            resp.context_data['form'].fields['show_fields'].widget.choices,
            [
                ('show_booking_user', 'User who made the booking'),
                ('show_date_booked', 'Date booked'),
                ('show_booking_reference', 'Booking reference'),
                ('show_paid', 'Paid status'),
                ('show_extra_ticket_info', 'Extra info 1 (extra requested ticket info)'),
                ('show_extra_ticket_info1', 'Extra info 2 (extra requested ticket info)')
            ]
        )

    def test_side_nav_selection_in_context(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.context_data['sidenav_selection'], 'print_tickets_list'
        )

    def test_print_event_ticket_list(self):
        post_resp = self.client.post(
            self.url,
            {
                'ticketed_event': self.ticketed_event.id,
                'show_fields': ['show_booking_user', 'show_date_booked',
                'show_booking_reference'],
                'order_field': 'ticket_booking__user__first_name',
                'print': 'View and Print Ticket List'
            }
        )

        self.assertEqual(post_resp.status_code, 200)
        # tickets are in context
        self.assertEqual(
            sorted([tkt.id for tkt in post_resp.context_data['tickets']]),
            sorted([tkt.id for tkt in Ticket.objects.all()])
        )

    def test_print_event_ticket_list_with_no_open_bookings(self):
        for i, tb in enumerate(TicketBooking.objects.all()):
            if i in range(3):
                tb.cancelled = True
                tb.save()
            else:
                tb.purchase_confirmed = False
                tb.save()

        post_resp = self.client.post(
            self.url,
            {
                'ticketed_event': self.ticketed_event.id,
                'show_fields': ['show_booking_user', 'show_date_booked',
                'show_booking_reference'],
                'order_field': 'ticket_booking__user__first_name',
                'print': 'View and Print Ticket List'
            }
        )
        self.assertEqual(post_resp.status_code, 200)
        # tickets are in context
        self.assertIn(
            'There are no open ticket bookings for the event selected',
            format_content(post_resp.rendered_content)
        )

    def test_print_event_ticket_list_with_form_errors(self):
        post_resp = self.client.post(
            self.url,
            {
                'ticketed_event': self.ticketed_event.id,
                'show_fields': ['user'],
                'order_field': 'ticket_booking__user__first_name',
                'print': 'View and Print Ticket List'
            }
        )

        self.assertEqual(post_resp.status_code, 200)
        self.assertIn(
            'Please correct the following errors: show_fieldsSelect a valid '
            'choice. user is not one of the available choices',
            format_content(post_resp.rendered_content),
            format_content(post_resp.rendered_content)
        )

    def test_print_list_only_shows_confirmed_and_open_tickets(self):
        tb1 = baker.make(
            TicketBooking,
            ticketed_event=self.ticketed_event,
            purchase_confirmed=False
        )
        tb2 = baker.make(
            TicketBooking,
            ticketed_event=self.ticketed_event,
            purchase_confirmed=True,
            cancelled=True
        )
        for tb in [tb1, tb2]:
            baker.make(
                Ticket, ticket_booking=tb,
            )

        post_resp = self.client.post(
            self.url, 
            {
                'ticketed_event': self.ticketed_event.id,
                'show_fields': ['show_booking_user', 'show_date_booked',
                'show_booking_reference'],
                'order_field': 'ticket_booking__user__first_name',
                'print': 'View and Print Ticket List'
            }
        )

        self.assertEqual(
            len(post_resp.context_data['tickets']),
            Ticket.objects.filter(
                ticket_booking__ticketed_event=self.ticketed_event
            ).count() - 2
        )

        open_and_confirmed = Ticket.objects.filter(
            ticket_booking__ticketed_event=self.ticketed_event,
            ticket_booking__purchase_confirmed=True,
            ticket_booking__cancelled=False
        )
        # tickets are in context
        self.assertEqual(
            sorted([tkt.id for tkt in post_resp.context_data['tickets']]),
            sorted([tkt.id for tkt in open_and_confirmed])
        )

    def test_print_event_ticket_list_shows_only_selected_fields(self):
        post_resp = self.client.post(
            self.url, 
            {
                'ticketed_event': self.ticketed_event.id,
                'show_fields': ['show_booking_reference'],
                'order_field': 'ticket_booking__user__first_name',
                'print': 'View and Print Ticket List'
            }
        )

        # tickets are in context
        self.assertEqual(
            post_resp.context_data['show_fields'], ['show_booking_reference']
        )
        for tck in Ticket.objects.all():
            self.assertIn(
                tck.ticket_booking.booking_reference,
                post_resp.rendered_content
            )
            self.assertNotIn(
                tck.ticket_booking.user.first_name,
                post_resp.rendered_content
            )

        self.assertNotIn("Extra provided info", post_resp.rendered_content)

        post_resp = self.client.post(
            self.url, 
            {
                'ticketed_event': self.ticketed_event.id,
                'show_fields': [
                    'show_extra_ticket_info', 'show_extra_ticket_info1'
                ],
                'order_field': 'ticket_booking__user__first_name',
                'print': 'View and Print Ticket List'
            }
        )
        for tck in Ticket.objects.all():
            self.assertIn(
                tck.extra_ticket_info,
                post_resp.rendered_content
            )
            self.assertIn(
                tck.extra_ticket_info1,
                post_resp.rendered_content
            )

    def test_order_tickets_by_date_booked(self):
        post_resp = self.client.post(
            self.url,
            {
                'ticketed_event': self.ticketed_event.id,
                'show_fields': ['show_booking_reference'],
                'order_field': 'ticket_booking__date_booked',
                'print': 'View and Print Ticket List'
            }
        )

        ordered_tickets = Ticket.objects.all().order_by(
            'ticket_booking__date_booked'
        )
        self.assertEqual(
            [tck.id for tck in post_resp.context_data['tickets']],
            [tck.id for tck in ordered_tickets]
        )

    def test_order_tickets_by_booking_user_first_name(self):
        post_resp = self.client.post(
            self.url,
            {
                'ticketed_event': self.ticketed_event.id,
                'show_fields': ['show_booking_reference'],
                'order_field': 'ticket_booking__user__first_name',
                'print': 'View and Print Ticket List'
            }
        )

        ordered_tickets = Ticket.objects.all().order_by(
            'ticket_booking__user__first_name'
        )
        self.assertEqual(
            [tck.id for tck in post_resp.context_data['tickets']],
            [tck.id for tck in ordered_tickets]
        )

    def test_order_tickets_by_booking_reference(self):
        post_resp = self.client.post(
            self.url,
            {
                'ticketed_event': self.ticketed_event.id,
                'show_fields': ['show_booking_reference'],
                'order_field': 'ticket_booking__booking_reference',
                'print': 'View and Print Ticket List'
            }
        )

        ordered_tickets = Ticket.objects.all().order_by(
            'ticket_booking__booking_reference'
        )
        self.assertEqual(
            [tck.id for tck in post_resp.context_data['tickets']],
            [tck.id for tck in ordered_tickets]
        )

    def test_order_tickets_by_extra_info_fields(self):
        post_resp = self.client.post(
            self.url,
            {
                'ticketed_event': self.ticketed_event.id,
                'show_fields': ['show_booking_reference'],
                'order_field': 'extra_ticket_info',
                'print': 'View and Print Ticket List'
            }
        )

        ordered_tickets = Ticket.objects.all().order_by('extra_ticket_info')
        self.assertEqual(
            [tck.id for tck in post_resp.context_data['tickets']],
            [tck.id for tck in ordered_tickets]
        )

        post_resp = self.client.post(
            self.url,
            {
                'ticketed_event': self.ticketed_event.id,
                'show_fields': ['show_booking_reference'],
                'order_field': 'extra_ticket_info1',
                'print': 'View and Print Ticket List'
            }
        )

        ordered_tickets = Ticket.objects.all().order_by('extra_ticket_info1')
        self.assertEqual(
            [tck.id for tck in post_resp.context_data['tickets']],
            [tck.id for tck in ordered_tickets]
        )
