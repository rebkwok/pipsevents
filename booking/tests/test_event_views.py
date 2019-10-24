import os

from unittest.mock import patch

from model_bakery import baker
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

from django.contrib.auth.models import User
from django.urls import reverse
from django.test import TestCase
from django.contrib.auth.models import Permission
from django.utils import timezone

from accounts.models import PrintDisclaimer, OnlineDisclaimer, \
    DataPrivacyPolicy
from accounts.utils import has_active_data_privacy_agreement

from booking.models import Event, BlockVoucher, Booking, EventVoucher
from booking.views import EventListView, EventDetailView
from common.tests.helpers import TestSetupMixin, format_content, \
    make_data_privacy_agreement


class EventListViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(EventListViewTests, cls).setUpTestData()
        cls.events = baker.make_recipe('booking.future_EV', _quantity=3)
        cls.poleclasses = baker.make_recipe('booking.future_PC', _quantity=3)
        baker.make_recipe('booking.future_CL', _quantity=3)
        cls.url = reverse('booking:events')
        cls.lessons_url = reverse('booking:lessons')

    def setUp(self):
        super().setUp()
        self.client.login(username=self.user.username, password='test')

    def tearDown(self):
        sale_env_vars = ['SALE_ON', 'SALE_OFF', 'SALE_CODE', 'SALE_TITLE']
        for var in sale_env_vars:
            if var in os.environ:
                del os.environ[var]

    def test_event_list(self):
        """
        Test that only events are listed (workshops and other events)
        """
        self.client.logout()
        resp = self.client.get(self.url)

        self.assertEquals(Event.objects.all().count(), 9)
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context['events'].count(), 3)

    def test_event_list_logged_in_no_data_protection_policy(self):
        DataPrivacyPolicy.objects.all().delete()
        user = User.objects.create_user(
            username='testnodp', email='testnodp@test.com', password='test'
        )
        baker.make(PrintDisclaimer, user=user)
        self.assertFalse(has_active_data_privacy_agreement(user))

        self.assertTrue(
            self.client.login(username=user.username, password='test')
        )
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

        DataPrivacyPolicy.objects.create(content='Foo')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(
            reverse('profile:data_privacy_review') + '?next=/events/',
            resp.url
        )

        make_data_privacy_agreement(user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_event_list_past_event(self):
        """
        Test that past events is not listed
        """
        baker.make_recipe('booking.past_event')
        # check there are now 4 events
        self.assertEquals(Event.objects.all().count(), 10)
        resp = self.client.get(self.url)

        # event listing should still only show future events
        self.assertEquals(resp.context['events'].count(), 3)

    def test_event_list_with_anonymous_user(self):
        """
        Test that no booked_events in context
        """
        self.client.logout()
        resp = self.client.get(self.url)

        # event listing should still only show future events
        self.assertFalse('booked_events' in resp.context)

    def test_event_list_with_logged_in_user(self):
        """
        Test that booked_events in context
        """
        resp = self.client.get(self.url)
        self.assertTrue('booked_events' in resp.context_data)

    def test_event_list_with_booked_events(self):
        """
        test that booked events are shown on listing
        """
        resp = self.client.get(self.url)
        # check there are no booked events yet
        self.assertEquals(len(resp.context_data['booked_events']), 0)

        # create a booking for this user
        event = self.events[0]
        baker.make_recipe('booking.booking', user=self.user, event=event)
        resp = self.client.get(self.url)
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(len(booked_events), 1)
        self.assertTrue(event.id in booked_events)

    def test_event_list_booked_paid_events(self):
        """
        test that booked events are shown on listing
        """
        event = self.events[0]
        # create a booking for this user
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event,
            paid=True, payment_confirmed=True
        )
        resp = self.client.get(self.url)
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(len(booked_events), 1)
        self.assertTrue(event.id in booked_events)
        self.assertNotIn('pay_button', resp.rendered_content)

        # unpaid booking
        booking.paid = False
        booking.payment_confirmed = False
        booking.save()
        resp = self.client.get(self.url)
        self.assertIn('pay_button', resp.rendered_content)

    def test_event_list_shows_only_current_user_bookings(self):
        """
        Test that only user's booked events are shown as booked
        """
        resp = self.client.get(self.url)
        # check there are no booked events yet
        self.assertEquals(len(resp.context_data['booked_events']), 0)

        # create booking for this user
        event = self.events[0]
        baker.make_recipe('booking.booking', user=self.user, event=event)
        # create booking for another user, different event
        user1 = baker.make_recipe('booking.user')
        event1 = self.events[1]
        baker.make_recipe('booking.booking', user=user1, event=event1)

        # check only event1 shows in the booked events
        resp = self.client.get(self.url)
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(Booking.objects.all().count(), 2)
        self.assertEquals(len(booked_events), 1)
        self.assertTrue(event.id in booked_events)

    def test_filter_events(self):
        """
        Test that we can filter the classes by name
        """
        baker.make_recipe('booking.future_EV', name='test_name', _quantity=3)
        baker.make_recipe('booking.future_EV', name='test_name1', _quantity=4)

        resp = self.client.get(self.url, {'name': 'test_name'})
        self.assertEquals(resp.context['events'].count(), 3)

    def test_pole_practice_context_without_permission(self):
        Event.objects.all().delete()
        pp_event_type = baker.make_recipe('booking.event_type_OC', subtype="Pole practice")
        baker.make_recipe('booking.future_CL', event_type=pp_event_type)

        user = User.objects.create_user(username='test1', password='test1')
        baker.make(PrintDisclaimer, user=user)
        make_data_privacy_agreement(user)
        self.client.login(username='test1', password='test1')
        response = self.client.get(self.lessons_url)
        response.render()
        self.assertIn('N/A - see details', str(response.content))
        self.assertNotIn('book_button', str(response.content))
        self.assertNotIn('join_waiting_list_button', str(response.content))
        self.assertNotIn('leave_waiting_list_button', str(response.content))

    def test_pole_practice_context_with_permission(self):
        Event.objects.all().delete()
        pp_event_type = baker.make_recipe('booking.event_type_OC', subtype="Pole practice")
        baker.make_recipe('booking.future_CL', event_type=pp_event_type)

        user = User.objects.create_user(username='test1', password='test1')
        make_data_privacy_agreement(user)
        perm = Permission.objects.get(codename='is_regular_student')
        user.user_permissions.add(perm)
        user.save()
        baker.make(PrintDisclaimer, user=user)
        self.client.login(username='test1', password='test1')
        response = self.client.get(self.lessons_url)
        response.render()
        self.assertIn('book_button', str(response.content))
        self.assertNotIn('join_waiting_list_button', str(response.content))
        self.assertNotIn('leave_waiting_list_button', str(response.content))

    def test_cancelled_events_are_not_listed(self):
        Event.objects.all().delete()
        baker.make_recipe('booking.future_CL', cancelled=True)
        response = self.client.get(self.lessons_url)
        self.assertEquals(Event.objects.count(), 1)
        self.assertEquals(response.context_data['events'].count(), 0)

    @patch('booking.templatetags.bookingtags.timezone')
    def test_sale_message_template_tag(self, mock_tz):
        mock_tz.now.return_value = datetime(2015, 1, 3, tzinfo=timezone.utc)
        mock_tz.utc = timezone.utc

        os.environ['SALE_ON'] = '01-Jan-2015'
        os.environ['SALE_OFF'] = '15-Jan-2015'
        response = self.client.get(self.url)

        # no valid voucher
        self.assertNotIn('Use code', response.rendered_content)

        # with a sale title
        os.environ['SALE_TITLE'] = 'Test sale now on'
        response = self.client.get(self.url)
        self.assertIn('TEST SALE NOW ON', response.rendered_content)

    @patch('booking.templatetags.bookingtags.timezone')
    def test_sale_message_template_tag_sale_off(self, mock_tz):
        mock_tz.now.return_value = datetime(2015, 1, 3, tzinfo=timezone.utc)
        mock_tz.utc = timezone.utc

        os.environ['SALE_ON'] = '04-Jan-2015'
        os.environ['SALE_OFF'] = '15-Jan-2015'
        os.environ['SALE_TITLE'] = 'Sale now on'
        resp = self.client.get(self.url)

        self.assertNotIn('SALE NOW ON', resp.rendered_content)

    @patch('booking.templatetags.bookingtags.timezone')
    @patch('booking.models.timezone')
    def test_sale_message_template_tag_voucher_code(self, mock_tz, mock_tz1):
        mock_tz.now.return_value = datetime(2015, 1, 3, tzinfo=timezone.utc)
        mock_tz.utc = timezone.utc

        mock_tz1.now.return_value = datetime(2015, 1, 3, tzinfo=timezone.utc)
        mock_tz1.utc=timezone.utc

        voucher = baker.make(
            EventVoucher, code='testcode',
            start_date=datetime(2015, 1, 1, tzinfo=timezone.utc),
            expiry_date=datetime(2015, 1, 15, tzinfo=timezone.utc)
        )
        os.environ['SALE_ON'] = '01-Jan-2015'
        os.environ['SALE_OFF'] = '15-Jan-2015'
        os.environ['SALE_TITLE'] = 'Sale now on'
        os.environ['SALE_DESCRIPTION'] = 'Classes are on sale!'

        resp = self.client.get(self.url)
        self.assertIn('SALE NOW ON', resp.rendered_content)
        self.assertIn('Classes are on sale!', resp.rendered_content)

        # valid code but no env var set
        self.assertFalse(voucher.has_expired)
        self.assertTrue(voucher.has_started)
        self.assertNotIn('Use code testcode', resp.rendered_content)

        # set env var
        os.environ['SALE_CODE'] = 'testcode'
        resp = self.client.get(self.url)
        self.assertIn('Use code testcode', resp.rendered_content)

    @patch('booking.templatetags.bookingtags.timezone')
    @patch('booking.models.timezone')
    def test_sale_message_template_tag_block_voucher_code(self, mock_tz, mock_tz1):
        mock_tz.now.return_value = datetime(2015, 1, 3, tzinfo=timezone.utc)
        mock_tz.utc = timezone.utc

        mock_tz1.now.return_value = datetime(2015, 1, 3, tzinfo=timezone.utc)
        mock_tz1.utc=timezone.utc

        voucher = baker.make(
            BlockVoucher, code='block_testcode',
            start_date=datetime(2015, 1, 1, tzinfo=timezone.utc),
            expiry_date=datetime(2015, 1, 15, tzinfo=timezone.utc)
        )
        os.environ['SALE_ON'] = '01-Jan-2015'
        os.environ['SALE_OFF'] = '15-Jan-2015'
        os.environ['SALE_TITLE'] = 'Sale now on'
        os.environ['SALE_DESCRIPTION'] = 'Classes are on sale!'
        os.environ['SALE_CODE'] = 'block_testcode'

        resp = self.client.get(self.url)
        self.assertIn('SALE NOW ON', resp.rendered_content)
        self.assertIn('Classes are on sale!', resp.rendered_content)

        self.assertFalse(voucher.has_expired)
        self.assertTrue(voucher.has_started)
        self.assertIn('Use code block_testcode', resp.rendered_content)

    @patch('booking.templatetags.bookingtags.timezone')
    @patch('booking.models.timezone')
    def test_sale_message_template_tag_expired_voucher_code(
            self, mock_tz, mock_tz1
    ):
        mock_tz.now.return_value = datetime(2015, 1, 3, tzinfo=timezone.utc)
        mock_tz.utc = timezone.utc

        mock_tz1.now.return_value = datetime(2015, 1, 3, tzinfo=timezone.utc)
        mock_tz1.utc=timezone.utc

        voucher = baker.make(
            EventVoucher, code='testcode',
            start_date=datetime(2014, 1, 1, tzinfo=timezone.utc),
            expiry_date=datetime(2014, 1, 15, tzinfo=timezone.utc)
        )
        os.environ['SALE_ON'] = '01-Jan-2015'
        os.environ['SALE_OFF'] = '15-Jan-2015'
        os.environ['SALE_CODE'] = 'testcode'
        os.environ['SALE_TITLE'] = 'SALE NOW ON'

        resp = self.client.get(self.url)
        self.assertIn('SALE NOW ON', resp.rendered_content)

        self.assertTrue(voucher.has_expired)
        self.assertTrue(voucher.has_started)
        self.assertNotIn('Use code testcode', resp.rendered_content)

    @patch('booking.templatetags.bookingtags.timezone')
    @patch('booking.models.timezone')
    def test_sale_message_template_tag_no_voucher_code(
            self, mock_tz, mock_tz1
    ):
        mock_tz.now.return_value = datetime(2015, 1, 3, tzinfo=timezone.utc)
        mock_tz.utc = timezone.utc

        mock_tz1.now.return_value = datetime(2015, 1, 3, tzinfo=timezone.utc)
        mock_tz1.utc=timezone.utc

        os.environ['SALE_ON'] = '01-Jan-2015'
        os.environ['SALE_OFF'] = '15-Jan-2015'
        os.environ['SALE_CODE'] = 'testcode'
        os.environ['SALE_TITLE'] = 'SALE NOW ON'

        resp = self.client.get(self.url)
        self.assertIn('SALE NOW ON', resp.rendered_content)
        self.assertNotIn('Use code testcode', resp.rendered_content)

    @patch('booking.templatetags.bookingtags.timezone')
    @patch('booking.models.timezone')
    def test_sale_message_template_tag_not_started_voucher_code(
            self, mock_tz, mock_tz1
    ):
        mock_tz.now.return_value = datetime(2015, 1, 3, tzinfo=timezone.utc)
        mock_tz.utc = timezone.utc

        mock_tz1.now.return_value = datetime(2015, 1, 3, tzinfo=timezone.utc)
        mock_tz1.utc=timezone.utc

        voucher = baker.make(
            EventVoucher, code='testcode',
            start_date=datetime(2016, 1, 1, tzinfo=timezone.utc),
            expiry_date=datetime(2016, 1, 15, tzinfo=timezone.utc)
        )
        os.environ['SALE_ON'] = '01-Jan-2015'
        os.environ['SALE_OFF'] = '15-Jan-2015'
        os.environ['SALE_CODE'] = 'testcode'
        os.environ['SALE_TITLE'] = 'SALE NOW ON'

        resp = self.client.get(self.url)
        self.assertIn('SALE NOW ON', resp.rendered_content)

        self.assertFalse(voucher.has_expired)
        self.assertFalse(voucher.has_started)
        self.assertNotIn('Use code testcode', resp.rendered_content)

    def test_users_disclaimer_status_in_context(self):
        user = User.objects.create_user(username='test1', password='test1')
        make_data_privacy_agreement(user)
        self.client.login(username='test1', password='test1')
        resp = self.client.get(self.url)
        # user has no disclaimer
        self.assertFalse(resp.context_data.get('disclaimer'))
        self.assertIn(
            'Please note that you will need to complete a disclaimer form '
            'before booking',
            format_content(resp.rendered_content)
        )

        # expired disclaimer
        disclaimer = baker.make_recipe(
           'booking.online_disclaimer', user=user,
            date=datetime(2015, 2, 1, tzinfo=timezone.utc)
        )

        self.assertFalse(disclaimer.is_active)
        resp = self.client.get(self.url)
        self.assertNotIn(
            'Get a new block!', format_content(resp.rendered_content)
        )
        self.assertIn(
            'Your disclaimer has expired. Please review and confirm your '
            'information before booking.',
            format_content(resp.rendered_content)
        )

        baker.make_recipe('booking.online_disclaimer', user=user)
        resp = self.client.get(self.url)
        self.assertTrue(resp.context_data.get('disclaimer'))
        self.assertNotIn(
            'Your disclaimer has expired. Please review and confirm your '
            'information before booking.',
            format_content(resp.rendered_content)
        )

        OnlineDisclaimer.objects.all().delete()
        baker.make(PrintDisclaimer, user=user)
        resp = self.client.get(self.url)
        self.assertTrue(resp.context_data.get('disclaimer'))
        self.assertNotIn(
            'Please note that you will need to complete a disclaimer form '
            'before booking',
            format_content(resp.rendered_content)
        )

    @patch('booking.views.event_views.timezone')
    def test_event_list_formatting(self, mock_tz):
        """
        Test that events are coloured on alt days
        """
        # mock now to make sure our events are in the future for the test
        mock_tz.now.return_value = datetime(2017, 3, 19, tzinfo=timezone.utc)
        events = Event.objects.filter(event_type__event_type='EV')
        ev1 = events[0]
        ev2 = events[1]
        ev3 = events[2]
        # Mon
        ev1.date = datetime(2017, 3, 20, 10, 0, tzinfo=timezone.utc)
        ev1.save()
        # Tue
        ev2.date = datetime(2017, 3, 21, 10, 0, tzinfo=timezone.utc)
        ev2.save()
        # Wed
        ev3.date = datetime(2017, 3, 22, 10, 0, tzinfo=timezone.utc)
        ev3.save()

        resp = self.client.get(self.url)
        # Mon and Wed events are shaded, on the All locations and specific
        # location tabs
        self.assertEqual(
            resp.rendered_content.count('table-shaded'), 4
        )

    def test_event_list_tab_parameter(self):
        """
        Test that events are coloured on alt days
        """
        events = Event.objects.filter(event_type__event_type='EV')
        ev = events[0]
        ev.location = "Davidson's Mains"
        ev.save()

        url = reverse('booking:events')
        resp = self.client.get(self.url)

        # 3 loc events, 1 for all and 1 for each location
        self.assertEqual(
            len(resp.context_data['location_events']), 3
        )
        # tab 0 by default
        self.assertEqual(resp.context_data['tab'], '0')
        # tab 0 is active and open by default
        self.assertIn(
            '<div class="tab-pane fade active in" id="tab0">',
            resp.rendered_content
        )

        url += '?tab=1'
        resp = self.client.get(url)
        self.assertEqual(resp.context_data['tab'], '1')
        self.assertIn(
            '<div class="tab-pane fade active in" id="tab1">',
            resp.rendered_content
        )
        self.assertNotIn(
            '<div class="tab-pane fade active in" id="tab0">',
            resp.rendered_content
        )

    def test_event_list_default_pagination(self):
        # make enough events that they will paginate
        # total 31 (3 PC and 3 OC created in setup, plus 25 here), paginates by 30
        baker.make_recipe('booking.future_PC', _quantity=25)
        url = reverse('booking:lessons')
        resp = self.client.get(url)

        # 2 loc events, 1 for all and 1 for Beaverbank. None for DMs because there are no events there
        self.assertEqual(
            len(resp.context_data['location_events']), 2
        )
        # Queryset contains first 30
        self.assertEqual(
            len(resp.context_data['location_events'][0]['queryset']), 30
        )
        self.assertEqual(
            len(resp.context_data['location_events'][1]['queryset']), 30
        )

        # make some classes at second location
        baker.make_recipe('booking.future_PC', location="Davidson's Mains", _quantity=32)
        resp = self.client.get(url)

        # Queryset contains first 30
        self.assertEqual(
            len(resp.context_data['location_events'][0]['queryset']), 30
        )
        self.assertEqual(
            len(resp.context_data['location_events'][1]['queryset']), 30
        )
        self.assertEqual(
            len(resp.context_data['location_events'][2]['queryset']), 30
        )

    def test_event_list_default_pagination_with_page(self):
        # make enough events that they will paginate
        # total 31 (3 PC and 3 OC created in setup, plus 25 here), paginates by 30
        baker.make_recipe('booking.future_PC', _quantity=25)
        # make some classes at second location
        baker.make_recipe('booking.future_PC', location="Davidson's Mains", _quantity=10)

        # with specified page only, defaults to show all
        url = reverse('booking:lessons') + '?page=2'
        resp = self.client.get(url)
        # Queryset contains page 2 objs for all; 41 in all, paginated 30
        self.assertEqual(
            len(resp.context_data['location_events'][0]['queryset']), 11
        )
        self.assertEqual(
            resp.context_data['location_events'][0]['queryset'].number, 2
        )
        # pagination for non-specified tabs defaults to 1
        self.assertEqual(
            len(resp.context_data['location_events'][1]['queryset']), 30
        )
        self.assertEqual(
            resp.context_data['location_events'][1]['queryset'].number, 1
        )
        self.assertEqual(
            len(resp.context_data['location_events'][2]['queryset']), 10
        )
        self.assertEqual(
            resp.context_data['location_events'][2]['queryset'].number, 1
        )

        # with tab
        url = reverse('booking:lessons') + '?page=2&tab=1'
        resp = self.client.get(url)
        # Queryset contains page 2 objs for tab 1 only
        # tab 1 = beaverbank, 31 objs total
        self.assertEqual(
            len(resp.context_data['location_events'][0]['queryset']), 30
        )
        self.assertEqual(
            resp.context_data['location_events'][0]['queryset'].number, 1
        )
        self.assertEqual(
            len(resp.context_data['location_events'][1]['queryset']), 1
        )
        self.assertEqual(
            resp.context_data['location_events'][1]['queryset'].number, 2
        )
        self.assertEqual(
            len(resp.context_data['location_events'][2]['queryset']), 10
        )
        self.assertEqual(
            resp.context_data['location_events'][2]['queryset'].number, 1
        )

        # page out of range, defaults to last page
        url = reverse('booking:lessons') + '?page=10'
        resp = self.client.get(url)
        self.assertEqual(
            len(resp.context_data['location_events'][0]['queryset']), 11
        )
        self.assertEqual(
            resp.context_data['location_events'][0]['queryset'].number, 2
        )

        # page not an int, defaults to 1
        url = reverse('booking:lessons') + '?page=foo'
        resp = self.client.get(url)
        # Queryset contains page 2 objs for all
        self.assertEqual(
            len(resp.context_data['location_events'][0]['queryset']), 30
        )
        self.assertEqual(
            resp.context_data['location_events'][1]['queryset'].number, 1
        )

        # tab not an int, defaults to show specified page on index 0 (all), page 1 on the rest
        url = reverse('booking:lessons') + '?page=2&tab=foo'
        resp = self.client.get(url)
        # Queryset contains page 2 objs for all
        self.assertEqual(
            resp.context_data['location_events'][0]['queryset'].number, 2
        )
        # Queryset contains page 1 objs for non-specified tabs
        self.assertEqual(
            resp.context_data['location_events'][1]['queryset'].number, 1
        )


class EventDetailViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(EventDetailViewTests, cls).setUpTestData()
        baker.make_recipe('booking.future_PC', _quantity=3)
        baker.make_recipe('booking.future_CL', _quantity=3)

    def setUp(self):
        super(EventDetailViewTests, self).setUp()
        self.event = baker.make_recipe('booking.future_EV')

    def _get_response(self, user, event, ev_type):
        url = reverse('booking:event_detail', args=[event.slug])
        request = self.factory.get(url)
        request.user = user
        view = EventDetailView.as_view()
        return view(request, slug=event.slug, ev_type=ev_type)

    def test_login_required(self):
        """
        test that page redirects if there is no user logged in
        """
        url = reverse('booking:event_detail', kwargs={'slug': self.event.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

    def test_with_logged_in_user(self):
        """
        test that page loads if there user is available
        """
        resp = self._get_response(self.user, self.event, 'event')
        self.assertEqual(resp.status_code, 200)
        self.assertEquals(resp.context_data['type'], 'event')

    def test_with_booked_event(self):
        """
        Test that booked event is shown as booked
        """
        #create a booking for this event and user
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=self.event, paid=True,
            payment_confirmed=True
        )
        resp = self._get_response(self.user, self.event, 'event')
        self.assertTrue(resp.context_data['booked'])
        self.assertEquals(resp.context_data['booking_info_text'],
                          'You have booked for this workshop/event.')
        self.assertNotIn('pay_button', resp.rendered_content)

        # make booking unpaid
        booking.paid = False
        booking.payment_confirmed = False
        booking.save()
        resp = self._get_response(self.user, self.event, 'event')
        self.assertTrue(resp.context_data['booked'])
        self.assertEquals(resp.context_data['booking_info_text'],
                          'You have booked for this workshop/event.')
        self.assertIn('pay_button', resp.rendered_content)

    def test_with_booked_event_for_different_user(self):
        """
        Test that the event is not shown as booked if the current user has
        not booked it
        """
        user1 = baker.make_recipe('booking.user')
        #create a booking for this event and a different user
        baker.make_recipe('booking.booking', user=user1, event=self.event)

        resp = self._get_response(self.user, self.event,'event')
        self.assertFalse('booked' in resp.context_data)
        self.assertEquals(resp.context_data['booking_info_text'], '')

    def test_pole_practice_context_without_permission(self):
        pp_event_type = baker.make_recipe('booking.event_type_OC', subtype="Pole practice")
        pole_practice = baker.make_recipe('booking.future_CL', event_type=pp_event_type)

        user = baker.make_recipe('booking.user')
        make_data_privacy_agreement(user)
        baker.make(PrintDisclaimer, user=user)

        response = self._get_response(user, pole_practice, 'lesson')
        response.render()
        self.assertIn('unbookable_pole_practice', response.context_data)
        self.assertTrue(response.context_data['unbookable_pole_practice'])
        self.assertFalse(response.context_data['bookable'])
        self.assertNotIn('book_button_disabled', str(response.content))
        self.assertNotIn('book_button', str(response.content))
        self.assertNotIn('join_waiting_list_button', str(response.content))
        self.assertNotIn('leave_waiting_list_button', str(response.content))

    def test_pole_practice_context_with_permission(self):
        pp_event_type = baker.make_recipe('booking.event_type_OC', subtype="Pole practice")
        pole_practice = baker.make_recipe('booking.future_CL', event_type=pp_event_type)

        user = baker.make_recipe('booking.user')
        make_data_privacy_agreement(user)
        perm = Permission.objects.get(codename='is_regular_student')
        user.user_permissions.add(perm)
        user.save()
        baker.make(PrintDisclaimer, user=user)

        response = self._get_response(user, pole_practice, 'lesson')
        response.render()
        self.assertNotIn('unbookable_pole_practice', response.context_data)
        self.assertTrue(response.context_data['bookable'])
        self.assertNotIn('book_button_disabled', str(response.content))
        self.assertIn('book_button', str(response.content))
        self.assertNotIn('join_waiting_list_button', str(response.content))
        self.assertNotIn('leave_waiting_list_button', str(response.content))

    def test_payment_due_information_displayed_payment_due_date(self):
        """
        For not cancelled future events, show payment due date/time
        Payment open and payment due date --> show payment due date
        Payment open and time allowed --> show hours allowed
        """
        self.event.cost = 10
        self.event.advance_payment_required = True
        self.event.payment_due_date = timezone.now() + timedelta(15)
        self.event.payment_open = True
        self.event.save()

        self.assertTrue(self.event.allow_booking_cancellation)
        self.assertTrue(self.event.can_cancel())

        resp = self._get_response(self.user, self.event, 'event')
        soup = BeautifulSoup(resp.rendered_content, 'html.parser')
        content = soup.text

        # show text for payment due date, but not any for payment time allowed
        # or cancellation due date
        self.assertIn('Payment is due by', content)
        self.assertNotIn(
            'Once booked, your space will be held for', content
        )
        self.assertNotIn('(payment due ', content)

        self.event.payment_time_allowed = 4
        self.event.save()
        # payment due date overrides payment time allowed; if both are set, use
        # the due date
        resp = self._get_response(self.user, self.event, 'event')
        soup = BeautifulSoup(resp.rendered_content, 'html.parser')
        content = soup.text

        self.assertIn('Payment is due by', content)
        self.assertNotIn(
            'Once booked, your space will be held for', content
        )
        self.assertNotIn('(payment due ', content)

    def test_payment_due_information_displayed_payment_time(self):
        """
        For not cancelled future events, show payment due date/time
        Payment open and payment due date --> show payment due date
        Payment open and time allowed --> show hours allowed
        """
        self.event.cost = 10
        self.event.advance_payment_required = True
        self.event.payment_time_allowed = 6
        self.event.payment_open = True
        self.event.save()

        self.assertTrue(self.event.allow_booking_cancellation)
        self.assertTrue(self.event.can_cancel())

        resp = self._get_response(self.user, self.event, 'event')
        soup = BeautifulSoup(resp.rendered_content, 'html.parser')
        content = soup.text

        # show text for payment time allowed, but not any for payment due date
        # or cancellation due date
        self.assertNotIn('Payment is due by', content)
        self.assertIn(
            'Once booked, your space will be held for 6 hours', content
        )
        self.assertNotIn('(payment due ', content)

    def test_payment_due_information_displayed_cancellation_period(self):
        """
        For not cancelled future events, show payment due date/time
        Payment open and payment due date --> show payment due date
        Payment open and time allowed --> show hours allowed
        """
        self.event.cost = 10
        self.event.payment_open = True
        self.event.advance_payment_required = True
        self.event.save()

        self.assertTrue(self.event.allow_booking_cancellation)
        self.assertTrue(self.event.can_cancel())

        resp = self._get_response(self.user, self.event, 'event')
        soup = BeautifulSoup(resp.rendered_content, 'html.parser')
        content = soup.text

        # show text for cancellation due date, but not any for payment due date
        # or payment time allowed
        self.assertNotIn('Payment is due by', content)
        self.assertNotIn( 'Once booked, your space will be held for', content)
        self.assertIn('(payment due ', content)

    def test_cancellation_information_displayed_cancellation_period(self):
        """
        For not cancelled future events, show cancellation info
        If booking cancellation allowed, show cancellation period if there
        is one
        No payment_due_date or payment_time_allowed --> show due date with
        cancellation period
        If booking cancellation not allowed, show nonrefundable message
        """
        self.event.cost = 10
        self.event.advance_payment_required = True
        self.event.payment_open = True
        self.event.save()

        self.assertTrue(self.event.allow_booking_cancellation)
        self.assertEqual(self.event.cancellation_period, 24)

        resp = self._get_response(self.user, self.event, 'event')
        soup = BeautifulSoup(resp.rendered_content, 'html.parser')
        content = soup.text
        # show cancellation period and due date text
        self.assertIn(
            'Cancellation is allowed up to 24 hours prior to the workshop/event',
            content
        )
        self.assertIn('(payment due ', content)

    def test_cancellation_information_displayed_cancellation_not_allowed(self):
        """
        For not cancelled future events, show cancellation info
        If booking cancellation allowed, show cancellation period if there
        is one
        No payment_due_date or payment_time_allowed --> show due date with
        cancellation period
        If booking cancellation not allowed, show nonrefundable message
        """
        self.event.cost = 10
        self.event.advance_payment_required = True
        self.event.payment_open = True
        self.event.allow_booking_cancellation = False
        self.event.save()

        self.assertEqual(self.event.cancellation_period, 24)

        resp = self._get_response(self.user, self.event, 'event')
        soup = BeautifulSoup(resp.rendered_content, 'html.parser')
        content = soup.text
        # don't show cancellation period and due date text
        self.assertNotIn(
            'Cancellation is allowed up to 24 hours prior to the event ',
            content
        )
        self.assertNotIn('(payment due ', content)
        self.assertIn(
            'Bookings are final and non-refundable; if you cancel your booking '
            'you will not be eligible for any refund or credit.', content
        )

    def test_autocancelled_booking(self):
        self.event.cost = 10
        self.event.advance_payment_required = True
        self.event.save()

        baker.make(
            Booking, user=self.user, event=self.event, status='CANCELLED',
            auto_cancelled=True
        )
        resp = self._get_response(self.user, self.event, 'event')
        self.assertIn('auto_cancelled', resp.context_data.keys())
        self.assertIn('book_button_autocancel_disabled', resp.rendered_content)


class LessonListViewTests(TestSetupMixin, TestCase):
    """
    Test EventListView with lessons; reuses the event templates and context
    data helpers
    """
    @classmethod
    def setUpTestData(cls):
        super(LessonListViewTests, cls).setUpTestData()
        baker.make_recipe('booking.future_EV', cost=5, _quantity=1)
        baker.make_recipe('booking.future_PC', cost=5, _quantity=3)
        baker.make_recipe('booking.future_CL', cost=5, _quantity=3)
        baker.make_recipe('booking.future_WS', cost=5, _quantity=1)

    def _get_response(self, user, ev_type):
        url = reverse('booking:lessons')
        request = self.factory.get(url)
        request.user = user
        view = EventListView.as_view()
        return view(request, ev_type=ev_type)

    def test_with_logged_in_user(self):
        """
        test that page loads if there is a user is available
        """
        resp = self._get_response(self.user, 'lessons')
        self.assertEqual(resp.status_code, 200)
        self.assertEquals(resp.context_data['type'], 'lessons')
        self.assertTrue('booked_events' in resp.context_data)

    def test_lesson_list_with_anonymous_user(self):
        """
        Test that no booked_events in context
        """
        url = reverse('booking:lessons')
        resp = self.client.get(url)

        # event listing should still only show future events
        self.assertFalse('booked_events' in resp.context)

    def test_lesson_list(self):
        """
        Test that only classes are listed (pole classes and other classes)
        """
        url = reverse('booking:lessons')
        resp = self.client.get(url)

        self.assertEquals(Event.objects.all().count(), 8)
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context['events'].count(), 6)
        self.assertEquals(resp.context['type'], 'lessons')

    def test_filter_lessons(self):
        """
        Test that we can filter the classes by name
        """
        baker.make_recipe('booking.future_PC', name='test_name', _quantity=3)
        baker.make_recipe('booking.future_PC', name='test_name1', _quantity=4)

        url = reverse('booking:lessons')
        resp = self.client.get(url, {'name': 'test_name'})
        self.assertEquals(resp.context['events'].count(), 3)
        resp = self.client.get(url, {'name': 'test_name1'})
        self.assertEquals(resp.context['events'].count(), 4)

    def test_lesson_list_shows_only_current_user_bookings(self):
        """
        Test that only user's booked events are shown as booked
        """
        events = Event.objects.filter(event_type__event_type="CL")
        event1,  event2 = events[0:2]

        resp = self._get_response(self.user, 'lessons')
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(len(resp.context_data['booked_events']), 0)

        # create booking for this user
        baker.make_recipe('booking.booking', user=self.user, event=event1)
        # create booking for another user
        user1 = baker.make_recipe('booking.user')
        baker.make_recipe('booking.booking', user=user1, event=event2)

        # check only event1 shows in the booked events
        resp = self._get_response(self.user, 'lessons')
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(Booking.objects.all().count(), 2)
        self.assertEquals(len(booked_events), 1)
        self.assertTrue(event1.id in booked_events)

    def test_lesson_list_only_shows_open_bookings(self):
        events = Event.objects.filter(event_type__event_type="CL")
        event1,  event2 = events[0:2]

        resp = self._get_response(self.user, 'lessons')
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(len(resp.context_data['booked_events']), 0)

        # create open and cancelled booking for this user
        baker.make_recipe('booking.booking', user=self.user, event=event1)
        baker.make_recipe(
            'booking.booking', user=self.user, event=event2, status='CANCELLED'
        )

        # check only event1 shows in the booked events
        resp = self._get_response(self.user, 'lessons')
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(Booking.objects.all().count(), 2)
        self.assertEquals(len(booked_events), 1)
        self.assertTrue(event1.id in booked_events)

    def test_autocancelled_booking(self):
        events = Event.objects.filter(event_type__event_type="CL")
        event1, event2 = events[0:2]

        # create auto cancelled booking for this user
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event2, status='CANCELLED',
            auto_cancelled=True
        )

        resp = self._get_response(self.user, 'lessons')
        self.assertEqual(
            list(resp.context_data['auto_cancelled_events']), [event2.id]
        )
        self.assertIn('autocancelled_button', resp.rendered_content)

        booking.auto_cancelled = False
        booking.save()
        resp = self._get_response(self.user, 'lessons')
        self.assertEqual(
            list(resp.context_data['auto_cancelled_events']), []
        )
        self.assertIn('book_button', resp.rendered_content)
        self.assertNotIn('autocancelled_button', resp.rendered_content)


