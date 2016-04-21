from django.test import TestCase
from model_mommy import mommy

from booking.forms import BookingCreateForm, BlockCreateForm, \
    TicketPurchaseForm, BlockAdminForm, BookingAdminForm, \
    TicketBookingAdminForm, WaitingListUserAdminForm
from booking.models import Block, TicketBooking, Ticket


class BookingCreateFormTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = mommy.make_recipe('booking.user')
        cls.event = mommy.make_recipe('booking.future_EV')
        cls.blocktype = mommy.make_recipe('booking.blocktype5')

    def test_create_form(self):
        form_data = {'event': self.event.id}
        form = BookingCreateForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_create_form_with_block(self):
        form_data = {'event': self.event.id, 'block_type': self.blocktype}
        form = BookingCreateForm(data=form_data)
        self.assertTrue(form.is_valid())


class BlockCreateFormTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = mommy.make_recipe('booking.user')

    def test_create_form_with_available_block(self):

        block_type = mommy.make_recipe('booking.blocktype')
        mommy.make_recipe('booking.blocktype', _quantity=5)
        block = mommy.make_recipe(
            'booking.block', user=self.user, paid=True,
            block_type=block_type)
        form_data = {'block_type': block.block_type.id}
        form = BlockCreateForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_create_form_block_type_display(self):
        block_type = mommy.make_recipe(
            'booking.blocktype', event_type__subtype='Test', size=3
        )
        block_type1 = mommy.make_recipe(
            'booking.blocktype', event_type__subtype='Test 1', size=4,
            identifier='test'
        )
        form = BlockCreateForm()

        self.assertEqual(
            form.fields['block_type'].label_from_instance(block_type),
            'Test - quantity 3'

        )
        self.assertEqual(
            form.fields['block_type'].label_from_instance(block_type1),
            'Test 1 (test) - quantity 4'
        )


class TicketPurchaseFormTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = mommy.make_recipe('booking.user')

    def setUp(self):
        self.ticketed_event = mommy.make_recipe('booking.ticketed_event_max10')
        self.ticket_booking = mommy.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            purchase_confirmed=True,
        )

    def test_form_valid(self):
        form_data = {'quantity': 2}
        form = TicketPurchaseForm(
            data=form_data, ticketed_event=self.ticketed_event,
            ticket_booking=self.ticket_booking
        )
        self.assertTrue(form.is_valid())

    def test_quantity_choices(self):
        form = TicketPurchaseForm(
            ticketed_event=self.ticketed_event,
            ticket_booking=self.ticket_booking
        )
        self.assertEqual(self.ticketed_event.tickets_left(), 10)
        self.assertEqual(self.ticketed_event.max_tickets, 10)
        self.assertIsNone(self.ticketed_event.max_ticket_purchase)

        quantity_widget = form.fields['quantity'].widget

        # choices 1 - 10: max tickets, none bought yet
        choices = [(i, i) for i in range(1, 11)]
        choices.insert(0, (0, '------'))
        self.assertEqual(quantity_widget.choices, choices)

    def test_quantity_choices_max_ticket_purchase(self):
        self.ticketed_event.max_ticket_purchase = 5
        self.ticketed_event.save()
        form = TicketPurchaseForm(
            ticketed_event=self.ticketed_event,
            ticket_booking=self.ticket_booking
        )
        self.assertEqual(self.ticketed_event.tickets_left(), 10)
        self.assertEqual(self.ticketed_event.max_tickets, 10)
        self.assertEqual(self.ticketed_event.max_ticket_purchase, 5)

        quantity_widget = form.fields['quantity'].widget
        # choices 1 - 5: max tickets 10 but max single purchase is 5
        choices = [(i, i) for i in range(1, 6)]
        choices.insert(0, (0, '------'))
        self.assertEqual(quantity_widget.choices, choices)

    def test_quantity_choices_max_ticket_purchase_and_booked_tickets(self):
        self.ticketed_event.max_ticket_purchase = 5
        self.ticketed_event.save()
        new_booking = mommy.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            purchase_confirmed=True,
        )
        mommy.make(Ticket, ticket_booking=new_booking, _quantity=7)
        self.ticketed_event.save()
        form = TicketPurchaseForm(
            ticketed_event=self.ticketed_event,
            ticket_booking=self.ticket_booking
        )
        self.assertEqual(self.ticketed_event.tickets_left(), 3)
        self.assertEqual(self.ticketed_event.max_tickets, 10)
        self.assertEqual(self.ticketed_event.max_ticket_purchase, 5)

        quantity_widget = form.fields['quantity'].widget
        # choices 1 - 3: max single purchase is 5, but there are only 3 left
        choices = [(i, i) for i in range(1, 4)]
        choices.insert(0, (0, '------'))
        self.assertEqual(quantity_widget.choices, choices)

    def test_quantity_choices_no_max_ticket_purchase_or_max_tickets(self):
        self.ticketed_event.max_tickets = None
        self.ticketed_event.save()
        form = TicketPurchaseForm(
            ticketed_event=self.ticketed_event,
            ticket_booking=self.ticket_booking
        )
        self.assertEqual(self.ticketed_event.tickets_left(), 10000)
        self.assertIsNone(self.ticketed_event.max_tickets)
        self.assertIsNone(self.ticketed_event.max_ticket_purchase)

        quantity_widget = form.fields['quantity'].widget
        # choices 1 - 100
        choices = [(i, i) for i in range(1, 101)]
        choices.insert(0, (0, '------'))
        self.assertEqual(quantity_widget.choices, choices)

    def test_quantity_choices_with_booked_tickets(self):
        new_booking = mommy.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            purchase_confirmed=True,
        )
        mommy.make(Ticket, ticket_booking=new_booking, _quantity=8)
        form = TicketPurchaseForm(
            ticketed_event=self.ticketed_event,
            ticket_booking=self.ticket_booking
        )
        self.assertEqual(self.ticketed_event.tickets_left(), 2)
        self.assertEqual(self.ticketed_event.max_tickets, 10)
        self.assertIsNone(self.ticketed_event.max_ticket_purchase)

        quantity_widget = form.fields['quantity'].widget
        # choices = 1-2; 8 tickets bought on another booking, 2 left to purchase
        choices = [(i, i) for i in range(1, 3)]
        choices.insert(0, (0, '------'))
        self.assertEqual(quantity_widget.choices, choices)

    def test_quantity_choices_with_booked_tickets_on_same_ticket_booking(self):
        """
        tickets booked on the current ticket booking do not affect the choices
        (if user has booked 8 out of 10 max tickets, we want them to have the
        option to change it to e.g. 4, so don't want to limit it to 2)
        """
        mommy.make(Ticket, ticket_booking=self.ticket_booking, _quantity=8)
        form = TicketPurchaseForm(
            ticketed_event=self.ticketed_event,
            ticket_booking=self.ticket_booking
        )
        self.assertEqual(self.ticketed_event.tickets_left(), 2)
        self.assertEqual(self.ticketed_event.max_tickets, 10)
        self.assertIsNone(self.ticketed_event.max_ticket_purchase)

        quantity_widget = form.fields['quantity'].widget
        # choices = 1-10; 8 tickets booked on this booking, user can change
        # quantity to up to 10 still
        choices = [(i, i) for i in range(1, 11)]
        choices.insert(0, (0, '------'))
        self.assertEqual(quantity_widget.choices, choices)

    def test_quantity_choices_with_booked_unconfirmed_tickets_on_same_tb(self):
        """
        same quantity choices shoould be returned if the purchase is not
        yet confirmed
        """
        self.ticket_booking.purchase_confirmed = False
        self.ticket_booking.save()
        mommy.make(
            Ticket, ticket_booking=self.ticket_booking, _quantity=8
        )
        form = TicketPurchaseForm(
            ticketed_event=self.ticketed_event,
            ticket_booking=self.ticket_booking
        )
        # tickets left is 10 since this booking is unconfirmed
        self.assertEqual(self.ticketed_event.tickets_left(), 10)
        self.assertEqual(self.ticketed_event.max_tickets, 10)
        self.assertIsNone(self.ticketed_event.max_ticket_purchase)

        quantity_widget = form.fields['quantity'].widget
        # choices = 1-10; 8 tickets booked on this booking, user can change
        # quantity to up to 10 still
        choices = [(i, i) for i in range(1, 11)]
        choices.insert(0, (0, '------'))
        self.assertEqual(quantity_widget.choices, choices)

    def test_quantity_choices_with_booked_tickets_multiple_bookings(self):
        new_booking = mommy.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            purchase_confirmed=True
        )
        mommy.make(Ticket, ticket_booking=new_booking, _quantity=4)
        mommy.make(Ticket, ticket_booking=self.ticket_booking, _quantity=4)
        form = TicketPurchaseForm(
            ticketed_event=self.ticketed_event,
            ticket_booking=self.ticket_booking
        )
        self.assertEqual(self.ticketed_event.tickets_left(), 2)
        self.assertEqual(self.ticketed_event.max_tickets, 10)
        self.assertIsNone(self.ticketed_event.max_ticket_purchase)

        quantity_widget = form.fields['quantity'].widget
        # choices = 1-6; 4 tickets booked on another booking, 6 left altogether,
        # including the 4 already allocated to this booking
        choices = [(i, i) for i in range(1, 7)]
        choices.insert(0, (0, '------'))
        self.assertEqual(quantity_widget.choices, choices)

    def test_quantity_choices_with_booked_tickets_on_cancelled_booking(self):
        new_booking = mommy.make(
            TicketBooking, ticketed_event=self.ticketed_event,
            purchase_confirmed=True,
            cancelled=True
        )
        mommy.make(Ticket, ticket_booking=new_booking, _quantity=8)
        form = TicketPurchaseForm(
            ticketed_event=self.ticketed_event,
            ticket_booking=self.ticket_booking
        )
        self.assertEqual(self.ticketed_event.tickets_left(), 10)
        self.assertEqual(self.ticketed_event.max_tickets, 10)
        self.assertIsNone(self.ticketed_event.max_ticket_purchase)

        quantity_widget = form.fields['quantity'].widget
        # choices = 1-10; 8 tickets bought on another booking, but cancelled, so
        # still 10 left to book
        choices = [(i, i) for i in range(1, 11)]
        choices.insert(0, (0, '------'))
        self.assertEqual(quantity_widget.choices, choices)


class AdminFormsTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = mommy.make_recipe(
            'booking.user', first_name="c", last_name='b', username='a'
        )
        cls.user1 =  mommy.make_recipe(
           'booking.user', first_name="a", last_name='b', username='c'
        )
        cls.user2=  mommy.make_recipe(
           'booking.user', first_name="b", last_name='a', username='b'
        )

    def test_booking_admin_form_user_display(self):
       # check ordering of users - should be by first name (user1, user2, user)

       form = BookingAdminForm()
       userfield = form.fields['user']
       self.assertEqual(
           list(userfield.queryset.values_list('id', flat=True)),
           [self.user1.id, self.user2.id, self.user.id]
       )
       self.assertEqual(
           [ch[1] for ch in userfield.widget.choices],
           ['---------', 'a b (c)', 'b a (b)', 'c b (a)']
       )

    def test_block_shows_users_blocks_on_booking_admin_form(self):
        user = mommy.make_recipe('booking.user')
        block = mommy.make_recipe('booking.block_5', user=user)
        block1 = mommy.make_recipe('booking.block_10', user=user)
        mommy.make_recipe('booking.block_10')
        booking = mommy.make_recipe('booking.booking', user=user)

        form = BookingAdminForm(instance=booking)
        block_field = form.fields['block']

        self.assertEqual(Block.objects.count(), 3)
        self.assertEqual(block_field.queryset.count(), 2)
        self.assertEqual(
            [bl.id for bl in block_field.queryset],
            [block.id, block1.id]
        )

    def test_block_admin_form_user_display(self):
       # check ordering of users - should be by first name (user1, user2, user)
       form = BlockAdminForm()
       userfield = form.fields['user']
       self.assertEqual(
           list(userfield.queryset.values_list('id', flat=True)),
           [self.user1.id, self.user2.id, self.user.id]
       )

    def test_ticket_booking_admin_form_user_display(self):
       # check ordering of users - should be by first name (user1, user2, user)

       form = TicketBookingAdminForm()
       userfield = form.fields['user']
       self.assertEqual(
           list(userfield.queryset.values_list('id', flat=True)),
           [self.user1.id, self.user2.id, self.user.id]
       )

    def test_waiting_list_admin_form_user_display(self):
       # check ordering of users - should be by first name (user1, user2, user)

       form = WaitingListUserAdminForm()
       userfield = form.fields['user']
       self.assertEqual(
           list(userfield.queryset.values_list('id', flat=True)),
           [self.user1.id, self.user2.id, self.user.id]
       )
