from django.test import TestCase
from model_mommy import mommy

from booking.forms import BookingCreateForm, BlockCreateForm
from booking.context_helpers import get_blocktypes_available_to_book


class BookingCreateFormTests(TestCase):

    def setUp(self):
        self.user = mommy.make_recipe('booking.user')
        self.event = mommy.make_recipe('booking.future_EV')
        self.blocktype = mommy.make_recipe('booking.blocktype5')

    def test_create_form(self):
        form_data = {'event': self.event.id}
        form = BookingCreateForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_create_form_with_block(self):
        form_data = {'event': self.event.id, 'block_type': self.blocktype}
        form = BookingCreateForm(data=form_data)
        self.assertTrue(form.is_valid())


class BlockCreateFormTests(TestCase):

    def setUp(self):
        self.user = mommy.make_recipe('booking.user')

    def test_create_form_with_available_block(self):

        block_type = mommy.make_recipe('booking.blocktype')
        mommy.make_recipe('booking.blocktype', _quantity=5)
        block = mommy.make_recipe(
            'booking.block', user=self.user, paid=True,
            block_type=block_type)
        form_data = {'block_type': block.block_type.id}
        form = BlockCreateForm(data=form_data)
        self.assertTrue(form.is_valid())