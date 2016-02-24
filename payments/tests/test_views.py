from model_mommy import mommy

from django.core.urlresolvers import reverse
from django.test import TestCase

from booking.tests.helpers import set_up_fb


class TestViews(TestCase):

    @classmethod
    def setUpTestData(cls):
        set_up_fb()

    def test_confirm_return(self):

        booking = mommy.make_recipe('booking.booking')

        url = reverse('payments:paypal_confirm')
        resp = self.client.post(
            url,
            {
                'custom': '{} {}'.format('booking', booking.id),
                'payment_status': 'paid',
                'item_name': booking.event.name
            }
        )
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context_data['obj_type'], 'booking')
        self.assertEquals(resp.context_data['obj'], booking)

        block = mommy.make_recipe('booking.block')

        resp = self.client.post(
            url,
            {
                'custom': '{} {}'.format('block', block.id),
                'payment_status': 'paid',
                'item_name': block
            }
        )
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context_data['obj_type'], 'block')
        self.assertEquals(resp.context_data['obj'], block)

        ticket_booking = mommy.make_recipe('booking.ticket_booking')

        resp = self.client.post(
            url,
            {
                'custom': '{} {}'.format('ticket_booking', ticket_booking.id),
                'payment_status': 'paid',
                'item_name': ticket_booking.ticketed_event.name
            }
        )
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context_data['obj_type'], 'ticket_booking')
        self.assertEquals(resp.context_data['obj'], ticket_booking)

    def test_confirm_return_with_unknown_obj(self):
        block = mommy.make_recipe('booking.block')
        url = reverse('payments:paypal_confirm')
        resp = self.client.post(
            url,
            {
                'custom': '{} {}'.format('other', block.id),
                'payment_status': 'paid',
                'item_name': block
            }
        )
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context_data['obj_unknown'], True)
        self.assertIn(
            'Everything is probably fine...',
            resp.rendered_content
        )

    def test_confirm_return_with_no_custom_field(self):
        booking = mommy.make_recipe('booking.booking')

        url = reverse('payments:paypal_confirm')
        resp = self.client.post(
            url,
            {
                'payment_status': 'paid',
            }
        )
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context_data['obj_unknown'], True)
        self.assertIn(
            'Everything is probably fine...',
            resp.rendered_content
        )


    def test_cancel_return(self):
        url = reverse('payments:paypal_cancel')
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