class RoomHireListViewTests(TestSetupMixin, TestCase):
    """
    Test EventListView with room hires; reuses the event templates and context
    data helpers
    """
    @classmethod
    def setUpTestData(cls):
        super(RoomHireListViewTests, cls).setUpTestData()
        baker.make_recipe('booking.future_RH', _quantity=4)
        baker.make_recipe('booking.future_EV', _quantity=1)
        baker.make_recipe('booking.future_PC', _quantity=3)
        baker.make_recipe('booking.future_CL', _quantity=3)
        baker.make_recipe('booking.future_WS', _quantity=1)

    def _get_response(self, user, ev_type):
        url = reverse('booking:room_hires')
        request = self.factory.get(url)
        request.user = user
        view = EventListView.as_view()
        return view(request, ev_type=ev_type)

    def test_with_logged_in_user(self):
        """
        test that page loads if there is a user is available
        """
        resp = self._get_response(self.user, 'room_hires')
        self.assertEqual(resp.status_code, 200)
        self.assertEquals(resp.context_data['type'], 'room_hires')
        self.assertTrue('booked_events' in resp.context_data)

    def test_room_hire_list_with_anonymous_user(self):
        """
        Test that no booked_events in context
        """
        url = reverse('booking:room_hires')
        resp = self.client.get(url)

        # event listing should still only show future events
        self.assertFalse('booked_events' in resp.context)

    def test_room_hire_list(self):
        """
        Test that only room hires are listed
        """
        url = reverse('booking:room_hires')
        resp = self.client.get(url)

        self.assertEquals(Event.objects.all().count(), 12)
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context['events'].count(), 4)
        self.assertEquals(resp.context['type'], 'room_hires')

    def test_filter_room_hire(self):
        """
        Test that we can filter the room hires by name
        """
        baker.make_recipe('booking.future_RH', name='test_name', _quantity=3)
        baker.make_recipe('booking.future_RH', name='test_name1', _quantity=4)

        url = reverse('booking:room_hires')
        resp = self.client.get(url, {'name': 'test_name'})
        self.assertEquals(resp.context['events'].count(), 3)
        resp = self.client.get(url, {'name': 'test_name1'})
        self.assertEquals(resp.context['events'].count(), 4)

    def test_room_hire_list_shows_only_current_user_bookings(self):
        """
        Test that only user's booked room hires are shown as booked
        """
        events = Event.objects.filter(event_type__event_type="RH")
        event1,  event2 = events[0:2]

        resp = self._get_response(self.user, 'room_hires')
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(len(resp.context_data['booked_events']), 0)

        # create booking for this user
        baker.make_recipe('booking.booking', user=self.user, event=event1)
        # create booking for another user
        user1 = baker.make_recipe('booking.user')
        baker.make_recipe('booking.booking', user=user1, event=event2)

        # check only event1 shows in the booked events
        resp = self._get_response(self.user, 'room_hires')
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(Booking.objects.all().count(), 2)
        self.assertEquals(len(booked_events), 1)
        self.assertTrue(event1.id in booked_events)

    def test_room_hire_list_only_shows_open_bookings(self):
        events = Event.objects.filter(event_type__event_type="RH")
        event1,  event2 = events[0:2]

        resp = self._get_response(self.user, 'room_hires')
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(len(resp.context_data['booked_events']), 0)

        # create open and cancelled booking for this user
        baker.make_recipe('booking.booking', user=self.user, event=event1)
        baker.make_recipe(
            'booking.booking', user=self.user, event=event2, status='CANCELLED'
        )

        # check only event1 shows in the booked events
        resp = self._get_response(self.user, 'room_hires')
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEquals(Booking.objects.all().count(), 2)
        self.assertEquals(len(booked_events), 1)
        self.assertTrue(event1.id in booked_events)


