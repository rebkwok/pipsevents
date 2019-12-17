import os
from datetime import datetime
from unittest.mock import patch

from model_bakery import baker

from django.contrib.auth.models import Group
from django.urls import reverse
from django.test import TestCase
from django.utils import timezone

from activitylog.models import ActivityLog

from booking.models import Ticket, TicketBooking
from booking.templatetags.bookingtags import temporary_banner
from booking.views import EventDetailView
from common.tests.helpers import TestSetupMixin, format_content


class BookingtagTests(TestSetupMixin, TestCase):

    def setUp(self):
        super(BookingtagTests, self).setUp()
        self.user.is_staff = True
        self.user.save()

    def tearDown(self):
        super().tearDown()
        env_vars = ['TEMP_BANNER', 'BANNER_START', 'BANNER_END']
        for var in env_vars:
            if var in os.environ:
                del os.environ[var]

    def _get_response(self, user, event, ev_type):
        url = reverse('booking:event_detail', args=[event.slug])
        request = self.factory.get(url)
        request.user = user
        view = EventDetailView.as_view()
        return view(request, slug=event.slug, ev_type=ev_type)

    def test_cancellation_format_tag_event_detail(self):
        """
        Test that cancellation period is formatted correctly
        """
        event = baker.make_recipe('booking.future_EV', cancellation_period=24)
        resp = self._get_response(self.user, event, 'event')
        resp.render()
        self.assertIn('24 hours', str(resp.content))

        event = baker.make_recipe('booking.future_EV', cancellation_period=25)
        resp = self._get_response(self.user, event, 'event')
        resp.render()
        self.assertIn('1 day and 1 hour', str(resp.content))

        event = baker.make_recipe('booking.future_EV', cancellation_period=48)
        resp = self._get_response(self.user, event, 'event')
        resp.render()
        self.assertIn('2 days', str(resp.content))

        event = baker.make_recipe('booking.future_EV', cancellation_period=619)
        resp = self._get_response(self.user, event, 'event')
        resp.render()
        self.assertIn('3 weeks, 4 days and 19 hours', str(resp.content))

        event = baker.make_recipe('booking.future_EV', cancellation_period=168)
        resp = self._get_response(self.user, event, 'event')
        resp.render()
        self.assertIn('1 week', str(resp.content))

        event = baker.make_recipe('booking.future_EV', cancellation_period=192)
        resp = self._get_response(self.user, event, 'event')
        resp.render()
        self.assertIn('1 week, 1 day and 0 hours', str(resp.content))

    def test_formatted_uk_date(self):
        # activitylog in BST
        baker.make(
            ActivityLog, log="Test log",
            timestamp=datetime(2016, 7, 1, 18, 0, tzinfo=timezone.utc)
        )
        # activitylog in GMT (same as UTC)
        baker.make(
            ActivityLog, log="Test log",
            timestamp=datetime(2016, 1, 1, 18, 0, tzinfo=timezone.utc)
        )

        self.client.login(username=self.user.username, password='test')

        resp = self.client.get(reverse('studioadmin:activitylog'))
        content = format_content(resp.rendered_content)

        self.assertIn("01 Jul 2016 19:00:00", content)
        self.assertIn("01 Jan 2016 18:00:00", content)

    def test_abbreviated_ticket_booking_references(self):
        tb = baker.make(
            TicketBooking, purchase_confirmed=True, paid=True
        )
        baker.make(Ticket, ticket_booking=tb)

        self.client.login(username=self.user.username, password='test')

        resp = self.client.get(
            reverse(
                'studioadmin:ticketed_event_bookings',
                kwargs={'slug':tb.ticketed_event.slug}
            )
        )
        self.assertEqual(len(tb.booking_reference), 22)
        content = format_content(resp.rendered_content)
        self.assertNotIn(tb.booking_reference, content)
        self.assertIn(tb.booking_reference[0:5] + '...', content)

    def test_format_block(self):
        Group.objects.get_or_create(name='instructors')
        user = baker.make_recipe('booking.user')
        block = baker.make_recipe('booking.block_5', user=user,)
        event = baker.make_recipe(
            'booking.future_PC', event_type=block.block_type.event_type
        )
        baker.make_recipe(
            'booking.booking', event=event, user=user, block=block
        )
        baker.make_recipe('booking.booking', block=block, _quantity=3)

        self.client.login(username=self.user.username, password='test')

        resp = self.client.get(reverse('studioadmin:event_register', args=[event.slug]))

        self.assertIn(
            '{} (1/5 left); exp 01 Mar 15'.format(event.event_type.subtype),
            resp.rendered_content
        )

    @patch('booking.templatetags.bookingtags.timezone')
    def test_temporary_banner_on(self, mock_tz):
        mock_tz.now.return_value = datetime(2015, 1, 3, tzinfo=timezone.utc)
        mock_tz.utc = timezone.utc

        os.environ['TEMP_BANNER'] = 'Banner text'
        os.environ['BANNER_START'] = '01-Jan-2015'
        os.environ['BANNER_END'] = '15-Jan-2015'

        banner = temporary_banner()
        self.assertCountEqual(
            banner,
            {'has_temporary_banner': True, 'temporary_banner': 'Banner text'}
        )

    @patch('booking.templatetags.bookingtags.timezone')
    def test_temporary_banner_off(self, mock_tz):
        mock_tz.now.return_value = datetime(2015, 1, 3, tzinfo=timezone.utc)
        mock_tz.utc = timezone.utc

        os.environ['TEMP_BANNER'] = 'Banner text'
        os.environ['BANNER_START'] = '04-Jan-2015'
        os.environ['BANNER_END'] = '15-Jan-2015'

        banner = temporary_banner()
        self.assertCountEqual(
            banner,
            {'has_temporary_banner': False}
        )

    @patch('booking.templatetags.bookingtags.timezone')
    def test_temporary_banner_no_start_date(self, mock_tz):
        mock_tz.now.return_value = datetime(2015, 1, 3, tzinfo=timezone.utc)
        mock_tz.utc = timezone.utc

        os.environ['TEMP_BANNER'] = 'Banner text'
        os.environ['BANNER_END'] = '15-Jan-2015'

        banner = temporary_banner()
        self.assertCountEqual(
            banner,
            {'has_temporary_banner': False}
        )

    @patch('booking.templatetags.bookingtags.timezone')
    def test_temporary_banner_no_end_date(self, mock_tz):
        mock_tz.now.return_value = datetime(2015, 1, 3, tzinfo=timezone.utc)
        mock_tz.utc = timezone.utc

        os.environ['TEMP_BANNER'] = 'Banner text'
        os.environ['BANNER_START'] = '01-Jan-2015'

        banner = temporary_banner()
        self.assertCountEqual(
            banner,
            {'has_temporary_banner': False}
        )