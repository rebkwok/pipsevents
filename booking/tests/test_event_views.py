import os
import pytest

from unittest.mock import patch

from model_bakery import baker
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from bs4 import BeautifulSoup

from django.contrib.auth.models import User
from django.urls import reverse
from django.test import TestCase
from django.contrib.auth.models import Permission
from django.utils import timezone

from accounts.models import OnlineDisclaimer, \
    DataPrivacyPolicy, DisclaimerContent
from accounts.models import has_active_data_privacy_agreement

from booking.models import Event, FilterCategory, Booking
from booking.views import EventListView, EventDetailView
from common.tests.helpers import TestSetupMixin, format_content, \
    make_data_privacy_agreement, make_online_disclaimer


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

    def test_event_list(self):
        """
        Test that only events are listed (workshops and other events)
        """
        self.client.logout()
        resp = self.client.get(self.url)

        self.assertEqual(Event.objects.all().count(), 9)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['events'].count(), 3)

    def test_event_list_visible_on_site(self):
        """
        Test that only visible_on_site events are listed
        """
        event = baker.make_recipe('booking.future_EV', visible_on_site=False)
        resp = self.client.get(self.url)
        assert Event.objects.all().count() == 10
        assert Event.objects.filter(event_type__event_type="EV").count() == 4
        assert resp.context['events'].count() == 3

        event.visible_on_site = True
        event.save()
        resp = self.client.get(self.url)
        assert resp.context['events'].count() == 4

    def test_event_list_logged_in_no_data_protection_policy(self):
        DataPrivacyPolicy.objects.all().delete()
        user = User.objects.create_user(
            username='testnodp', email='testnodp@test.com', password='test'
        )
        make_online_disclaimer(user)
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
        self.assertEqual(Event.objects.all().count(), 10)
        resp = self.client.get(self.url)

        # event listing should still only show future events
        self.assertEqual(resp.context['events'].count(), 3)

    def test_event_list_past_event_within_10_mins_is_listed(self):
        """
        Test that past events is not listed
        """
        past = baker.make_recipe('booking.past_event', date=timezone.now() - timedelta(minutes=30))
        # check there are now 4 events (10 altogether)
        self.assertEqual(Event.objects.all().count(), 10)
        resp = self.client.get(self.url)

        # event listing should still only show future events
        self.assertEqual(resp.context['events'].count(), 3)

        past.date = timezone.now() - timedelta(minutes=9)
        past.save()
        # event listing should shows future events plus pas within 10 mins
        self.assertEqual(resp.context['events'].count(), 4)

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
        self.assertEqual(len(resp.context_data['booked_events']), 0)

        # create a booking for this user
        event = self.events[0]
        baker.make_recipe('booking.booking', user=self.user, event=event)
        resp = self.client.get(self.url)
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEqual(len(booked_events), 1)
        self.assertTrue(event.id in booked_events)

    def test_event_list_members_only(self):
        resp = self.client.get(self.url)
        assert "Members only" not in resp.rendered_content
        event = self.events[0]
        event.members_only = True
        event.save()
        resp = self.client.get(self.url)
        assert "Members only" in resp.rendered_content

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
        self.assertEqual(len(booked_events), 1)
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
        self.assertEqual(len(resp.context_data['booked_events']), 0)

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
        self.assertEqual(Booking.objects.all().count(), 2)
        self.assertEqual(len(booked_events), 1)
        self.assertTrue(event.id in booked_events)

    def test_filter_events(self):
        """
        Test that we can filter the classes by name
        """
        baker.make_recipe('booking.future_EV', name='test_name', _quantity=3)
        baker.make_recipe('booking.future_EV', name='test_name1', _quantity=4)

        resp = self.client.get(self.url, {'name': 'test_name'})
        self.assertEqual(resp.context['events'].count(), 3)

    @patch("booking.views.event_views.timezone")
    def test_filter_events_by_date(self, mock_tz):
        mock_tz.now.return_value = datetime(2023, 1, 1, tzinfo=dt_timezone.utc)
        baker.make_recipe('booking.future_EV', date=datetime(2023, 1, 23, 10, 0, tzinfo=dt_timezone.utc))
        baker.make_recipe('booking.future_EV', date=datetime(2023, 2, 23, 10, 0, tzinfo=dt_timezone.utc))
        baker.make_recipe('booking.future_EV', date=datetime(2023, 3, 23, 10, 0, tzinfo=dt_timezone.utc))

        resp = self.client.get(self.url, {'date_selection': '23-Jan-2023,23-Feb-2023'})
        self.assertEqual(resp.context['events'].count(), 2)

        # invalid date returns none
        resp = self.client.get(self.url, {'date_selection': '23Foo2023'})
        self.assertEqual(resp.context['events'].count(), 0)

    def test_filter_events_by_spaces(self):
        # full envent
        event = baker.make_recipe('booking.future_EV', max_participants=1)
        baker.make_recipe('booking.booking', event=event)
        # non-full event
        baker.make_recipe('booking.future_EV', max_participants=1)
        
        # full event for this user

        self.client.force_login(self.user)
        user_event = baker.make_recipe('booking.future_EV', max_participants=1)
        baker.make_recipe('booking.booking', event=user_event, user=self.user)

        resp = self.client.get(self.url, {'spaces_only': 'true'})
        # 3 from setup plus one non-full in this test and one full but booked by user
        self.assertEqual(resp.context['events'].count(), 5)

        self.client.logout()
        # anonymous user doesn't see the full booking for self.user
        resp = self.client.get(self.url, {'spaces_only': 'true'})
        # 3 from setup plus one in this test
        self.assertEqual(resp.context['events'].count(), 4)

    def test_pole_practice_context_without_permission(self):
        Event.objects.all().delete()
        baker.make_recipe('booking.future_PP')

        user = User.objects.create_user(username='test1', password='test1')
        make_online_disclaimer(user)
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
        event = baker.make_recipe('booking.future_PP')

        user = User.objects.create_user(username='test1', password='test1')
        make_data_privacy_agreement(user)
        event.event_type.add_permission_to_book(user)
        make_online_disclaimer(user)
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
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(response.context_data['events'].count(), 0)

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
            date=datetime(2015, 2, 1, tzinfo=dt_timezone.utc),
            version=DisclaimerContent.current_version()
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

        # active disclaimer
        disclaimer = baker.make_recipe(
            'booking.online_disclaimer', user=user, version=DisclaimerContent.current_version()
        )
        assert disclaimer.is_active is True
        resp = self.client.get(self.url)
        self.assertTrue(resp.context_data.get('disclaimer'))
        self.assertNotIn(
            'Your disclaimer has expired. Please review and confirm your '
            'information before booking.',
            format_content(resp.rendered_content)
        )

        OnlineDisclaimer.objects.all().delete()
        make_online_disclaimer(user)
        resp = self.client.get(self.url)
        self.assertTrue(resp.context_data.get('disclaimer'))
        self.assertNotIn(
            'Please note that you will need to complete a disclaimer form '
            'before booking',
            format_content(resp.rendered_content)
        )

    def test_event_list_tab_parameter_with_locations(self):
        """
        Test that events are coloured on alt days
        """
        events = Event.objects.filter(event_type__event_type='EV')
        ev = events[0]
        ev.location = "Davidson's Mains"
        ev.save()

        resp = self.client.get(self.url)

        # 1 loc events for all
        self.assertEqual(
            len(resp.context_data['location_events']), 0
        )
        # tab 0 by default
        self.assertEqual(resp.context_data['tab'], '0')
        # tab 0 is active and open by default
        self.assertIn(
            '<div class="tab-pane fade active in" id="tab0">',
            resp.rendered_content
        )

    @pytest.mark.skip("Locations currently not used")
    def test_event_list_tab_parameter_with_locations(self):
        """
        Test that events are coloured on alt days
        """
        events = Event.objects.filter(event_type__event_type='EV')
        ev = events[0]
        ev.location = "Davidson's Mains"
        ev.save()

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

        # bad tab, defaults to 0
        url += '?tab=foo'
        resp = self.client.get(url)
        self.assertEqual(resp.context_data['tab'], '0')

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

        # 1 loc event
        self.assertEqual(
            len(resp.context_data['location_events']), 1
        )
        # Queryset contains first 30
        self.assertEqual(
            len(resp.context_data['location_events'][0]['queryset']), 30
        )

    @pytest.mark.skip("Locations not currently used")
    def test_event_list_default_pagination_with_location(self):
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

    def test_event_list_default_pagination_with_page_and_location(self):
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

        # tab not an int, defaults to show specified page on index 0 (all), page 1 on the rest
        url = reverse('booking:lessons') + '?page=2&tab=foo'
        resp = self.client.get(url)
        # Queryset contains page 2 objs for all
        self.assertEqual(
            resp.context_data['location_events'][0]['queryset'].number, 2
        )

    @pytest.mark.skip("Locations not currently used")
    def test_event_list_default_pagination_with_page_and_location(self):
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

    def test_online_event_video_link(self):
        online_class = baker.make_recipe(
            'booking.future_CL', event_type__subtype="Online class", video_link="https://foo.test"
        )
        active_video_link_id = f"video_link_id_{online_class.id}"
        disabled_video_link_id = f"video_link_id_disabled_{online_class.id}"

        url = reverse('booking:lessons')

        # User is not booked, no links shown
        resp = self.client.get(url)
        assert active_video_link_id not in resp.rendered_content
        assert disabled_video_link_id not in resp.rendered_content

        booking = baker.make_recipe("booking.booking", event=online_class, user=self.user)
        # User is booked but not paid, no links shown
        resp = self.client.get(url)
        assert active_video_link_id not in resp.rendered_content
        assert disabled_video_link_id not in resp.rendered_content

        # User is booked and paid but class is more than 20 mins ahead
        booking.paid = True
        booking.save()
        resp = self.client.get(url)
        assert active_video_link_id not in resp.rendered_content
        assert disabled_video_link_id in resp.rendered_content

        # User is booked and paid, class is less than 20 mins ahead
        online_class.date = timezone.now() + timedelta(minutes=10)
        online_class.save()
        resp = self.client.get(url)
        assert active_video_link_id in resp.rendered_content
        assert disabled_video_link_id not in resp.rendered_content

        # User is no show
        booking.no_show = True
        booking.save()
        resp = self.client.get(url)
        assert active_video_link_id not in resp.rendered_content
        assert disabled_video_link_id not in resp.rendered_content

        # user has cancelled
        booking.no_show = False
        booking.status = "CANCELLED"
        booking.save()
        resp = self.client.get(url)
        assert active_video_link_id not in resp.rendered_content
        assert disabled_video_link_id not in resp.rendered_content


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

    def test_login_not_required(self):
        """
        test that page redirects if there is no user logged in
        """
        url = reverse('booking:event_detail', kwargs={'slug': self.event.slug})
        resp = self.client.get(url)
        assert resp.status_code == 200
        for item in ["booking", "disclaimer", "disclaimer_expired"]:
            assert item not in resp.context_data
        assert "To book this workshop" in resp.rendered_content

    def test_with_logged_in_user(self):
        """
        test that page loads if there user is available
        """
        resp = self._get_response(self.user, self.event, 'event')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context_data['ev_type_for_url'], 'events')

    def test_event_members_only(self):
        self.client.force_login(self.user)
        url = reverse('booking:event_detail', kwargs={'slug': self.event.slug})

        resp = self.client.get(url)
        assert "open to members only" not in resp.rendered_content
        
        self.event.members_only = True
        self.event.save()
        resp = self.client.get(url)
        assert "open to members only" in resp.rendered_content

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
        self.assertEqual(resp.context_data['booking_info_text'],
                          'You have booked for this workshop/event.')
        self.assertNotIn('pay_button', resp.rendered_content)

        # make booking unpaid
        booking.paid = False
        booking.payment_confirmed = False
        booking.save()
        resp = self._get_response(self.user, self.event, 'event')
        self.assertTrue(resp.context_data['booked'])
        self.assertEqual(resp.context_data['booking_info_text'],
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
        self.assertEqual(resp.context_data['booking_info_text'], '')

    def test_pole_practice_context_without_permission(self):
        pole_practice = baker.make_recipe('booking.future_PP')
        user = baker.make_recipe('booking.user')
        make_data_privacy_agreement(user)
        make_online_disclaimer(user)

        response = self._get_response(user, pole_practice, 'lesson')
        response.render()
        self.assertIn('needs_permission', response.context_data)
        self.assertTrue(response.context_data['needs_permission'])
        self.assertFalse(response.context_data['bookable'])
        self.assertNotIn('book_button_disabled', str(response.content))
        self.assertNotIn('book_button', str(response.content))
        self.assertNotIn('join_waiting_list_button', str(response.content))
        self.assertNotIn('leave_waiting_list_button', str(response.content))

    def test_pole_practice_context_with_permission(self):
        pole_practice = baker.make_recipe('booking.future_PP')

        user = baker.make_recipe('booking.user')
        make_data_privacy_agreement(user)
        pole_practice.event_type.add_permission_to_book(user)
        make_online_disclaimer(user)

        response = self._get_response(user, pole_practice, 'lesson')
        response.render()
        self.assertNotIn('needs_permission', response.context_data)
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
        self.assertTrue(self.event.can_cancel)

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
        self.assertTrue(self.event.can_cancel)

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
        self.assertTrue(self.event.can_cancel)

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
        self.assertEqual(resp.context_data['ev_type_for_url'], 'lessons')
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

        self.assertEqual(Event.objects.all().count(), 8)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['events'].count(), 6)
        self.assertEqual(resp.context['ev_type_for_url'], 'lessons')

    def test_filter_lessons(self):
        """
        Test that we can filter the classes by category
        """
        cat1 = baker.make(FilterCategory, category="test_name")
        cat2 = baker.make(FilterCategory, category="test_name1")
        pc1s = baker.make_recipe('booking.future_PC', _quantity=3)
        for pc in pc1s:
            pc.categories.add(cat1)
        pc2s = baker.make_recipe('booking.future_PC', _quantity=4)
        for pc in pc2s:
            pc.categories.add(cat2)

        url = reverse('booking:lessons')
        resp = self.client.get(url, {'name': 'test_name'})
        self.assertEqual(resp.context['events'].count(), 3)
        resp = self.client.get(url, {'name': 'test_name1'})
        self.assertEqual(resp.context['events'].count(), 4)

    def test_lesson_list_shows_only_current_user_bookings(self):
        """
        Test that only user's booked events are shown as booked
        """
        events = Event.objects.filter(event_type__event_type="CL")
        event1,  event2 = events[0:2]

        resp = self._get_response(self.user, 'lessons')
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEqual(len(resp.context_data['booked_events']), 0)

        # create booking for this user
        baker.make_recipe('booking.booking', user=self.user, event=event1)
        # create booking for another user
        user1 = baker.make_recipe('booking.user')
        baker.make_recipe('booking.booking', user=user1, event=event2)

        # check only event1 shows in the booked events
        resp = self._get_response(self.user, 'lessons')
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEqual(Booking.objects.all().count(), 2)
        self.assertEqual(len(booked_events), 1)
        self.assertTrue(event1.id in booked_events)

    def test_lesson_list_only_shows_open_bookings(self):
        events = Event.objects.filter(event_type__event_type="CL")
        event1,  event2 = events[0:2]

        resp = self._get_response(self.user, 'lessons')
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEqual(len(resp.context_data['booked_events']), 0)

        # create open and cancelled booking for this user
        baker.make_recipe('booking.booking', user=self.user, event=event1)
        baker.make_recipe(
            'booking.booking', user=self.user, event=event2, status='CANCELLED'
        )

        # check only event1 shows in the booked events
        resp = self._get_response(self.user, 'lessons')
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEqual(Booking.objects.all().count(), 2)
        self.assertEqual(len(booked_events), 1)
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
        self.assertEqual(resp.context_data['ev_type_for_url'], 'room_hires')
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

        self.assertEqual(Event.objects.all().count(), 12)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['events'].count(), 4)
        self.assertEqual(resp.context['ev_type_for_url'], 'room_hires')

    def test_filter_room_hire(self):
        """
        Test that we can filter the room hires by name
        """
        baker.make_recipe('booking.future_RH', name='test_name', _quantity=3)
        baker.make_recipe('booking.future_RH', name='test_name1', _quantity=4)

        url = reverse('booking:room_hires')
        resp = self.client.get(url, {'name': 'test_name'})
        self.assertEqual(resp.context['events'].count(), 3)
        resp = self.client.get(url, {'name': 'test_name1'})
        self.assertEqual(resp.context['events'].count(), 4)

    def test_room_hire_list_shows_only_current_user_bookings(self):
        """
        Test that only user's booked room hires are shown as booked
        """
        events = Event.objects.filter(event_type__event_type="RH")
        event1,  event2 = events[0:2]

        resp = self._get_response(self.user, 'room_hires')
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEqual(len(resp.context_data['booked_events']), 0)

        # create booking for this user
        baker.make_recipe('booking.booking', user=self.user, event=event1)
        # create booking for another user
        user1 = baker.make_recipe('booking.user')
        baker.make_recipe('booking.booking', user=user1, event=event2)

        # check only event1 shows in the booked events
        resp = self._get_response(self.user, 'room_hires')
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEqual(Booking.objects.all().count(), 2)
        self.assertEqual(len(booked_events), 1)
        self.assertTrue(event1.id in booked_events)

    def test_room_hire_list_only_shows_open_bookings(self):
        events = Event.objects.filter(event_type__event_type="RH")
        event1,  event2 = events[0:2]

        resp = self._get_response(self.user, 'room_hires')
        # check there are no booked events yet
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEqual(len(resp.context_data['booked_events']), 0)

        # create open and cancelled booking for this user
        baker.make_recipe('booking.booking', user=self.user, event=event1)
        baker.make_recipe(
            'booking.booking', user=self.user, event=event2, status='CANCELLED'
        )

        # check only event1 shows in the booked events
        resp = self._get_response(self.user, 'room_hires')
        booked_events = [event for event in resp.context_data['booked_events']]
        self.assertEqual(Booking.objects.all().count(), 2)
        self.assertEqual(len(booked_events), 1)
        self.assertTrue(event1.id in booked_events)