class LessonDetailViewTests(TestSetupMixin, TestCase):
    """
    Test EventDetailView with lessons; reuses the event templates and
    context data helpers
    """
    @classmethod
    def setUpTestData(cls):
        super(LessonDetailViewTests, cls).setUpTestData()
        cls.lesson = baker.make_recipe('booking.future_PC')
        baker.make_recipe('booking.future_EV', _quantity=3)
        baker.make_recipe('booking.future_PC', _quantity=3)

    def test_with_logged_in_user(self):
        """
        test that page loads if there user is available
        """
        url = reverse('booking:lesson_detail', args=[self.lesson.slug])
        request = self.factory.get(url)
        # Set the user on the request
        request.user = self.user
        view = EventDetailView.as_view()
        resp = view(request, slug=self.lesson.slug, ev_type='lesson')

        self.assertEqual(resp.status_code, 200)
        self.assertEquals(resp.context_data['type'], 'lesson')


class RoomHireDetailViewTests(TestSetupMixin, TestCase):
    """
    Test EventDetailView with room hires; reuses the event templates and
    context data helpers
    """
    @classmethod
    def setUpTestData(cls):
        super(RoomHireDetailViewTests, cls).setUpTestData()
        cls.room_hire = baker.make_recipe('booking.future_RH')
        baker.make_recipe('booking.future_EV', _quantity=3)
        baker.make_recipe('booking.future_PC', _quantity=3)
        baker.make_recipe('booking.future_RH', _quantity=3)

    def test_with_logged_in_user(self):
        """
        test that page loads if there user is available
        """
        url = reverse('booking:room_hire_detail', args=[self.room_hire.slug])
        request = self.factory.get(url)
        # Set the user on the request
        request.user = self.user
        view = EventDetailView.as_view()
        resp = view(request, slug=self.room_hire.slug, ev_type='room_hire')

        self.assertEqual(resp.status_code, 200)
        self.assertEquals(resp.context_data['type'], 'room_hire')
