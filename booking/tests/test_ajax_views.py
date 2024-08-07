# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from unittest.mock import patch
from model_bakery import baker

import pytest

from django.conf import settings
from django.core import mail
from django.urls import reverse
from django.test import override_settings, TestCase
from django.contrib.auth.models import Group, User
from django.contrib.sites.models import Site
from django.contrib.sessions.middleware import SessionMiddleware
from django.utils import timezone

from accounts.models import DisclaimerContent, OnlineDisclaimer, AccountBan

from booking.models import Event, EventType, Booking, Block, WaitingListUser, MembershipItem, Membership, UserMembership
from booking.views.shopping_basket_views import shopping_basket_bookings_total_context, \
    shopping_basket_blocks_total_context
from common.tests.helpers import TestSetupMixin, make_data_privacy_agreement

from stripe_payments.models import Seller
from stripe_payments.tests.mock_connector import MockConnector


class BookingAjaxCreateViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.pole_class_event_type = baker.make(
            EventType, event_type='CL', subtype='Pole level class'
        )
        cls.event = baker.make_recipe('booking.future_EV', cost=5, max_participants=3)
        cls.event_url = reverse('booking:ajax_create_booking', args=[cls.event.id]) + "?ref=events"
        cls.free_blocktype = baker.make_recipe(
            'booking.blocktype', size=1, cost=0,
            event_type=cls.pole_class_event_type, identifier='free class'
        )
        cls.group, _ = Group.objects.get_or_create(name='subscribed')
        cls.tutorial = baker.make_recipe('booking.future_OT', cost=5, max_participants=3)
        cls.tutorial_url = reverse('booking:ajax_create_booking', args=[cls.tutorial.id]) + "?ref=events"
        baker.make(Seller, site=Site.objects.get_current())

    def _mock_new_user_email_sent(self):
        session = self.client.session
        session["new_user_email_sent"] = True
        session.save()

    def setUp(self):
        super().setUp()
        self.user_no_disclaimer = User.objects.create_user(username='no_disclaimer', password='test')
        make_data_privacy_agreement(self.user_no_disclaimer)

    def test_cannot_access_if_no_disclaimer(self):
        self.client.login(username=self.user_no_disclaimer.username, password='test')
        resp = self.client.post(self.event_url)

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:disclaimer_required'))

        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(self.event_url)
        self.assertEqual(resp.status_code, 200)

    def test_cannot_access_if_expired_disclaimer(self):
        user = User.objects.create_user(username='exp_disclaimer', password='test')
        make_data_privacy_agreement(user)
        disclaimer = baker.make_recipe(
           'booking.online_disclaimer', user=user,
            date=datetime(2015, 2, 1, tzinfo=dt_timezone.utc),
            version = DisclaimerContent.current_version()
        )
        self.assertFalse(disclaimer.is_active)

        self.client.login(username=user.username, password='test')
        resp = self.client.post(self.event_url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:disclaimer_required'))

        baker.make(OnlineDisclaimer, user=user, version=DisclaimerContent.current_version())
        resp = self.client.post(self.event_url)
        self.assertEqual(resp.status_code, 200)

    def test_create_booking(self):
        """
        Test creating a booking
        """
        assert Booking.objects.count() == 0
        self.client.login(username=self.user.username, password='test')
        self._mock_new_user_email_sent()
        resp = self.client.post(self.event_url)
        assert Booking.objects.count() == 1
        msg = 'Added to basket; booking not confirmed until payment has been made.'
        assert resp.context['alert_message']['message'] == msg, resp.context['alert_message'] 
        assert not Booking.objects.first().paid
        assert Booking.objects.first().event == self.event
        # unpaid, no email yet
        assert len(mail.outbox) == 0

    def test_create_tutorial_booking(self):
        """
        Test creating a tutorial booking
        """
        assert Booking.objects.count() == 0
        self.client.login(username=self.user.username, password='test')
        self._mock_new_user_email_sent()
        resp = self.client.post(self.tutorial_url)
        assert Booking.objects.count() == 1
        msg = 'Added to basket; online tutorial not available until payment has been made.'
        assert resp.context['alert_message']['message'] == msg
        assert not Booking.objects.first().paid
        assert Booking.objects.first().event == self.tutorial
        # no emails for tutorials
        assert len(mail.outbox) == 0

    def test_create_booking_new_user(self):
        """
        Test creating a booking for a new user sends new user email
        """
        self.client.login(username=self.user.username, password='test')
        self.client.post(self.event_url)
        assert Booking.objects.all().count() == 1

        # emails for booking and new user
        assert len(mail.outbox) == 1
        prefix = settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
        assert mail.outbox[0].subject == f"{prefix} Important studio information - please read!"

        assert self.client.session.get("new_user_email_sent")

        # Making another booking in the same session doesn't send new user email again
        event = baker.make_recipe('booking.future_EV', cost=5)
        event_url = reverse('booking:ajax_create_booking', args=[event.id])
        self.client.post(event_url)
        assert Booking.objects.all().count() == 2
        # no new email (booking isn't paid)
        assert len(mail.outbox) == 1

        # But in a new session, it will be sent
        self.client.logout()
        self.client.login(username=self.user.username, password="test")
        event1 = baker.make_recipe('booking.future_EV', cost=5)
        event1_url = reverse('booking:ajax_create_booking', args=[event1.id])
        self.client.post(event1_url)
        assert Booking.objects.all().count() == 3
        assert len(mail.outbox) == 2
        assert mail.outbox[1].subject == f"{prefix} Important studio information - please read!"

        # If one of the bookings is now paid, no new user email is sent
        booking = Booking.objects.first()
        booking.paid = True
        booking.save()

        self.client.logout()
        self.client.login(username=self.user.username, password="test")
        event2 = baker.make_recipe('booking.future_EV', cost=5)
        event2_url = reverse('booking:ajax_create_booking', args=[event2.id])
        self.client.post(event2_url)
        assert Booking.objects.all().count() == 4
        assert len(mail.outbox) == 2

    def test_create_booking_free_event(self):
        """
        Test creating a booking
        """
        event = baker.make_recipe('booking.future_EV', cost=0, max_participants=3)
        url = reverse('booking:ajax_create_booking', args=[event.id]) + "?ref=events"
        self.assertEqual(Booking.objects.all().count(), 0)
        self.client.login(username=self.user.username, password='test')
        self._mock_new_user_email_sent()

        resp = self.client.post(url)
        self.assertEqual(Booking.objects.all().count(), 1)
        self.assertEqual(
            resp.context['alert_message']['message'],
            'Booked.'
        )
        self.assertTrue(Booking.objects.first().paid)

        # email to student only
        self.assertEqual(len(mail.outbox), 1)

    def test_create_booking_already_booked(self):
        """
        Test creating a booking
        """
        self.client.login(username=self.user.username, password='test')
        event = baker.make_recipe('booking.future_EV', cost=0, max_participants=3)
        baker.make_recipe('booking.booking', user=self.user, event=event, status="OPEN", no_show=False)
        
        url = reverse('booking:ajax_create_booking', args=[event.id]) + "?ref=bookings"
        
        assert Booking.objects.count() == 1
        self._mock_new_user_email_sent()

        resp = self.client.post(url)
        assert resp.status_code == 200
        assert Booking.objects.count() == 1
        assert 'alert_message' not in resp.context
        assert len(mail.outbox) == 0

    def test_create_booking_sends_email_to_studio_if_set(self):
        """
        Test creating a booking send email to user and studio if flag sent on
        event
        """
        event = baker.make_recipe(
            'booking.future_EV', cost=5, max_participants=3,
            email_studio_when_booked=True
        )
        url = reverse('booking:ajax_create_booking', args=[event.id]) + "?ref=events"
        self.assertEqual(Booking.objects.all().count(), 0)
        self.client.login(username=self.user.username, password='test')
        self._mock_new_user_email_sent()

        self.client.post(url)
        self.assertEqual(Booking.objects.all().count(), 1)
        # unpaid booking, email to studio only
        self.assertEqual(len(mail.outbox), 1)
        assert "has just booked for" in mail.outbox[0].subject

    @override_settings(WATCHLIST=['foo@test.com', 'bar@test.com'])
    def test_create_booking_sends_email_to_studio_for_users_on_watchlist(self):
        self.client.login(username=self.user.username, password='test')
        self._mock_new_user_email_sent()
        self.client.post(self.event_url)
        self.assertEqual(Booking.objects.count(), 1)
        # unpaid booking, no email
        self.assertEqual(len(mail.outbox), 0)

        # create watched user and book
        watched_user = User.objects.create_user(
            username='foo', email='foo@test.com', password='test'
        )
        baker.make(OnlineDisclaimer, user=watched_user, version=DisclaimerContent.current_version())
        make_data_privacy_agreement(watched_user)
        self.client.login(username=watched_user.username, password='test')
        self._mock_new_user_email_sent()

        self.client.post(self.event_url)
        self.assertEqual(Booking.objects.count(), 2)
        # email to studio studio
        self.assertEqual(len(mail.outbox), 1)

    def test_create_room_hire(self):
        """
        Test creating a room hire booking
        """
        room_hire = baker.make_recipe('booking.future_RH', max_participants=3, cost=5)
        url = reverse('booking:ajax_create_booking', args=[room_hire.id]) + "?ref=events"
        self.assertEqual(Booking.objects.all().count(), 0)
        self.client.login(username=self.user.username, password='test')
        self._mock_new_user_email_sent()

        resp = self.client.post(url)
        self.assertEqual(Booking.objects.all().count(), 1)
        self.assertEqual(
            resp.context['alert_message']['message'],
            'Added to basket; booking not confirmed until payment has been made.'
        )

    def test_cannot_make_duplicate_booking(self):
        """
        Test trying to create duplicate booking returns 200 and existing booking
        """
        booking = baker.make_recipe('booking.booking', user=self.user, event=self.event)

        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(self.event_url)
        self.assertEqual(resp.status_code, 200)
        assert resp.context['booking'] == booking

    def test_cannot_book_for_full_event(self):
        """
        Test trying create booking for a full event returns 400
        """
        users = baker.make_recipe('booking.user', _quantity=3)
        for user in users:
            baker.make_recipe('booking.booking', event=self.event, user=user)
        # check event is full; we need to get the event again as spaces_left is
        # cached property
        event = Event.objects.get(id=self.event.id)
        self.assertEqual(event.spaces_left, 0)

        self.client.login(username=self.user.username, password='test')
        # try to book for event
        resp = self.client.post(self.event_url)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.content.decode('utf-8'), 'Sorry, this event is now full')

    def test_cannot_book_for_cancelled_event(self):
        """cannot create booking for a full event
        """
        event = baker.make_recipe('booking.future_EV', max_participants=3, cancelled=True, cost=5)
        url = reverse('booking:ajax_create_booking', args=[event.id]) + "?ref=events"

        self.client.login(username=self.user.username, password='test')
        # try to book for event
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.content.decode('utf-8'), 'Sorry, this event has been cancelled')

    def test_cancelled_booking_can_be_rebooked(self):
        """
        Test can load create booking page with a cancelled booking
        """
        booking = baker.make_recipe(
            'booking.booking', event=self.event, user=self.user, status='CANCELLED'
        )

        self.client.login(username=self.user.username, password='test')
        # try to book again
        resp = self.client.post(self.event_url)

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'OPEN')
        self.assertIsNotNone(booking.date_rebooked)

        self.assertEqual(
            resp.context['alert_message']['message'],
            'Added to basket; booking not confirmed until payment has been made.'
        )

    def test_rebook_no_show_booking(self):
        """
        Test can rebook a booking marked as no_show
        """
        pclass = baker.make_recipe(
            'booking.future_PC', allow_booking_cancellation=False, cost=10
        )
        url = reverse('booking:ajax_create_booking', args=[pclass.id]) + "?ref=events"

        # book for non-refundable event and mark as no_show
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=pclass, paid=True,
            no_show=True
        )
        self.assertIsNone(booking.date_rebooked)

        # try to book again
        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(url)
        booking.refresh_from_db()
        self.assertEqual('OPEN', booking.status)
        self.assertFalse(booking.no_show)
        self.assertIsNotNone(booking.date_rebooked)
        self.assertEqual(
            resp.context['alert_message']['message'],
            'You previously paid for this booking and your booking has been reopened.'
        )

        # emails sent to student
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ['test@test.com'])

    def test_rebook_no_show_block_booking(self):
        """
        Test can rebook a block booking marked as no_show
        """

        pclass = baker.make_recipe(
            'booking.future_PC', allow_booking_cancellation=False, cost=10
        )
        block = baker.make_recipe(
            'booking.block', user=self.user, paid=True,
            block_type__event_type =pclass.event_type
        )
        # book for non-refundable event and mark as no_show
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=pclass, paid=True,
            no_show=True, block=block
        )

        url = reverse('booking:ajax_create_booking', args=[pclass.id]) + "?ref=events"
        self.assertIsNone(booking.date_rebooked)

        # try to book again
        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(url)
        booking.refresh_from_db()
        self.assertEqual('OPEN', booking.status)
        self.assertFalse(booking.no_show)
        self.assertIsNotNone(booking.date_rebooked)
        self.assertEqual(
            resp.context['alert_message']['message'],
            'You previously paid for this booking with a block and your '
            'booking has been reopened.'
        )

        # emails sent to student
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ['test@test.com'])

    def test_rebook_cancelled_paid_booking(self):

        """
        Test rebooking a cancelled booking still marked as paid reopens booking
        and emails studio
        """
        booking = baker.make_recipe(
            'booking.booking', event=self.event, user=self.user, paid=True,
            payment_confirmed=True, status='CANCELLED'
        )

        # try to book again
        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(self.event_url)
        booking.refresh_from_db()
        self.assertEqual('OPEN', booking.status)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)

        self.assertEqual(
            resp.context['alert_message']['message'],
            'You previously paid for this booking; your booking will remain as '
            'pending until the organiser has reviewed your payment status.'

        )

        # email to user and to studio
        self.assertEqual(len(mail.outbox), 2)
        mail_to_user = mail.outbox[0]
        mail_to_studio = mail.outbox[1]

        self.assertEqual(mail_to_user.to, [self.user.email])
        self.assertEqual(mail_to_studio.to, [settings.DEFAULT_STUDIO_EMAIL])

    def test_rebook_from_bookings(self):

        """
        Test rebooking a cancelled booking still marked as paid reopens booking
        and emails studio
        """
        booking = baker.make_recipe(
            'booking.booking', event=self.event, user=self.user, paid=True,
            payment_confirmed=True, status='CANCELLED'
        )

        # try to book again
        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(reverse('booking:ajax_create_booking', args=[self.event.id]) + "?ref=bookings")
        booking.refresh_from_db()
        self.assertEqual('OPEN', booking.status)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)

        self.assertEqual(
            resp.context['alert_message']['message'],
            'You previously paid for this booking; your booking will remain as '
            'pending until the organiser has reviewed your payment status.'

        )

    def test_creating_booking_with_active_user_block(self):
        """
        Test that an active block is automatically used when booking
        """
        event_type = baker.make_recipe('booking.event_type_PC')
        event = baker.make_recipe('booking.future_PC', event_type=event_type, cost=5)
        url = reverse('booking:ajax_create_booking', args=[event.id]) + "?ref=events"

        blocktype = baker.make_recipe(
            'booking.blocktype5', event_type=event_type
        )
        block = baker.make_recipe(
            'booking.block', block_type=blocktype, user=self.user, paid=True
        )
        self.assertTrue(block.active_block())

        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(url)
        self.assertEqual(
            resp.context['alert_message']['message'],
            "Booked with block. "
        )

        bookings = Booking.objects.filter(user=self.user)
        self.assertEqual(bookings.count(), 1)
        self.assertEqual(bookings[0].block, block)
        self.assertTrue(bookings[0].paid)

    @patch("booking.models.membership_models.StripeConnector", MockConnector)
    @pytest.mark.freeze_time("2024, 2, 20")
    def test_creating_booking_with_active_user_block_and_membership(self):
        """
        Test that by default an active membership is automatically used before a block when booking
        Unless prefernces are set to block
        """
        self.user.userprofile.stripe_customer_id = "cus1"
        self.user.userprofile.save()

        event_type = baker.make_recipe('booking.event_type_PC')
        event1 = baker.make_recipe('booking.future_PC', event_type=event_type, cost=5)
        event2 = baker.make_recipe('booking.future_PC', event_type=event_type, cost=5)
        event1_url = reverse('booking:ajax_create_booking', args=[event1.id]) + "?ref=events"
        event2_url = reverse('booking:ajax_create_booking', args=[event2.id]) + "?ref=events"

        blocktype = baker.make_recipe(
            'booking.blocktype5', event_type=event_type
        )
        block = baker.make_recipe(
            'booking.block', block_type=blocktype, user=self.user, paid=True
        )
        assert block.active_block()

        m1 = baker.make(Membership, name="m1", active=True)
        baker.make(MembershipItem, membership=m1, event_type=event_type, quantity=2)
        user_membership = baker.make(
            UserMembership, 
            user=self.user, 
            membership=m1, 
            subscription_id="sub-1",
            subscription_status="active",
            start_date=datetime(2024, 2, 1, tzinfo=dt_timezone.utc)
        )

        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(event1_url)
        assert resp.context['alert_message']['message'] == "Booked with membership."

        booking = Booking.objects.get(user=self.user, event=event1)
        assert booking.block is None
        assert booking.membership == user_membership
        assert booking.paid

        # change preferences
        self.user.userprofile.booking_preference = "block"
        self.user.userprofile.save()
        # membership still valid for both events
        for event in [event1, event2]:
            assert user_membership.valid_for_event(event)

        resp = self.client.post(event2_url)
        assert resp.context['alert_message']['message'].strip() == "Booked with block."

        booking = Booking.objects.get(user=self.user, event=event2)
        assert booking.block == block
        assert booking.membership is None
        assert booking.paid

    @patch("booking.models.membership_models.StripeConnector", MockConnector)
    @pytest.mark.freeze_time("2024, 2, 20")
    def test_creating_booking_with_active_membership_block_preference(self):
        """
        Test that by default an active membership is used when prefernces are set to block
        """
        self.user.userprofile.stripe_customer_id = "cus1"
        self.user.userprofile.booking_preference = "block"
        self.user.userprofile.save()

        event_type = baker.make_recipe('booking.event_type_PC')
        event1 = baker.make_recipe('booking.future_PC', event_type=event_type, cost=5)
        event1_url = reverse('booking:ajax_create_booking', args=[event1.id]) + "?ref=events"

        m1 = baker.make(Membership, name="m1", active=True)
        baker.make(MembershipItem, membership=m1, event_type=event_type, quantity=2)
        user_membership = baker.make(
            UserMembership, 
            user=self.user, 
            membership=m1, 
            subscription_id="sub-1",
            subscription_status="active",
            start_date=datetime(2024, 2, 1, tzinfo=dt_timezone.utc)
        )

        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(event1_url)
        assert resp.context['alert_message']['message'] == "Booked with membership."

        booking = Booking.objects.get(user=self.user, event=event1)
        assert booking.block is None
        assert booking.membership == user_membership
        assert booking.paid

    def test_creating_booking_with_unpaid_user_block(self):
        """
        Test that an unpaid block is ignored used when booking
        """
        event_type = baker.make_recipe('booking.event_type_PC', )
        event = baker.make_recipe('booking.future_PC', event_type=event_type, cost=5)
        url = reverse('booking:ajax_create_booking', args=[event.id]) + "?ref=events"

        blocktype = baker.make_recipe(
            'booking.blocktype5', event_type=event_type
        )
        block = baker.make_recipe(
            'booking.block', block_type=blocktype, user=self.user, paid=False
        )
        self.assertFalse(block.active_block())

        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(url)
        self.assertEqual(
            resp.context['alert_message']['message'],
            'Added to basket; booking not confirmed until payment has been made.'
        )

        bookings = Booking.objects.filter(user=self.user)
        self.assertEqual(bookings.count(), 1)
        self.assertIsNone(bookings[0].block)
        self.assertFalse(bookings[0].paid)

    def test_cannot_book_for_members_only_class(self):
        event = baker.make_recipe(
            'booking.future_PC', members_only=True, cost=5
        )
        url = reverse('booking:ajax_create_booking', args=[event.id]) + "?ref=events"
        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(url)
        assert resp.status_code == 400
        assert resp.content.decode('utf-8') == (
            "Only members are allowed to book this class; please contact the studio for further information."
        )

    def test_cannot_book_for_pole_practice_without_permission(self):
        """
        Test trying to create a booking for pole practice without permission returns 400
        """
        event = baker.make_recipe(
            'booking.future_PP', event_type__subtype='Pole practice', cost=5
        )
        url = reverse('booking:ajax_create_booking', args=[event.id]) + "?ref=events"
        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(
            resp.content.decode('utf-8'),
             "Additional permission is required to book this class; please "
             "contact the studio for further information."
        )

    @patch('booking.models.booking_models.timezone')
    @patch('booking.views.views_utils.timezone')
    def test_booking_with_transfer_block(self, mock_tz, mock_tz1):
        """
        Usually there should be only one block of each type available, but in
        case an admin has added additional blocks, ensure that the one with the
        earlier expiry date is used
        """
        mock_tz.now.return_value = mock_tz1.now.return_value = datetime(2015, 1, 10, tzinfo=dt_timezone.utc)
        event_type = baker.make_recipe('booking.event_type_PC')
        event = baker.make_recipe('booking.future_PC', event_type=event_type, cost=5)
        url = reverse('booking:ajax_create_booking', args=[event.id]) + "?ref=events"
        blocktype = baker.make_recipe(
            'booking.blocktype', event_type=event_type, identifier="transferred", duration=1
        )
        transfer = baker.make_recipe(
            'booking.block', block_type=blocktype, user=self.user, paid=True,
            start_date=datetime(2015, 1, 2, tzinfo=dt_timezone.utc)
        )

        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(url)

        bookings = Booking.objects.filter(user=self.user)
        self.assertEqual(bookings.count(), 1)
        self.assertEqual(bookings[0].block, transfer)

        self.assertEqual(
            resp.context['alert_message']['message'],
            "Booked with credit block."
        )

    @patch('booking.models.booking_models.timezone')
    @patch('booking.views.views_utils.timezone')
    def test_booking_with_block_if_multiple_blocks_available(self, mock_views_tz, mock_tz):
        """
        Usually there should be only one block of each type available, but in
        case an admin has added additional blocks, ensure that the one with the
        earlier expiry date is used
        """
        mock_now = datetime(2015, 1, 10, tzinfo=dt_timezone.utc)
        mock_tz.now.return_value = mock_now
        mock_views_tz.now.return_value = mock_now
        event_type = baker.make_recipe('booking.event_type_PC')

        event = baker.make_recipe('booking.future_PC', event_type=event_type, cost=5)
        url = reverse('booking:ajax_create_booking', args=[event.id]) + "?ref=events"
        blocktype = baker.make_recipe(
            'booking.blocktype5', event_type=event_type, duration=2
        )
        block1 = baker.make_recipe(
            'booking.block', block_type=blocktype, user=self.user, paid=True,
            start_date=datetime(2015, 1, 2, tzinfo=dt_timezone.utc)
        )
        block2 = baker.make_recipe(
            'booking.block', block_type=blocktype, user=self.user, paid=True,
            start_date=datetime(2015, 1, 1, tzinfo=dt_timezone.utc)
        )
        # block1 was created first, but block2 has earlier expiry date so
        # should be used first
        self.assertGreater(block1.expiry_date, block2.expiry_date)

        self.client.login(username=self.user.username, password='test')
        self.client.post(url)

        bookings = Booking.objects.filter(user=self.user)
        self.assertEqual(bookings.count(), 1)
        self.assertEqual(bookings[0].block, block2)

        # change start dates so block1 now has the earlier expiry date
        bookings[0].delete()
        block2.start_date = datetime(2015, 1, 3, tzinfo=dt_timezone.utc)
        block2.save()
        resp = self.client.post(url)
        self.assertEqual(
            resp.context['alert_message']['message'],
            "Booked with block. "
        )

        bookings = Booking.objects.filter(user=self.user)
        self.assertEqual(bookings.count(), 1)
        self.assertEqual(bookings[0].block, block1)

    def test_booking_with_block_completes_block(self):
        event_type = baker.make_recipe('booking.event_type_PC')

        event = baker.make_recipe('booking.future_PC', event_type=event_type, cost=5)
        url = reverse('booking:ajax_create_booking', args=[event.id]) + "?ref=events"
        blocktype = baker.make_recipe(
            'booking.blocktype5', event_type=event_type, duration=2
        )
        block1 = baker.make_recipe(
            'booking.block', block_type=blocktype, user=self.user, paid=True,
        )
        baker.make("booking.booking", user=self.user, block=block1, paid=True, _quantity=4)

        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(url)

        bookings = Booking.objects.filter(user=self.user)
        assert bookings.count() == 5
        assert block1.bookings.count() == 5
        assert "You have just used the last space" in resp.content.decode()

    def test_create_booking_user_on_waiting_list(self):
        """
        Test creating a booking for a user on the waiting list deletes waiting list
        """
        baker.make(WaitingListUser, event=self.event, user=self.user)
        baker.make(WaitingListUser, event=self.event)
        baker.make(WaitingListUser, user=self.user)
        self.assertEqual(Booking.objects.all().count(), 0)
        self.client.login(username=self.user.username, password='test')
        self._mock_new_user_email_sent()

        self.client.post(self.event_url)
        self.assertEqual(Booking.objects.all().count(), 1)
        # the waiting list user for this user and event only has been deleted
        self.assertEqual(WaitingListUser.objects.all().count(), 2)
        self.assertFalse(WaitingListUser.objects.filter(user=self.user, event=self.event).exists())

        # unpaid booking, no email
        self.assertEqual(len(mail.outbox), 0)

    def test_cannot_make_booking_if_account_locked(self):
        """
        Test trying to create booking with locked account returns 400
        """
        expires = timezone.now() + timedelta(days=4)
        AccountBan.objects.create(user=self.user, end_date=expires)
        baker.make_recipe('booking.booking', user=self.user, event=self.event)

        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(self.event_url)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(
            resp.content.decode('utf-8'),
            f"Your account is currently blocked until {expires.strftime('%d %b %Y, %H:%M')}"
        )