class OnlineTutorialListViewTests(TestSetupMixin, TestCase):
    """
    Test EventListView with room hires; reuses the event templates and context
    data helpers
    """
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        baker.make_recipe('booking.future_OT', name="Bar", _quantity=3)
        baker.make_recipe('booking.future_OT', name="Foo")

    def test_online_tutorials(self):
        resp = self.client.get(reverse('booking:online_tutorials'))
        assert resp.context_data["events"].count() == 4

    def test_online_tutorials_with_name(self):
        resp = self.client.get(reverse('booking:online_tutorials') + "?name=Foo")
        assert resp.context_data["events"].count() == 1

        resp = self.client.get(reverse('booking:online_tutorials') + "?name=all")
        assert resp.context_data["events"].count() == 4


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

    def setUp(self):
        super().setUp()
        self.client.login(username=self.user.username, password="test")

    def test_with_logged_in_user(self):
        """
        test that page loads if there user is available
        """
        url = reverse('booking:lesson_detail', args=[self.lesson.slug])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context_data['ev_type_for_url'], 'lessons')

    def test_online_event_video_link(self):
        online_class = baker.make_recipe(
            'booking.future_CL', event_type__subtype="Online class", video_link="https://foo.test"
        )
        active_video_link_id = f"video_link_id"
        disabled_video_link_id = f"video_link_disabled_id"

        url = reverse('booking:lesson_detail', args=[online_class.slug])

        # User is not booked, disabled link shown
        resp = self.client.get(url)
        assert active_video_link_id not in resp.rendered_content
        assert disabled_video_link_id in resp.rendered_content

        booking = baker.make_recipe("booking.booking", event=online_class, user=self.user)
        # User is booked but not paid, disabled link shown
        resp = self.client.get(url)
        assert active_video_link_id not in resp.rendered_content
        assert disabled_video_link_id in resp.rendered_content

        # User is booked and paid but class is more than 20 mins ahead
        booking.paid = True
        booking.save()
        resp = self.client.get(url)
        assert active_video_link_id not in resp.rendered_content
        assert disabled_video_link_id in resp.rendered_content

        # User is booked and paid, class is less than 20 mins ahead
        online_class.date = timezone.now() + timedelta(minutes=10)
        online_class.save()
        resp = self.client.get(url)
        assert active_video_link_id in resp.rendered_content
        assert disabled_video_link_id not in resp.rendered_content

        # User is no show
        booking.no_show = True
        booking.save()
        resp = self.client.get(url)
        assert active_video_link_id not in resp.rendered_content
        assert disabled_video_link_id in resp.rendered_content

        # user has cancelled
        booking.no_show = False
        booking.status = "CANCELLED"
        booking.save()
        resp = self.client.get(url)
        assert active_video_link_id not in resp.rendered_content
        assert disabled_video_link_id in resp.rendered_content


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
        self.assertEqual(resp.context_data['ev_type_for_url'], 'room_hires')
