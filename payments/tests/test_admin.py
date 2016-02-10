# -*- coding: utf-8 -*-

from model_mommy import mommy

from django.contrib.auth.models import User
from django.contrib.admin.sites import AdminSite
from django.test import TestCase

from paypal.standard.ipn.models import PayPalIPN

from booking.models import Ticket, TicketBooking, TicketedEvent

from payments import helpers
from payments import admin
from payments.models import PaypalBookingTransaction, PaypalBlockTransaction, \
    PaypalTicketBookingTransaction


class PaymentsAdminTests(TestCase):

    def test_paypal_booking_admin_display(self):
        user = mommy.make_recipe(
            'booking.user', first_name='Test', last_name='User')
        booking = mommy.make_recipe('booking.booking', user=user)
        pptrans = helpers.create_booking_paypal_transaction(
            booking.user, booking
        )

        ppbooking_admin = admin.PaypalBookingTransactionAdmin(
            PaypalBookingTransaction, AdminSite()
        )
        ppbooking_query = ppbooking_admin.get_queryset(None)[0]

        self.assertEqual(
            ppbooking_admin.get_booking_id(ppbooking_query), booking.id
        )
        self.assertEqual(
            ppbooking_admin.get_user(ppbooking_query), 'Test User'
        )
        self.assertEqual(
            ppbooking_admin.get_event(ppbooking_query), booking.event
        )
        self.assertEqual(
            ppbooking_admin.cost(ppbooking_query),
            u"\u00A3{}.00".format(booking.event.cost)
        )

    def test_paypal_block_admin_display(self):
        user = mommy.make_recipe(
            'booking.user', first_name='Test', last_name='User')
        block = mommy.make_recipe('booking.block_5', user=user)
        pptrans = helpers.create_block_paypal_transaction(
            block.user, block
        )

        ppblock_admin = admin.PaypalBlockTransactionAdmin(
            PaypalBlockTransaction, AdminSite()
        )
        ppblock_query = ppblock_admin.get_queryset(None)[0]

        self.assertEqual(
            ppblock_admin.get_block_id(ppblock_query), block.id
        )
        self.assertEqual(
            ppblock_admin.get_user(ppblock_query), 'Test User'
        )
        self.assertEqual(
            ppblock_admin.get_blocktype(ppblock_query), block.block_type
        )
        self.assertEqual(
            ppblock_admin.cost(ppblock_query),
            u"\u00A3{:.2f}".format(block.block_type.cost)
        )
        self.assertEqual(
            ppblock_admin.block_start(ppblock_query),
            block.start_date.strftime('%d %b %Y, %H:%M')
        )
        self.assertEqual(
            ppblock_admin.block_expiry(ppblock_query),
            block.expiry_date.strftime('%d %b %Y, %H:%M')
        )

    def test_paypal_ticket_admin_display(self):
        user = mommy.make_recipe(
            'booking.user', first_name='Test', last_name='User')
        ticketed_event = mommy.make(TicketedEvent, ticket_cost=10)
        ticket_booking = mommy.make(
            TicketBooking, user=user, ticketed_event=ticketed_event
        )
        mommy.make(Ticket, ticket_booking=ticket_booking, _quantity=2)
        pptrans = helpers.create_ticket_booking_paypal_transaction(
            user, ticket_booking
        )

        pptbooking_admin = admin.PaypalTicketBookingTransactionAdmin(
            PaypalTicketBookingTransaction, AdminSite()
        )
        query = pptbooking_admin.get_queryset(None)[0]

        self.assertEqual(
            pptbooking_admin.get_ticket_booking_id(query), ticket_booking.id
        )
        self.assertEqual(
            pptbooking_admin.get_user(query), 'Test User'
        )
        self.assertEqual(
            pptbooking_admin.get_ticketed_event(query),
            ticket_booking.ticketed_event
        )
        self.assertEqual(pptbooking_admin.ticket_cost(query), "£10.00")
        self.assertEqual(
            pptbooking_admin.number_of_tickets(query),
            ticket_booking.tickets.count()
        )
        self.assertEqual(pptbooking_admin.total_cost(query), "£20.00")

    def test_paypaladmin_display(self):
        mommy.make(PayPalIPN, first_name='Mickey', last_name='Mouse')
        paypal_admin = admin.PayPalAdmin(PayPalIPN, AdminSite())
        query = paypal_admin.get_queryset(None)[0]
        self.assertEqual(paypal_admin.buyer(query), 'Mickey Mouse')


class PaymentsAdminFiltersTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = mommy.make_recipe(
            'booking.user', first_name="Foo", last_name="Bar", username="foob"
        )
        cls.user1 = mommy.make_recipe(
            'booking.user', first_name="Donald", last_name="Duck", username="dd"
        )
        for user in User.objects.all():
            mommy.make(PaypalBookingTransaction, booking__user=user,
                       _quantity=5
                       )
            mommy.make(PaypalBlockTransaction, block__user=user,
                       _quantity=5
                       )
            mommy.make(
                PaypalTicketBookingTransaction, ticket_booking__user=user,
                _quantity=5
            )

    def test_payments_user_filter_choices(self):
        # test that user filter shows formatted choices ordered by first name

        userfilter = admin.PaypalBookingUserFilter(
            None, {}, PaypalBookingTransaction,
            admin.PaypalBookingTransactionAdmin
        )

        self.assertEqual(
            userfilter.lookup_choices,
            [
                (self.user1.id, 'Donald Duck (dd)'),
                (self.user.id, 'Foo Bar (foob)')
            ]
        )

    def test_paypal_booking_user_filter(self):

        userfilter = admin.PaypalBookingUserFilter(
            None, {}, PaypalBookingTransaction,
            admin.PaypalBookingTransactionAdmin
        )
        result = userfilter.queryset(
            None, PaypalBookingTransaction.objects.all()
        )
        # with no filter parameters, return all
        self.assertEqual(PaypalBookingTransaction.objects.count(), 10)
        self.assertEqual(result.count(), 10)
        self.assertEqual(
            [ppbt.id for ppbt in result],
            [ppbt.id for ppbt in PaypalBookingTransaction.objects.all()]
        )

        userfilter = admin.PaypalBookingUserFilter(
            None, {'user': self.user.id}, PaypalBookingTransaction,
            admin.PaypalBookingTransactionAdmin
        )
        result = userfilter.queryset(
            None, PaypalBookingTransaction.objects.all()
        )
        self.assertEqual(PaypalBookingTransaction.objects.count(), 10)
        self.assertEqual(result.count(), 5)
        self.assertEqual(
            [ppbt.id for ppbt in result],
            [
                ppbt.id for ppbt in
                PaypalBookingTransaction.objects.filter(booking__user=self.user)
            ]
        )

    def test_paypal_ticket_booking_user_filter(self):

        userfilter = admin.PaypalTicketBookingUserFilter(
            None, {}, PaypalTicketBookingTransaction,
            admin.PaypalTicketBookingTransactionAdmin
        )
        result = userfilter.queryset(
            None, PaypalTicketBookingTransaction.objects.all()
        )
        # with no filter parameters, return all
        self.assertEqual(PaypalTicketBookingTransaction.objects.count(), 10)
        self.assertEqual(result.count(), 10)
        self.assertEqual(
            [ppbt.id for ppbt in result],
            [ppbt.id for ppbt in PaypalTicketBookingTransaction.objects.all()]
        )

        userfilter = admin.PaypalTicketBookingUserFilter(
            None, {'user': self.user.id}, PaypalTicketBookingTransaction,
            admin.PaypalTicketBookingTransactionAdmin
        )
        result = userfilter.queryset(
            None, PaypalTicketBookingTransaction.objects.all()
        )
        self.assertEqual(PaypalTicketBookingTransaction.objects.count(), 10)
        self.assertEqual(result.count(), 5)
        self.assertEqual(
            [ppbt.id for ppbt in result],
            [
                ppbt.id for ppbt in
                PaypalTicketBookingTransaction.objects.filter(
                    ticket_booking__user=self.user
                )
            ]
        )

    def test_paypal_block_user_filter(self):

        userfilter = admin.PaypalBlockUserFilter(
            None, {}, PaypalBlockTransaction,
            admin.PaypalBlockTransactionAdmin
        )
        result = userfilter.queryset(
            None, PaypalBlockTransaction.objects.all()
        )
        # with no filter parameters, return all
        self.assertEqual(PaypalBlockTransaction.objects.count(), 10)
        self.assertEqual(result.count(), 10)
        self.assertEqual(
            [ppbt.id for ppbt in result],
            [ppbt.id for ppbt in PaypalBlockTransaction.objects.all()]
        )

        userfilter = admin.PaypalBlockUserFilter(
            None, {'user': self.user.id}, PaypalBlockTransaction,
            admin.PaypalBlockTransactionAdmin
        )
        result = userfilter.queryset(
            None, PaypalBlockTransaction.objects.all()
        )
        self.assertEqual(PaypalBlockTransaction.objects.count(), 10)
        self.assertEqual(result.count(), 5)
        self.assertEqual(
            [ppbt.id for ppbt in result],
            [
                ppbt.id for ppbt in
                PaypalBlockTransaction.objects.filter(block__user=self.user)
            ]
        )
