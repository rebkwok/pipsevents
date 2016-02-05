from model_mommy import mommy

from django.contrib.admin.sites import AdminSite
from django.test import TestCase
from payments import helpers
from payments.admin import PaypalBookingTransactionAdmin, \
    PaypalBlockTransactionAdmin
from payments.models import PaypalBookingTransaction, PaypalBlockTransaction



class PaymentsAdminTests(TestCase):

    def test_paypal_booking_admin_display(self):
        user = mommy.make_recipe(
            'booking.user', first_name='Test', last_name='User')
        booking = mommy.make_recipe('booking.booking', user=user)
        pptrans = helpers.create_booking_paypal_transaction(
            booking.user, booking
        )

        ppbooking_admin = PaypalBookingTransactionAdmin(
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

        ppblock_admin = PaypalBlockTransactionAdmin(
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
