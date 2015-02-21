from django.test import TestCase
from model_mommy import mommy

from booking.forms import BookingCreateForm, BookingUpdateForm


class BookingCreateFormTests(TestCase):

    def setUp(self):
        self.user = mommy.make_recipe('booking.user')
        self.event = mommy.make_recipe('booking.future_EV')

    def test_create_form(self):
        form_data = {'event': self.event.id}
        form = BookingCreateForm(data=form_data)
        self.assertEqual(form.is_valid(), True)


class BookingUpdateFormTests(TestCase):

    def setUp(self):
        self.user = mommy.make_recipe('booking.user')
        self.booking = mommy.make_recipe('booking.booking')

    def test_create_form(self):
        form_data = {'paid': True}
        form = BookingUpdateForm(data=form_data)
        self.assertEqual(form.is_valid(), True)