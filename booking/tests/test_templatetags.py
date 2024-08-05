import os
from datetime import datetime
from datetime import timezone as dt_timezone

from unittest.mock import patch

from model_bakery import baker

from django.contrib.auth.models import Group
from django.urls import reverse
from django.test import TestCase

from accounts.models import DisclaimerContent
from activitylog.models import ActivityLog

from booking.models import Banner, Ticket, TicketBooking
from booking.templatetags.bookingtags import all_users_banner, new_users_banner
from booking.views import EventDetailView
from common.tests.helpers import TestSetupMixin, format_content


class BookingtagTests(TestSetupMixin, TestCase):

    def setUp(self):
        super(BookingtagTests, self).setUp()
        self.user.is_staff = True
        self.user.save()

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
            timestamp=datetime(2016, 7, 1, 18, 0, tzinfo=dt_timezone.utc)
        )
        # activitylog in GMT (same as UTC)
        baker.make(
            ActivityLog, log="Test log",
            timestamp=datetime(2016, 1, 1, 18, 0, tzinfo=dt_timezone.utc)
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

    def test_disclaimer_medical_info(self):
        Group.objects.get_or_create(name='instructors')
        self.client.login(username=self.user.username, password='test')
        user = baker.make_recipe('booking.user')
        event = baker.make_recipe('booking.future_PC')
        baker.make_recipe('booking.booking', event=event, user=user)

        resp = self.client.get(reverse('studioadmin:event_register', args=[event.slug]))
        assert '<span id="disclaimer" class="far fa-file-alt"></span> *' not in resp.rendered_content
        assert '<span id="disclaimer" class="fas fa-times"></span>' in resp.rendered_content
        disclaimer = baker.make_recipe(
            'booking.online_disclaimer', medical_conditions=True, medical_conditions_details="test", user=user,
            version=DisclaimerContent.current_version()
        )
        resp = self.client.get(reverse('studioadmin:event_register', args=[event.slug]))
        assert '<span id="disclaimer" class="far fa-file-alt"></span> *</a>' in resp.rendered_content
        assert '<span id="disclaimer" class="far fa-file-alt"></span></a>' not in resp.rendered_content

        disclaimer.delete()
        baker.make_recipe(
            'booking.online_disclaimer', user=user, medical_conditions=False, joint_problems=False, allergies=False,
            version=DisclaimerContent.current_version()
        )
        resp = self.client.get(reverse('studioadmin:event_register', args=[event.slug]))
        assert '<span id="disclaimer" class="far fa-file-alt"></span> *</a>' not in resp.rendered_content
        assert '<span id="disclaimer" class="far fa-file-alt"></span></a>' in resp.rendered_content

    def test_all_users_banner_no_banner(self):
        banner_output = all_users_banner({})
        assert banner_output == {}

        # Default still shown if in admin
        banner_output = all_users_banner({"studioadmin": True})
        assert banner_output == {
            'banner_content': 'Banner content here', 
            'banner_colour': 'info',
        }
    
    def test_new_users_banner_no_banner(self):
        banner_output = new_users_banner({})
        assert banner_output == {}

        # Default still shown if in admin
        banner_output = new_users_banner({"studioadmin": True})
        assert banner_output == {
            'banner_content': 'Banner content here', 
            'banner_colour': 'info',
    }
    
    @patch('booking.templatetags.bookingtags.timezone')
    def test_all_users_banner(self, mock_tz):
        mock_tz.now.return_value = datetime(2015, 1, 3, tzinfo=dt_timezone.utc)
        mock_tz.utc = dt_timezone.utc

        baker.make(
            Banner, 
            banner_type="banner_all", 
            start_datetime=datetime(2015, 1, 1, 10, 0),
            end_datetime=datetime(2015, 1, 15, 18, 0),
            content="Banner text"
        )

        # non-admin, within dates
        banner_output = all_users_banner({})
        assert banner_output == {
            'banner_content': 'Banner text', 
            'banner_colour': 'info',
            'banner_type': 'banner_all',
        }

        # not started yet
        mock_tz.now.return_value = datetime(2015, 1, 1, 9, 0, tzinfo=dt_timezone.utc)
        banner_output = all_users_banner({})
        assert banner_output == {}

        # But still shown if in admin
        banner_output = all_users_banner({"studioadmin": True})
        assert banner_output == {
            'banner_content': 'Banner text', 
            'banner_colour': 'info',
            'banner_type': 'banner_all',
        }

        # expired
        mock_tz.now.return_value = datetime(2015, 2, 1, 9, 0, tzinfo=dt_timezone.utc)
        banner_output = all_users_banner({})
        assert banner_output == {}

        # But still shown if in admin
        banner_output = all_users_banner({"studioadmin": True})
        assert banner_output == {
            'banner_content': 'Banner text', 
            'banner_colour': 'info',
            'banner_type': 'banner_all',
        }

    @patch('booking.templatetags.bookingtags.timezone')
    def test_new_users_banner(self, mock_tz):
        mock_tz.now.return_value = datetime(2015, 1, 3, tzinfo=dt_timezone.utc)
        mock_tz.utc = dt_timezone.utc

        # make sure the right banner is selected
        baker.make(
            Banner, 
            banner_type="banner_all", 
            start_datetime=datetime(2015, 1, 1, 10, 0),
            end_datetime=datetime(2015, 1, 15, 18, 0),
            content="Banner text"
        )
        baker.make(
            Banner, 
            banner_type="banner_new", 
            start_datetime=datetime(2015, 1, 1, 10, 0),
            end_datetime=datetime(2015, 1, 15, 18, 0),
            content="New banner text"
        )

        # non-admin, within dates
        banner_output = new_users_banner({})
        assert banner_output == {
            'banner_content': 'New banner text', 
            'banner_colour': 'info',
            'banner_type': 'banner_new',
        }

        # not started yet
        mock_tz.now.return_value = datetime(2015, 1, 1, 9, 0, tzinfo=dt_timezone.utc)
        banner_output = new_users_banner({})
        assert banner_output == {}

        # But still shown if in admin
        banner_output = new_users_banner({"studioadmin": True})
        assert banner_output == {
            'banner_content': 'New banner text', 
            'banner_colour': 'info',
            'banner_type': 'banner_new',
        }

        # expired
        mock_tz.now.return_value = datetime(2015, 2, 1, 9, 0, tzinfo=dt_timezone.utc)
        banner_output = new_users_banner({})
        assert banner_output == {}

        # But still shown if in admin
        banner_output = new_users_banner({"studioadmin": True})
        assert banner_output == {
            'banner_content': 'New banner text', 
            'banner_colour': 'info',
            'banner_type': 'banner_new',
        }

    