class AjaxTests(TestSetupMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.event = baker.make_recipe('booking.future_PC', max_participants=3)

        self.staff_user = User.objects.create_user(
            username='testuser', email='test@test.com', password='test'
        )
        self.staff_user.is_staff = True
        self.staff_user.save()
        self.instructor_user = User.objects.create_user(
            username='testinstructoruser', email='instructor@test.com',
            password='test'
        )
        group, _ = Group.objects.get_or_create(name="instructors")
        self.instructor_user.groups.add(group)

        self.client.login(username=self.user.username, password='test')

    def test_update_shopping_basket_count_no_bookings(self):
        url = reverse('booking:update_shopping_basket_count')
        resp = self.client.get(url)
        self.assertIn('<span class="basket-count">0</span>', resp.content.decode('utf-8'))

    def test_update_shopping_basket_count_unpaid_bookings(self):
        baker.make_recipe('booking.booking', event=self.event, user=self.user)
        baker.make_recipe('booking.booking') # booking for another user
        url = reverse('booking:update_shopping_basket_count')
        resp = self.client.get(url)
        self.assertIn('<span class="basket-count">1</span>', resp.content.decode('utf-8'))

    def test_update_shopping_basket_count_paid_and_unpaid_bookings(self):
        event1 = baker.make_recipe('booking.future_PC')
        baker.make_recipe('booking.booking', event=self.event, user=self.user, paid=True)
        baker.make_recipe('booking.booking', event=event1, user=self.user)
        url = reverse('booking:update_shopping_basket_count')
        resp = self.client.get(url)
        self.assertIn('<span class="basket-count">1</span>', resp.content.decode('utf-8'))

    def test_toggle_waiting_list_on(self):
        url = reverse('booking:toggle_waiting_list', args=[self.event.id])
        self.assertFalse(WaitingListUser.objects.exists())
        resp = self.client.post(url)

        wl_user = WaitingListUser.objects.first()
        self.assertEqual(wl_user.user, self.user)
        self.assertEqual(wl_user.event, self.event)

        self.assertEqual(resp.context['event'], self.event)
        self.assertEqual(resp.context['on_waiting_list'], True)

    def test_toggle_waiting_list_off(self):
        url = reverse('booking:toggle_waiting_list', args=[self.event.id])
        baker.make(WaitingListUser, user=self.user, event=self.event)
        resp = self.client.post(url)

        self.assertFalse(WaitingListUser.objects.exists())
        self.assertEqual(resp.context['event'], self.event)
        self.assertEqual(resp.context['on_waiting_list'], False)

    def test_shopping_basket_bookings_total_context(self):
        self.event.cost = 5
        self.event.payment_open = True
        self.event.save()
        booking = baker.make_recipe('booking.booking', event=self.event, user=self.user)
        request = self.factory.post(reverse("booking:delete_booking", args=(booking.id,)))
        request.user = self.user
        _add_session(request)
        context = shopping_basket_bookings_total_context(request)
        self.assertEqual(context['total_unpaid_booking_cost'], 5)

    def test_shopping_basket_bookings_total_context_no_cost(self):
        booking = baker.make_recipe('booking.booking', event=self.event, user=self.user)
        request = self.factory.post(reverse("booking:delete_booking", args=(booking.id,)))
        request.user = self.user
        _add_session(request)
        context = shopping_basket_bookings_total_context(request)
        self.assertIsNone(context['total_unpaid_booking_cost'])

    def test_shopping_basket_bookings_total_context_with_code(self):
        booking = baker.make_recipe('booking.booking', event=self.event, user=self.user)
        request = self.factory.post(
            reverse("booking:delete_booking", args=(booking.id,)) + "?code=test"
        )
        request.user = self.user
        _add_session(request)
        context = shopping_basket_bookings_total_context(request)
        self.assertIsNone(context['total_unpaid_booking_cost'])
        self.assertEqual(context['booking_code'], 'test')

    def test_ajax_shopping_blocks_total(self):
        block = baker.make_recipe('booking.block', block_type__cost=20, user=self.user)
        request = self.factory.post(
            reverse("booking:delete_block", args=(block.id,))
        )
        request.user = self.user
        _add_session(request)
        context = shopping_basket_blocks_total_context(request)
        self.assertEqual(context['total_unpaid_block_cost'], 20)

    def test_ajax_shopping_basket_blocks_total_with_code(self):
        block = baker.make_recipe('booking.block', block_type__cost=20, user=self.user)
        request = self.factory.post(
            reverse("booking:delete_block", args=(block.id,)) + '?code=test'
        )
        request.user = self.user
        _add_session(request)
        context = shopping_basket_blocks_total_context(request)
        self.assertEqual(context['total_unpaid_block_cost'], 20)
        self.assertEqual(context['block_code'], 'test')

    @override_settings(PAYMENT_METHOD="paypal")
    def test_ajax_shopping_basket_bookings_total_updates_cart_items_paypal(self):
        # calling the shopping_basket_bookings_total resets the session cart items
        # paypal only
        self.event.cost = 5
        self.event.payment_open = True
        self.event.save()
        booking = baker.make_recipe('booking.booking', event=self.event, user=self.user)

        request = self.factory.post(
            reverse("booking:delete_booking", args=(booking.id,)) + "?code=test"
        )
        request.user = self.user
        _add_session(request)
        context = shopping_basket_bookings_total_context(request)
        assert context['total_unpaid_booking_cost'] == 5
        assert request.session["cart_items"] == f"obj=booking ids={booking.id} usr={self.user.email}"

        request.session["cart_items"] = "foo 1"
        context = shopping_basket_bookings_total_context(request)
        assert request.session["cart_items"] == f"obj=booking ids={booking.id} usr={self.user.email}"

    @override_settings(PAYMENT_METHOD="paypal")
    def test_shopping_basket_bookings_total_context_updates_cart_items_for_blocks_paypal(self):
        # calling the shopping_basket_bookings_total sets the session cart items for unpaid blocks
        # (paypal only)
        # if there are no unpaid bookings left
        booking = baker.make_recipe('booking.booking', event=self.event, user=self.user)
        block = baker.make_recipe('booking.block', block_type__cost=20, user=self.user)
        request = self.factory.post(
            reverse("booking:delete_booking", args=(booking.id,)) + "?code=test"
        )
        request.user = self.user
        _add_session(request)
        context = shopping_basket_bookings_total_context(request)
        assert context['total_unpaid_booking_cost'] is None
        assert request.session["cart_items"] == f"obj=block ids={block.id} usr={self.user.email}"

    @override_settings(PAYMENT_METHOD="paypal")
    def test_ajax_shopping_basket_blocks_total_updates_cart_items_for_paypal(self):
        # calling the shopping_basket_blocks_total sets the session cart items for paypal
        block = baker.make_recipe('booking.block', block_type__cost=20, user=self.user)
        request = self.factory.post(
            reverse("booking:delete_block", args=(block.id,))
        )
        request.user = self.user
        _add_session(request)
        context = shopping_basket_blocks_total_context(request)
        self.assertEqual(context['total_unpaid_block_cost'], 20)
        assert request.session["cart_items"] == f"obj=block ids={block.id} usr={self.user.email}"

    @override_settings(PAYMENT_METHOD="paypal")
    def test_ajax_shopping_basket_blocks_total_updates_cart_items_for_bookings_paypal(self):
        # calling the shopping_basket_blocks_total resets the session cart items for unpaid bookings
        # (paypal only)
        # if there are no unpaid blocks left
        block = baker.make_recipe('booking.block', block_type__cost=20, user=self.user)
        self.event.cost = 5
        self.event.payment_open = True
        self.event.save()
        booking = baker.make_recipe('booking.booking', event=self.event, user=self.user)

        request = self.factory.post(
            reverse("booking:delete_block", args=(block.id,))
        )
        request.user = self.user
        _add_session(request)

        assert "cart_items" not in request.session
        shopping_basket_blocks_total_context(request)

        # No cart items because there are both booking and block unpaid
        assert "cart_items" not in request.session

        block.delete()
        shopping_basket_blocks_total_context(request)

        # After the block is deleted, we can allow booking cart items
        assert request.session["cart_items"] == f"obj=booking ids={booking.id} usr={self.user.email}"


def _add_session(request):
    middleware = SessionMiddleware(lambda x: None)
    middleware.process_request(request)
    request.session.save()
