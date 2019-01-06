# -*- coding: utf-8 -*-
from datetime import datetime
from unittest.mock import patch
from model_mommy import mommy

from django.conf import settings
from django.core import mail
from django.urls import reverse
from django.test import override_settings, TestCase
from django.contrib.auth.models import Group, User
from django.utils import timezone

from accounts.models import OnlineDisclaimer

from booking.models import Event, EventType, Booking, Block, WaitingListUser
from common.tests.helpers import TestSetupMixin, make_data_privacy_agreement

from payments.helpers import create_booking_paypal_transaction


class BookingAjaxCreateViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.pole_class_event_type = mommy.make(
            EventType, event_type='CL', subtype='Pole level class'
        )
        cls.event = mommy.make_recipe('booking.future_EV', max_participants=3)
        cls.event_url = reverse('booking:ajax_create_booking', args=[cls.event.id])
        cls.free_blocktype = mommy.make_recipe(
            'booking.blocktype', size=1, cost=0,
            event_type=cls.pole_class_event_type, identifier='free class'
        )
        cls.group, _ = Group.objects.get_or_create(name='subscribed')

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
        disclaimer = mommy.make_recipe(
           'booking.online_disclaimer', user=user,
            date=datetime(2015, 2, 1, tzinfo=timezone.utc)
        )
        self.assertFalse(disclaimer.is_active)

        self.client.login(username=user.username, password='test')
        resp = self.client.post(self.event_url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:disclaimer_required'))

        mommy.make(OnlineDisclaimer, user=user)
        resp = self.client.post(self.event_url)
        self.assertEqual(resp.status_code, 200)

    def test_create_booking(self):
        """
        Test creating a booking
        """
        self.assertEqual(Booking.objects.all().count(), 0)
        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(self.event_url)
        self.assertEqual(Booking.objects.all().count(), 1)
        self.assertEqual(
            resp.context['alert_message']['message'],
            'Added to basket; booking not confirmed until payment has been made.'
        )

        # email to student only
        self.assertEqual(len(mail.outbox), 1)

    def test_create_booking_sends_email_to_studio_if_set(self):
        """
        Test creating a booking send email to user and studio if flag sent on
        event
        """
        event = mommy.make_recipe(
            'booking.future_EV', max_participants=3,
            email_studio_when_booked=True
        )
        url = reverse('booking:ajax_create_booking', args=[event.id])
        self.assertEqual(Booking.objects.all().count(), 0)
        self.client.login(username=self.user.username, password='test')
        self.client.post(url)
        self.assertEqual(Booking.objects.all().count(), 1)
        # email to student and studio
        self.assertEqual(len(mail.outbox), 2)

    @override_settings(WATCHLIST=['foo@test.com', 'bar@test.com'])
    def test_create_booking_sends_email_to_studio_for_users_on_watchlist(self):
        self.client.login(username=self.user.username, password='test')
        self.client.post(self.event_url)
        self.assertEqual(Booking.objects.count(), 1)
        # email to student only
        self.assertEqual(len(mail.outbox), 1)

        # create watched user and book
        watched_user = User.objects.create_user(
            username='foo', email='foo@test.com', password='test'
        )
        mommy.make(OnlineDisclaimer, user=watched_user)
        make_data_privacy_agreement(watched_user)
        self.client.login(username=watched_user.username, password='test')
        self.client.post(self.event_url)
        self.assertEqual(Booking.objects.count(), 2)
        # 2 addition emails in mailbox for this booking, to student and studio
        self.assertEqual(len(mail.outbox), 3)

    @patch('booking.views.booking_views.send_mail')
    def test_create_booking_with_email_error(self, mock_send_emails):
        """
        Test creating a booking sends email to support if there is an email
        error but still creates booking
        """
        mock_send_emails.side_effect = Exception('Error sending mail')

        event = mommy.make_recipe(
            'booking.future_EV', max_participants=3,
            email_studio_when_booked=True
        )
        url = reverse('booking:ajax_create_booking', args=[event.id])

        self.assertEqual(Booking.objects.all().count(), 0)
        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(url)
        self.assertEqual(Booking.objects.all().count(), 1)
        self.assertEqual(
            resp.context['alert_message']['message'],
            'Added to basket; booking not confirmed until payment has been made.'
        )

        # email to support only
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, [settings.SUPPORT_EMAIL])
        self.assertEqual(mail.outbox[1].to, [settings.SUPPORT_EMAIL])

    def test_create_room_hire(self):
        """
        Test creating a room hire booking
        """
        room_hire = mommy.make_recipe('booking.future_RH', max_participants=3)
        url = reverse('booking:ajax_create_booking', args=[room_hire.id])
        self.assertEqual(Booking.objects.all().count(), 0)
        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(url)
        self.assertEqual(Booking.objects.all().count(), 1)
        self.assertEqual(
            resp.context['alert_message']['message'],
            'Added to basket; booking not confirmed until payment has been made.'
        )

    def test_cannot_make_duplicate_booking(self):
        """
        Test trying to create duplicate booking returns 400
        """
        mommy.make_recipe('booking.booking', user=self.user, event=self.event)

        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(self.event_url)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.content.decode('utf-8'), '')

    def test_cannot_book_for_full_event(self):
        """
        Test trying create booking for a full event returns 400
        """
        users = mommy.make_recipe('booking.user', _quantity=3)
        for user in users:
            mommy.make_recipe('booking.booking', event=self.event, user=user)
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
        event = mommy.make_recipe('booking.future_EV', max_participants=3, cancelled=True)
        url = reverse('booking:ajax_create_booking', args=[event.id])

        self.client.login(username=self.user.username, password='test')
        # try to book for event
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.content.decode('utf-8'), 'Sorry, this event has been cancelled')

    def test_cancelled_booking_can_be_rebooked(self):
        """
        Test can load create booking page with a cancelled booking
        """
        booking = mommy.make_recipe(
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
        pclass = mommy.make_recipe(
            'booking.future_PC', allow_booking_cancellation=False, cost=10
        )
        url = reverse('booking:ajax_create_booking', args=[pclass.id])

        # book for non-refundable event and mark as no_show
        booking = mommy.make_recipe(
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

        pclass = mommy.make_recipe(
            'booking.future_PC', allow_booking_cancellation=False, cost=10
        )
        block = mommy.make_recipe(
            'booking.block', user=self.user, paid=True,
            block_type__event_type =pclass.event_type
        )
        # book for non-refundable event and mark as no_show
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=pclass, paid=True,
            no_show=True, block=block
        )

        url = reverse('booking:ajax_create_booking', args=[pclass.id])
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
        booking = mommy.make_recipe(
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

    def test_rebook_cancelled_paypal_paid_booking(self):
        """
        Test rebooking a cancelled booking still marked as paid by paypal makes
        booking status open, fetches the paypal
        transaction id
        """
        event = mommy.make_recipe('booking.future_PC')
        url = reverse('booking:ajax_create_booking', args=[event.id])
        booking = mommy.make_recipe(
            'booking.booking', event=event, user=self.user, paid=True,
            payment_confirmed=True, status='CANCELLED'
        )
        pptrans = create_booking_paypal_transaction(
            booking=booking, user=self.user
        )
        pptrans.transaction_id = "txn"
        pptrans.save()

        # try to book again
        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(url)
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
        self.assertIn(pptrans.transaction_id, mail_to_studio.body)
        self.assertIn(pptrans.invoice_id, mail_to_studio.body)

    def test_creating_booking_with_active_user_block(self):
        """
        Test that an active block is automatically used when booking
        """
        event_type = mommy.make_recipe('booking.event_type_PC')
        event = mommy.make_recipe('booking.future_PC', event_type=event_type)
        url = reverse('booking:ajax_create_booking', args=[event.id])

        blocktype = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type
        )
        block = mommy.make_recipe(
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

    def test_creating_booking_with_unpaid_user_block(self):
        """
        Test that an unpaid block is ignored used when booking
        """
        event_type = mommy.make_recipe('booking.event_type_PC')
        event = mommy.make_recipe('booking.future_PC', event_type=event_type)
        url = reverse('booking:ajax_create_booking', args=[event.id])

        blocktype = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type
        )
        block = mommy.make_recipe(
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

    def test_cannot_book_for_pole_practice_if_not_regular_student(self):
        """
        Test trying to create a booking for pole practice if not regular
         student returns 400
        """
        event = mommy.make_recipe(
            'booking.future_PP', event_type__subtype='Pole practice'
        )
        url = reverse('booking:ajax_create_booking', args=[event.id])

        self.user.user_permissions.all().delete()

        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(
            resp.content.decode('utf-8'),
             "You must be a regular student to book this class; please "
             "contact the studio for further information."
        )

    @patch('booking.models.timezone')
    def test_booking_with_block_if_multiple_blocks_available(self, mock_tz):
        """
        Usually there should be only one block of each type available, but in
        case an admin has added additional blocks, ensure that the one with the
        earlier expiry date is used
        """
        mock_tz.now.return_value = datetime(2015, 1, 10, tzinfo=timezone.utc)
        event_type = mommy.make_recipe('booking.event_type_PC')

        event = mommy.make_recipe('booking.future_PC', event_type=event_type)
        url = reverse('booking:ajax_create_booking', args=[event.id])
        blocktype = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type, duration=2
        )
        block1 = mommy.make_recipe(
            'booking.block', block_type=blocktype, user=self.user, paid=True,
            start_date=datetime(2015, 1, 2, tzinfo=timezone.utc)
        )
        block2 = mommy.make_recipe(
            'booking.block', block_type=blocktype, user=self.user, paid=True,
            start_date=datetime(2015, 1, 1, tzinfo=timezone.utc)
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
        block2.start_date = datetime(2015, 1, 3, tzinfo=timezone.utc)
        block2.save()
        resp = self.client.post(url)
        self.assertEqual(
            resp.context['alert_message']['message'],
            "Booked with block. "
        )

        bookings = Booking.objects.filter(user=self.user)
        self.assertEqual(bookings.count(), 1)
        self.assertEqual(bookings[0].block, block1)

    @patch('booking.models.timezone')
    def test_booking_with_block_if_original_and_free_available(self, mock_tz):
        """
        Usually there will only be an open free block attached to another block
        if the original is full, but in case an admin has changed this, ensure
        that the original block is used first (free block with parent block
        should always be created after the original block)
        """
        mock_tz.now.return_value = datetime(2015, 1, 10, tzinfo=timezone.utc)

        event = mommy.make_recipe(
            'booking.future_PC', event_type=self.pole_class_event_type
        )
        url = reverse('booking:ajax_create_booking', args=[event.id])

        blocktype = mommy.make_recipe(
            'booking.blocktype', size=10, cost=60, duration=4,
            event_type=self.pole_class_event_type, identifier='standard'
        )

        block = mommy.make_recipe(
            'booking.block', user=self.user, block_type=blocktype, paid=True
        )
        free_block = mommy.make_recipe(
            'booking.block', user=self.user, block_type=self.free_blocktype,
            paid=True, parent=block
        )

        self.assertTrue(block.active_block())
        self.assertTrue(free_block.active_block())
        self.assertEqual(block.expiry_date, free_block.expiry_date)

        blocks = self.user.blocks.all()
        active_blocks = [
            block for block in blocks if block.active_block()
            and block.block_type.event_type == event.event_type
        ]
        # the original and free block are both available blocks for this event
        self.assertEqual(set(active_blocks), set([block, free_block]))

        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(url)
        self.assertEqual(
            resp.context['alert_message']['message'],
            "Booked with block. "
        )

        # booking created using the original block
        bookings = Booking.objects.filter(user=self.user)
        self.assertEqual(bookings.count(), 1)
        self.assertEqual(bookings[0].block, block)

    def test_create_booking_uses_last_of_10_class_blocks(self):
        block = mommy.make_recipe(
            'booking.block_10', user=self.user,
            block_type__event_type=self.pole_class_event_type,
            paid=True, start_date=timezone.now()
        )
        event = mommy.make_recipe(
            'booking.future_CL', cost=10, event_type=self.pole_class_event_type
        )
        url = reverse('booking:ajax_create_booking', args=[event.id])

        mommy.make_recipe(
            'booking.booking', block=block, user=self.user, _quantity=9
        )

        self.assertEqual(Block.objects.count(), 1)
        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(url)
        self.assertEqual(
            resp.context['alert_message']['message'],
            "Booked with block. "
            "You have just used the last space in your block. "
            "You have qualified for a extra free class which has been added to your blocks"
        )

        self.assertEqual(block.bookings.count(), 10)
        self.assertEqual(Block.objects.count(), 2)
        self.assertEqual(Block.objects.latest('id').block_type, self.free_blocktype)

    def test_booking_uses_last_of_10_blocks_free_block_already_exists(self):
        block = mommy.make_recipe(
            'booking.block_10', user=self.user,
            block_type__event_type=self.pole_class_event_type,
            paid=True, start_date=timezone.now()
        )
        event = mommy.make_recipe(
            'booking.future_EV', cost=10, event_type=self.pole_class_event_type
        )
        url = reverse('booking:ajax_create_booking', args=[event.id])

        mommy.make_recipe(
            'booking.block', user=self.user, block_type=self.free_blocktype,
            paid=True, parent=block
        )

        mommy.make_recipe(
            'booking.booking', block=block, user=self.user, _quantity=9
        )
        self.assertEqual(Block.objects.count(), 2)

        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(url)
        self.assertEqual(
            resp.context['alert_message']['message'],
            "Booked with block. "
            "You have just used the last space in your block. "
            "Go to My Blocks buy a new one."
        )

        self.assertEqual(block.bookings.count(), 10)
        self.assertEqual(Block.objects.count(), 2)

    def test_create_booking_uses_last_of_block_but_doesnt_qualify_for_free(self):
        block = mommy.make_recipe(
            'booking.block_5', user=self.user,
            block_type__event_type=self.pole_class_event_type,
            paid=True, start_date=timezone.now()
        )
        event = mommy.make_recipe(
            'booking.future_CL', cost=10, event_type=self.pole_class_event_type
        )
        url = reverse('booking:ajax_create_booking', args=[event.id])

        mommy.make_recipe(
            'booking.booking', block=block, user=self.user, _quantity=4
        )

        self.assertEqual(Block.objects.count(), 1)

        self.client.login(username=self.user.username, password='test')
        resp = self.client.post(url)
        self.assertEqual(
            resp.context['alert_message']['message'],
            "Booked with block. "
            "You have just used the last space in your block. "
            "Go to My Blocks buy a new one."
        )

        self.assertEqual(block.bookings.count(), 5)
        self.assertTrue(block.full)
        # 5 class blocks do not qualify for free classes, no free class block
        # created
        self.assertEqual(Block.objects.count(), 1)


class AjaxTests(TestSetupMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.event = mommy.make_recipe('booking.future_PC', max_participants=3)

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
        mommy.make_recipe('booking.booking', event=self.event, user=self.user)
        mommy.make_recipe('booking.booking') # booking for another user
        url = reverse('booking:update_shopping_basket_count')
        resp = self.client.get(url)
        self.assertIn('<span class="basket-count">1</span>', resp.content.decode('utf-8'))

    def test_update_shopping_basket_count_paid_and_unpaid_bookings(self):
        event1 = mommy.make_recipe('booking.future_PC')
        mommy.make_recipe('booking.booking', event=self.event, user=self.user, paid=True)
        mommy.make_recipe('booking.booking', event=event1, user=self.user)
        url = reverse('booking:update_shopping_basket_count')
        resp = self.client.get(url)
        self.assertIn('<span class="basket-count">1</span>', resp.content.decode('utf-8'))

    def test_update_bookings_count_spaces(self):
        url = reverse('booking:update_booking_count', args=[self.event.id])
        resp = self.client.get(url)
        self.assertIn('AVAILABLE', resp.content.decode('utf-8'))
        self.assertNotIn('3/3', resp.content.decode('utf-8'))

    def test_update_bookings_count_full(self):
        url = reverse('booking:update_booking_count', args=[self.event.id])
        mommy.make_recipe('booking.booking', event=self.event, _quantity=3)
        resp = self.client.get(url)
        self.assertIn('FULL', resp.content.decode('utf-8'))
        self.assertNotIn('0/3', resp.content.decode('utf-8'))

    def test_update_bookings_count_spaces_instructor(self):
        url = reverse('booking:update_booking_count', args=[self.event.id])
        self.client.login(username=self.instructor_user.username, password='test')
        resp = self.client.get(url)
        self.assertNotIn('AVAILABLE', resp.content.decode('utf-8'))
        self.assertIn('3/3', resp.content.decode('utf-8'))

    def test_update_bookings_count_full_instructor(self):
        url = reverse('booking:update_booking_count', args=[self.event.id])
        self.client.login(username=self.instructor_user.username, password='test')
        mommy.make_recipe('booking.booking', event=self.event, _quantity=3)
        resp = self.client.get(url)
        self.assertNotIn('FULL', resp.content.decode('utf-8'))
        self.assertIn('0/3', resp.content.decode('utf-8'))

    def test_update_bookings_count_spaces_staff(self):
        url = reverse('booking:update_booking_count', args=[self.event.id])
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.get(url)
        self.assertNotIn('AVAILABLE', resp.content.decode('utf-8'))
        self.assertIn('3/3', resp.content.decode('utf-8'))

    def test_update_bookings_count_full_staff(self):
        url = reverse('booking:update_booking_count', args=[self.event.id])
        self.client.login(username=self.staff_user.username, password='test')
        mommy.make_recipe('booking.booking', event=self.event, _quantity=3)
        resp = self.client.get(url)
        self.assertNotIn('FULL', resp.content.decode('utf-8'))
        self.assertIn('0/3', resp.content.decode('utf-8'))

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
        mommy.make(WaitingListUser, user=self.user, event=self.event)
        resp = self.client.post(url)

        self.assertFalse(WaitingListUser.objects.exists())
        self.assertEqual(resp.context['event'], self.event)
        self.assertEqual(resp.context['on_waiting_list'], False)
