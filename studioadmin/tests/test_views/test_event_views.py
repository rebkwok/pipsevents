# -*- coding: utf-8 -*-
import pytz

from datetime import timedelta

from unittest.mock import patch

from model_bakery import baker

import pytest

from django.conf import settings
from django.urls import reverse
from django.core import mail
from django.contrib.sites.models import Site
from django.test import TestCase
from django.utils import timezone

from booking.models import Block, BlockType, Event, Booking, FilterCategory
from common.tests.helpers import (
    _add_user_email_addresses, format_content, create_configured_user
)
from studioadmin.tests.test_views.helpers import TestPermissionMixin
from stripe_payments.tests.mock_connector import MockConnector


class EventAdminListViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(EventAdminListViewTests, self).setUp()
        self.event = baker.make_recipe('booking.future_EV', cost=7)
        self.url = reverse('studioadmin:events')
        self.lesson_url = reverse('studioadmin:lessons')
        self.room_hire_url = reverse('studioadmin:room_hires')
        self.client.force_login(self.staff_user)

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        self.client.logout()
        url = reverse('studioadmin:events')
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        self.client.logout()
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_cannot_access(self):
        """
        test that the page redirects if user is in the instructor group but is
        not a staff user
        """
        self.client.logout()
        self.client.force_login(self.instructor_user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_events_url_shows_only_events(self):
        events = baker.make_recipe('booking.future_EV', _quantity=5)
        events.append(self.event)
        resp = self.client.get(self.url)

        assert {ev.id for ev in resp.context_data["events"]} == {ev.id for ev in events}
        self.assertIn('Scheduled Events', resp.rendered_content)

    def test_classes_url_shows_excludes_events(self):
        classes = baker.make_recipe('booking.future_PC', _quantity=5)
        resp = self.client.get(self.lesson_url)

        assert {ev.id for ev in resp.context_data["events"]} == {cl.id for cl in classes}
        self.assertIn('Scheduled Classes', resp.rendered_content)

    def test_room_hire_and_classes(self):
        baker.make_recipe('booking.future_PC', _quantity=5)
        baker.make_recipe('booking.future_RH', _quantity=4)
        resp = self.client.get(self.lesson_url)

        self.assertEqual(Event.objects.count(), 10)
        self.assertEqual(resp.context_data["events"].count(), 5)
        self.assertIn('Scheduled Classes', resp.rendered_content)

        resp = resp = self.client.get(self.room_hire_url)
        self.assertEqual(resp.context_data["events"].count(), 4)
        self.assertIn('Scheduled Room Hire', resp.rendered_content)

    def test_past_filter(self):
        past_evs = baker.make_recipe('booking.past_event', _quantity=5)
        resp = self.client.post(self.url, {'past': 'Show past'})

        assert {ev.id for ev in resp.context_data["events"]} == {ev.id for ev in past_evs}
        self.assertEqual(Event.objects.count(), 6)
        self.assertEqual(resp.context_data["events"] .count(), 5)

        self.assertIn('Past Events', resp.rendered_content)
        self.assertNotIn('Scheduled Events',resp.rendered_content)

    def test_classes_past_filter(self):
        past_classes = baker.make_recipe('booking.past_class', _quantity=5)
        resp = self.client.post(self.lesson_url, {'past': 'Show past'})

        {ev.id for ev in resp.context_data["events"]} == {ev.id for ev in past_classes}
        self.assertEqual(Event.objects.count(), 6)
        self.assertEqual(resp.context_data["events"].count() , 5)

        self.assertIn(
            'Past Classes', format_content(resp.rendered_content)
        )

    def test_upcoming_filter(self):
        past_evs = baker.make_recipe('booking.past_event', _quantity=5)
        resp = resp = self.client.post(self.url, {'upcoming': 'Show upcoming'})
       
        self.assertEqual(Event.objects.count(), 6)
        assert resp.context_data["events"].count() == 1

        self.assertIn('Scheduled Events', resp.rendered_content)
        self.assertNotIn('Past Events', resp.rendered_content)

    def test_pagination(self):
        baker.make_recipe('booking.future_PC', _quantity=35)
        url = reverse('studioadmin:lessons')
        self.assertEqual(
            Event.objects.filter(
                event_type__event_type='CL').count(), 35
        )
        # paginating future
        resp = self.client.get(url + '?page=1')
        self.assertEqual(resp.context_data["events"].count(), 30)
        paginator = resp.context_data['event_page']
        self.assertEqual(paginator.number, 1)

        # page not a number shows page 1
        resp = self.client.get(url + '?page=one')
        self.assertEqual(resp.context_data["events"].count() , 30)
        paginator = resp.context_data['event_page']
        self.assertEqual(paginator.number, 1)

        # page out of range shows last page
        resp = self.client.get(url + '?page=3')

        self.assertEqual(resp.context_data["events"].count(), 5)
        paginator = resp.context_data['event_page']
        self.assertEqual(paginator.number, 2)

    def test_past_pagination(self):
        baker.make_recipe('booking.past_class', _quantity=35)
        url = reverse('studioadmin:lessons')
        self.assertEqual(Event.objects.count(), 36)

        # get only shows future by default
        resp = self.client.get(url)
        self.assertEqual(resp.context_data["events"].count(), 0)

        # past with page defaults back to page 1 b/c we are switching from
        # displaying upcoming
        resp = self.client.post(url + '?page=2', {'past': 'Show past'})
        self.assertEqual(resp.context_data["events"].count(), 30)
        paginator = resp.context_data['event_page']
        self.assertEqual(paginator.number, 1)


class EventAdminUpdateViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(EventAdminUpdateViewTests, self).setUp()
        self.event = baker.make_recipe(
            'booking.future_EV',
            date=timezone.now().replace(second=0, microsecond=0) + timedelta(2)
        )
        self.url = reverse(
                'studioadmin:edit_event', kwargs={'slug': self.event.slug}
            )
        self.client.force_login(self.staff_user)

    def form_data(self, event, extra_data={}):
        data = {
            'id': event.id,
            'name': event.name,
            'event_type': event.event_type.id,
            'date': event.date.astimezone(
                pytz.timezone('Europe/London')
            ).strftime('%d %b %Y %H:%M'),
            'contact_email': event.contact_email,
            'contact_person': event.contact_person,
            'cancellation_period': event.cancellation_period,
            'location': event.location,
            'allow_booking_cancellation': True,
            'paypal_email': settings.DEFAULT_PAYPAL_EMAIL,
        }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        self.client.logout()
        url = reverse(
            'studioadmin:edit_event', kwargs={'slug': self.event.slug}
        )
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_cannot_access(self):
        """
        test that the page redirects if user is in the instructor group but is
        not a staff user
        """
        self.client.force_login(self.instructor_user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_edit_event_refers_to_events_on_page_and_menu(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.context_data['sidenav_selection'], 'events')
        self.assertEqual(resp.context_data['type'], 'event')
        resp.render()
        self.assertIn(
            self.event.name, str(resp.content), "Content not found"
        )

    def test_edit_class_refers_to_classes_on_page_and_menu(self):
        event = baker.make_recipe('booking.future_PC')
        resp = self.client.get(reverse('studioadmin:edit_lesson', kwargs={'slug': event.slug}))
        self.assertEqual(resp.context_data['sidenav_selection'], 'lessons')
        self.assertEqual(resp.context_data['type'], 'class')
        resp.render()
        self.assertIn(
            event.name, str(resp.content), "Content not found"
            )

    def test_edit_class_refers_to_room_hires_on_page_and_menu(self):
        event = baker.make_recipe('booking.future_RH')
        resp = self.client.get(reverse('studioadmin:edit_room_hire', kwargs={'slug': event.slug}))
        self.assertEqual(resp.context_data['sidenav_selection'], 'room_hires')
        self.assertEqual(resp.context_data['type'], 'room hire')
        resp.render()
        self.assertIn(
            event.name, str(resp.content), "Content not found"
            )
        
    def test_submitting_valid_event_form_redirects_back_to_events_list(self):
        form_data = self.form_data(event=self.event)
        resp = self.client.post(self.url, form_data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:events'))

    def test_submitting_valid_class_form_redirects_back_to_classes_list(self):
        event = baker.make_recipe('booking.future_PC')
        form_data = self.form_data(event=event)
        url = reverse('studioadmin:edit_lesson', kwargs={'slug': event.slug})
        resp = self.client.post(url, form_data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:lessons'))


    def test_submitting_valid_room_hire_form_redirects_back_to_room_hires_list(self):
        event = baker.make_recipe('booking.future_RH')
        form_data = self.form_data(event=event)
        url = reverse('studioadmin:edit_room_hire', kwargs={'slug': event.slug})
        resp = self.client.post(url, form_data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:room_hires'))

    def test_post_with_events_page(self):
        form_data = self.form_data(event=self.event)
        form_data['from_page'] = '2'
        resp = self.client.post(self.url, form_data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:events') + '?page=2')

    def test_no_changes(self):
        form_data = self.form_data(
            event=self.event, extra_data={
                'cost': self.event.cost,
                'booking_open': self.event.booking_open,
                'visible_on_site': self.event.visible_on_site,
                'allowed_group': self.event.allowed_group.id,
            }
        )
        url = reverse(
                'studioadmin:edit_event', kwargs={'slug': self.event.slug}
            )
        resp = self.client.post(url, form_data, follow=True)
        self.assertIn('No changes made', format_content(resp.rendered_content))

    def test_can_edit_event_data(self):
        self.assertTrue(self.event.booking_open)
        form_data = self.form_data(
            event=self.event, extra_data={'booking_open': False}
        )
        self.client.post(self.url, form_data)
        event = Event.objects.get(id=self.event.id)
        self.assertFalse(event.booking_open)

    @pytest.mark.serial
    def test_edit_with_categories(self):
        pole_class = baker.make_recipe('booking.future_PC')
        category = baker.make(FilterCategory, category="test xyz")
        assert not pole_class.categories.exists()
        data = self.form_data(event=self.event, extra_data={'categories': [category.id]})
        self.client.post(reverse('studioadmin:edit_event', kwargs={'slug': pole_class.slug}), data)
        pole_class = Event.objects.get(id=pole_class.id)
        assert FilterCategory.objects.count() == 1
        assert pole_class.categories.first().category == "test xyz"

    @pytest.mark.serial
    def test_edit_with_new_category(self):
        pole_class = baker.make_recipe('booking.future_PC')
        baker.make(FilterCategory, category="test abc")
        data = self.form_data(
            event=self.event, extra_data={'new_category': "Test 1a"}
        )
        self.client.post(reverse('studioadmin:edit_event', kwargs={'slug': pole_class.slug}), data)
        pole_class.refresh_from_db()
        assert FilterCategory.objects.count() == 2
        assert pole_class.categories.first().category == "Test 1a"

    def test_submitting_with_no_changes_does_not_change_event(self):
        form_data = self.form_data(self.event)
        self.client.post(self.url, form_data)
        event = Event.objects.get(id=self.event.id)
        self.assertEqual(self.event.id, event.id)
        self.assertEqual(self.event.name, event.name)
        self.assertEqual(self.event.event_type, event.event_type)
        self.assertEqual(
            self.event.date.strftime('%d %b %Y %H:%M'),
            event.date.strftime('%d %b %Y %H:%M')
        )
        self.assertEqual(self.event.contact_email, event.contact_email)
        self.assertEqual(self.event.contact_person, event.contact_person)
        self.assertEqual(
            self.event.cancellation_period, event.cancellation_period
        )
        self.assertEqual(self.event.location, event.location)

    def test_update_paypal_email_to_non_default(self):
        form_data = self.form_data(
            self.event,
            {
                'paypal_email': 'testpaypal@test.com',
                'paypal_email_check': 'testpaypal@test.com'
            }
        )
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.post(self.url, form_data, follow=True)

        self.assertIn(
            "You have changed the paypal receiver email. If you haven't used "
            "this email before, it is strongly recommended that you test the "
            "email address <a href='/studioadmin/test-paypal-email?"
            "email=testpaypal@test.com'>here</a>",
            resp.rendered_content
        )

        self.event.refresh_from_db()
        self.assertEqual(self.event.paypal_email, 'testpaypal@test.com')

        form_data = self.form_data(
            self.event,
            {
                'paypal_email': settings.DEFAULT_PAYPAL_EMAIL,
                'paypal_email_check': settings.DEFAULT_PAYPAL_EMAIL
            }
        )
        resp = self.client.post(
            self.url,
            form_data, follow=True
        )
        self.assertNotIn(
            "You have changed the paypal receiver email.",
            resp.rendered_content
        )
        self.event.refresh_from_db()
        self.assertEqual(self.event.paypal_email, settings.DEFAULT_PAYPAL_EMAIL)


class EventAdminCreateViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(EventAdminCreateViewTests, self).setUp()
        self.event_type_OE = baker.make_recipe('booking.event_type_OE')
        self.event_type_PC = baker.make_recipe('booking.event_type_PC')
        self.event_type_RH = baker.make_recipe('booking.event_type_RH')
        self.url = reverse('studioadmin:add_event')
        self.client.force_login(self.staff_user)

    def form_data(self, extra_data={}):
        data = {
            'name': 'test_event',
            'event_type': self.event_type_OE.id,
            'date': '15 Jun 2015 18:00',
            'contact_email': 'test@test.com',
            'contact_person': 'test',
            'cancellation_period': 24,
            'location': Event.LOCATION_CHOICES[0][0],
            'allow_booking_cancellation': True,
            'paypal_email': settings.DEFAULT_PAYPAL_EMAIL,
        }
        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        self.client.logout()
        url = reverse('studioadmin:add_event')
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_cannot_access(self):
        """
        test that the page redirects if user is in the instructor group but is
        not a staff user
        """
        self.client.force_login(self.instructor_user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_add_event_refers_to_events_on_page(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.context_data['sidenav_selection'], 'add_event')
        self.assertEqual(resp.context_data['type'], 'event')
        resp.render()
        self.assertIn(
            'Adding new event', str(resp.content), "Content not found"
        )

    def test_add_class_refers_to_classes_on_page(self):
        resp = self.client.get(reverse('studioadmin:add_lesson'))
        self.assertEqual(resp.context_data['sidenav_selection'], 'add_lesson')
        self.assertEqual(resp.context_data['type'], 'class')
        resp.render()
        self.assertIn(
            'Adding new class', str(resp.content), "Content not found"
        )

    def test_add_room_hire_refers_to_classes_on_page(self):
        resp = self.client.get(reverse('studioadmin:add_room_hire'))
        self.assertEqual(resp.context_data['sidenav_selection'], 'add_room_hire')
        self.assertEqual(resp.context_data['type'], 'room hire')
        resp.render()
        self.assertIn(
            'Adding new room hire', str(resp.content), "Content not found"
        )

    def test_submitting_valid_event_form_redirects_back_to_events_list(self):
        form_data = self.form_data()
        resp = self.client.post(self.url, form_data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:events'))

    def test_submitting_valid_class_form_redirects_back_to_classes_list(self):
        form_data = self.form_data(
            extra_data={'event_type': self.event_type_PC.id}
        )
        resp = self.client.post(reverse('studioadmin:add_lesson'), form_data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:lessons'))

    def test_submitting_valid_room_hire_form_redirects_back_to_room_hire_list(self):
        form_data = self.form_data(
            extra_data={'event_type': self.event_type_RH.id}
        )
        resp = self.client.post(reverse('studioadmin:add_room_hire'), form_data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:room_hires'))

    def test_can_add_event(self):
        self.assertEqual(Event.objects.count(), 0)
        form_data = self.form_data()
        resp = self.client.post(self.url, form_data)
        self.assertEqual(Event.objects.count(), 1)
        event = Event.objects.first()
        self.assertEqual(event.name, 'test_event')

    def test_submitting_form_with_errors_formats_field_names(self):
        self.assertEqual(Event.objects.count(), 0)
        form_data = self.form_data({'contact_email': 'test.com'})
        resp = self.client.post(self.url, form_data)
        self.assertEqual(Event.objects.count(), 0)
        self.assertIn(
            'Enter a valid email address.', resp.rendered_content
        )

    def test_create_event_with_non_default_paypal_email(self):
        form_data = self.form_data(
            {
                'paypal_email': 'testpaypal@test.com',
                'paypal_email_check': 'testpaypal@test.com'
            }
        )
        resp = self.client.post(self.url, form_data, follow=True)
        self.assertIn(
            "You have changed the paypal receiver email from the default value. "
            "If you haven't used "
            "this email before, it is strongly recommended that you test the "
            "email address <a href='/studioadmin/test-paypal-email?"
            "email=testpaypal@test.com'>here</a>",
            resp.rendered_content
        )

        event = Event.objects.latest('id')
        self.assertEqual(event.paypal_email, 'testpaypal@test.com')

        form_data = self.form_data()
        resp = self.client.post(self.url, form_data, follow=True)
        self.assertNotIn(
            "You have changed the paypal receiver email from the default value.",
            resp.rendered_content
        )
        event1 = Event.objects.latest('id')
        self.assertEqual(event1.paypal_email, settings.DEFAULT_PAYPAL_EMAIL)


class CancelEventTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = create_configured_user("test", "user@example.com", "test")
        cls.instructor_user = create_configured_user("instructor", "instructor@example.com", "test", instructor=True)
        cls.staff_user = create_configured_user("staff", "staff@example.com", "test", staff=True)

    def setUp(self):
        self.event = baker.make_recipe(
            'booking.future_EV', cost=10, booking_open=True, payment_open=True
        )
        self.lesson = baker.make_recipe(
            'booking.future_PC', cost=10, booking_open=True, payment_open=True
        )
        self.event_url = reverse('studioadmin:cancel_event', kwargs={'slug': self.event.slug})
        self.lesson_url = reverse('studioadmin:cancel_event', kwargs={'slug': self.lesson.slug})

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        resp = self.client.get(self.event_url)
        redirected_url = reverse('account_login') + "?next={}".format(self.event_url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        self.client.force_login(self.user)
        resp = self.client.get(self.event_url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        self.client.force_login(self.staff_user)
        resp = self.client.get(self.event_url)
        self.assertEqual(resp.status_code, 200)

    def test_get_cancel_page_with_no_bookings(self):
        # no open bookings displayed on page
        self.client.force_login(self.staff_user)
        resp = self.client.get(self.event_url)
        self.assertEqual(resp.context_data['open_bookings'], False)

    def test_get_cancel_page_with_cancelled_bookings_only(self):
        # no open bookings displayed on page
        baker.make_recipe(
            'booking.booking', event=self.event, status="CANCELLED", _quantity=3
        )

        self.client.force_login(self.staff_user)
        resp = self.client.get(self.event_url)
        self.assertEqual(resp.context_data['open_bookings'], False)

    def test_get_cancel_page_open_unpaid_bookings(self):
        # open bookings displayed on page, not in due_refunds list
        bookings = baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            paid=False,
            _quantity=3
        )
        self.client.force_login(self.staff_user)
        resp = self.client.get(self.event_url)
        self.assertEqual(
            sorted([bk.id for bk in resp.context_data['open_unpaid_bookings']]),
            sorted([bk.id for bk in bookings])
        )

        self.assertEqual(resp.context_data['open_bookings'], True)
        self.assertEqual(list(resp.context_data['open_block_bookings']), [])
        self.assertEqual(
            list(resp.context_data['open_deposit_only_paid_bookings']), []
        )
        self.assertEqual(
            list(resp.context_data['open_free_block_bookings']), []
        )
        self.assertEqual(
            list(resp.context_data['open_free_non_block_bookings']), []
        )
        self.assertEqual(
            list(resp.context_data['open_direct_paid_bookings']), []
        )

    def test_get_cancel_page_open_block_paid_bookings(self):
        # open bookings displayed on page, not in due_refunds list

        users = baker.make_recipe('booking.user', _quantity=3)
        for user in users:
            block = baker.make_recipe(
                'booking.block', block_type__event_type=self.event.event_type,
                user=user
            )
            baker.make_recipe(
                'booking.booking', event=self.event, status="OPEN", block=block,
                paid=True
        )
        bookings = Booking.objects.all()

        self.client.force_login(self.staff_user)
        resp = self.client.get(self.event_url)
        self.assertEqual(
            sorted([bk.id for bk in resp.context_data['open_block_bookings']]),
            sorted([bk.id for bk in bookings])
        )
        self.assertEqual(resp.context_data['open_bookings'], True)
        self.assertEqual(list(resp.context_data['open_unpaid_bookings']), [])
        self.assertEqual(
            list(resp.context_data['open_deposit_only_paid_bookings']), []
        )
        self.assertEqual(
            list(resp.context_data['open_free_block_bookings']), []
        )
        self.assertEqual(
            list(resp.context_data['open_free_non_block_bookings']), []
        )

        self.assertEqual(
            list(resp.context_data['open_direct_paid_bookings']), []
        )

    def test_get_cancel_page_open_free_class_bookings(self):
        # open bookings displayed on page, not in due_refunds list
        bookings = baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            free_class=True, paid=True,
            _quantity=3
        )
        self.client.force_login(self.staff_user)
        resp = self.client.get(self.event_url)
        self.assertEqual(
            sorted(
                [bk.id for bk in
                 resp.context_data['open_free_non_block_bookings']
                 ]
            ),
            sorted([bk.id for bk in bookings])
        )
        self.assertEqual(resp.context_data['open_bookings'], True)
        self.assertEqual(list(resp.context_data['open_block_bookings']), [])
        self.assertEqual(list(resp.context_data['open_free_block_bookings']), [])
        self.assertEqual(
            list(resp.context_data['open_deposit_only_paid_bookings']), []
        )
        self.assertEqual(list(resp.context_data['open_unpaid_bookings']), [])
        self.assertEqual(
            list(resp.context_data['open_direct_paid_bookings']), []
        )

    def test_get_cancel_page_open_direct_paid_bookings(self):
        # open bookings displayed on page, in due_refunds list
        bookings = baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            paid=True, free_class=False,
            _quantity=3
        )
        self.client.force_login(self.staff_user)
        resp = self.client.get(self.event_url)

        self.assertEqual(
            sorted(
                [bk.id for bk in resp.context_data['open_direct_paid_bookings']]
            ),
            sorted([bk.id for bk in bookings])
        )

        self.assertEqual(resp.context_data['open_bookings'], True)
        self.assertEqual(list(resp.context_data['open_block_bookings']), [])
        self.assertEqual(
            list(resp.context_data['open_deposit_only_paid_bookings']), []
        )
        self.assertEqual(
            list(resp.context_data['open_free_block_bookings']), []
        )
        self.assertEqual(
            list(resp.context_data['open_free_non_block_bookings']), []
        )
        self.assertEqual(list(resp.context_data['open_unpaid_bookings']), [])

    def test_get_cancel_page_multiple_bookings(self):
        # multiple bookings, cancelled not displayed at all; all open displayed
        # in open_bookings list, only direct paid displayed in due_refunds list

        cancelled_bookings = baker.make_recipe(
            'booking.booking', event=self.event, status="CANCELLED", _quantity=3
        )
        unpaid_bookings = baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            paid=False,
            _quantity=3
        )

        free_blocktype = baker.make_recipe('booking.free_blocktype')
        for user in baker.make_recipe('booking.user', _quantity=3):
            block = baker.make_recipe(
                'booking.block', block_type=free_blocktype, user=user
            )
            baker.make_recipe(
                'booking.booking', event=self.event, status="OPEN", block=block,
                paid=True, free_class=True
            )
        free_class_block_bookings = list(Booking.objects.filter(
            block__isnull=False, free_class=True)
        )

        free_class_non_block_bookings = baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            free_class=True, paid=True,
            _quantity=3
        )
        direct_paid_bookings = baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            paid=True, free_class=False,
            _quantity=3
        )

        deposit_only_paid_bookings = baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            deposit_paid=True, paid=False, free_class=False,
            _quantity=3
        )

        for user in baker.make_recipe('booking.user', _quantity=3):
            block = baker.make_recipe(
                'booking.block', block_type__event_type=self.event.event_type,
                user=user
            )
            baker.make_recipe(
                'booking.booking', event=self.event, status="OPEN", block=block,
                paid=True
        )
        block_bookings = list(Booking.objects.filter(
            block__isnull=False, free_class=False)
        )

        self.assertEqual(Booking.objects.filter(event=self.event).count(), 21)

        self.client.force_login(self.staff_user)
        resp = self.client.get(self.event_url)

        self.assertEqual(resp.context_data['open_bookings'], True)
        self.assertEqual(
            sorted(
                [bk.id for bk in resp.context_data['open_direct_paid_bookings']]
            ),
            sorted([bk.id for bk in direct_paid_bookings])
        )
        self.assertEqual(
            sorted(
                [bk.id for bk in resp.context_data['open_unpaid_bookings']]
            ),
            sorted([bk.id for bk in unpaid_bookings])
        )
        self.assertEqual(
            sorted(
                [bk.id for bk in resp.context_data['open_free_non_block_bookings']]
            ),
            sorted([bk.id for bk in free_class_non_block_bookings])
        )
        self.assertEqual(
            sorted(
                [bk.id for bk in resp.context_data['open_free_block_bookings']]
            ),
            sorted([bk.id for bk in free_class_block_bookings])
        )
        self.assertEqual(
            sorted(
                [bk.id for bk in resp.context_data['open_deposit_only_paid_bookings']]
            ),
            sorted([bk.id for bk in deposit_only_paid_bookings])
        )
        self.assertEqual(
            sorted(
                [bk.id for bk in resp.context_data['open_block_bookings']]
            ),
            sorted([bk.id for bk in block_bookings])
        )

    @patch("booking.models.membership_models.StripeConnector", MockConnector)
    def test_get_cancel_page_open_membership_paid_bookings(self):
        # open bookings displayed on page, not in due_refunds list
        baker.make("stripe_payments.Seller", site=Site.objects.get_current())
        self.client.force_login(self.staff_user)
        users = baker.make_recipe('booking.user', _quantity=3)
        for user in users:
            membership = baker.make(
                'booking.UserMembership', 
                user=user,
                membership__name="mem"
            )
            baker.make_recipe(
                'booking.booking', event=self.event, status="OPEN", membership=membership,
                paid=True
        )
        bookings = Booking.objects.all()

        url = reverse('studioadmin:cancel_event', kwargs={'slug': self.event.slug})
        resp = self.client.get(url)
        assert (
            sorted([bk.id for bk in resp.context_data['open_membership_bookings']]) == 
            sorted([bk.id for bk in bookings])
        )
        assert resp.context_data['open_bookings'] 
        assert not resp.context_data['open_block_bookings']
        assert not resp.context_data['open_unpaid_bookings']
        assert not resp.context_data['open_deposit_only_paid_bookings']
        assert not resp.context_data['open_free_block_bookings']
        assert not resp.context_data['open_free_non_block_bookings']
        assert not resp.context_data['open_direct_paid_bookings']

    @patch("booking.models.membership_models.StripeConnector", MockConnector)
    def test_cancel_event_with_open_membership_paid_bookings(self):
        # open bookings displayed on page, not in due_refunds list
        baker.make("stripe_payments.Seller", site=Site.objects.get_current())
        self.client.force_login(self.staff_user)
        users = baker.make_recipe('booking.user', _quantity=3)
        for user in users:
            membership = baker.make(
                'booking.UserMembership', 
                user=user,
                membership__name="mem"
            )
            baker.make_recipe(
                'booking.booking', event=self.event, status="OPEN", membership=membership,
                paid=True
        )
        bookings = Booking.objects.all()
        for booking in bookings:
            assert booking.membership is not None
            assert booking.paid
            assert booking.status == "OPEN"

        url = reverse('studioadmin:cancel_event', kwargs={'slug': self.event.slug})
        self.client.post(url, {"confirm": "Confirm"})
        bookings = Booking.objects.all()
        for booking in bookings:
            assert booking.membership is None
            assert booking.paid is False
            assert booking.status == "CANCELLED"
    
    def test_cancelling_event_sets_booking_and_payment_closed(self):
        """
        Cancelling and event sets cancelled to True, booking_open and
        payment_open to False
        """
        self.assertTrue(self.event.booking_open)
        self.assertTrue(self.event.payment_open)
        self.assertFalse(self.event.cancelled)
        self.client.force_login(self.staff_user)
        resp = self.client.post(self.event_url, {'confirm': 'Yes, cancel this event'})
        self.event.refresh_from_db()
        self.assertFalse(self.event.booking_open)
        self.assertFalse(self.event.payment_open)
        self.assertTrue(self.event.cancelled)


    def test_cancelling_event_cancels_open_block_bookings(self):
        """
        Cancelling changes block bookings to no block, not paid, not payment
        confirmed
        """
        for user in baker.make_recipe('booking.user', _quantity=3):
            block = baker.make_recipe(
                'booking.block', block_type__event_type=self.event.event_type,
                user=user
            )
            baker.make_recipe(
                'booking.booking', event=self.event, status="OPEN", block=block,
                paid=True
        )

        for booking in Booking.objects.filter(event=self.event):
            self.assertIsNotNone(booking.block)
            self.assertEqual(booking.status, 'OPEN')

        self.client.force_login(self.staff_user)
        resp = self.client.post(self.event_url, {'confirm': 'Yes, cancel this event'})
        for booking in Booking.objects.filter(event=self.event):
            self.assertIsNone(booking.block)
            self.assertEqual(booking.status, 'CANCELLED')

    def test_cancelling_event_cancels_free_class_bookings(self):
        """
        Cancelling changes leaves free class as free class, not paid, not payment
        confirmed if not booked with block
        """
        non_block_free = baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            free_class=True, paid=True,
            _quantity=3
        )
        block_type = baker.make_recipe('booking.free_blocktype')
        block = baker.make(Block, block_type=block_type)
        free_with_block = baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            free_class=True, paid=True, block=block
        )
        for booking in Booking.objects.filter(event=self.event):
            self.assertTrue(booking.free_class)
            self.assertEqual(booking.status, 'OPEN')

        self.client.force_login(self.staff_user)
        resp = self.client.post(self.event_url, {'confirm': 'Yes, cancel this event'})

        for booking in non_block_free:
            booking.refresh_from_db()
            self.assertTrue(booking.free_class)
            self.assertTrue(booking.paid)
            self.assertTrue(booking.payment_confirmed)
            self.assertEqual(booking.status, 'CANCELLED')

        free_with_block.refresh_from_db()
        self.assertFalse(free_with_block.free_class)
        self.assertFalse(free_with_block.paid)
        self.assertFalse(free_with_block.payment_confirmed)
        self.assertEqual(free_with_block.status, 'CANCELLED')

    def test_cancelling_event_cancels_direct_paid_bookings(self):
        """
        Cancelling changes direct paid classes to cancelled but does not change
         payment status
        """
        baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            paid=True, payment_confirmed=True, free_class=False,
            _quantity=3
        )
        for booking in Booking.objects.filter(event=self.event):
            self.assertTrue(booking.paid)
            self.assertTrue(booking.payment_confirmed)
            self.assertEqual(booking.status, 'OPEN')

        self.client.force_login(self.staff_user)
        resp = self.client.post(self.event_url, {'confirm': 'Yes, cancel this event'})

        for booking in Booking.objects.filter(event=self.event):
            self.assertTrue(booking.paid)
            self.assertTrue(booking.payment_confirmed)
            self.assertEqual(booking.status, 'CANCELLED')

    def test_cancelling_event_redirects_to_events_list(self):
        self.client.force_login(self.staff_user)
        resp = self.client.post(self.event_url, {'confirm': 'Yes, cancel this event'})
        self.event.refresh_from_db()
        self.assertTrue(self.event.cancelled)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:events'))

    def test_cancelling_class_redirects_to_classes_list(self):
        self.client.force_login(self.staff_user)
        resp = self.client.post(self.lesson_url, {'confirm': 'Yes, cancel this event'})
        self.lesson.refresh_from_db()
        self.assertTrue(self.lesson.cancelled)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:lessons'))

    def test_can_abort_cancel_event_request(self):
        self.client.force_login(self.staff_user)
        resp = self.client.post(self.event_url, {'confirm': 'Yes, cancel this event'})
        self.assertFalse(self.event.cancelled)
        self.assertTrue(self.event.booking_open)
        self.assertTrue(self.event.payment_open)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:events'))

    def test_can_abort_cancel_class_request(self):
        self.client.force_login(self.staff_user)
        resp = self.client.post(self.lesson_url, {'confirm': 'Yes, cancel this event'})
        self.assertFalse(self.lesson.cancelled)
        self.assertTrue(self.lesson.booking_open)
        self.assertTrue(self.lesson.payment_open)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:lessons'))

    def test_open_bookings_on_aborted_cancel_request_remain_open(self):
        baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            _quantity=3
        )
        self.client.force_login(self.staff_user)
        resp = self.client.post(self.event_url, {'cancel': 'No, take me back'})
        self.assertFalse(self.event.cancelled)
        for booking in Booking.objects.filter(event=self.event):
            self.assertEqual(booking.status, 'OPEN')

    def test_emails_sent_to_all_users_with_open_bookings(self):
        # unpaid
        baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            paid=False,
            _quantity=3
        )
        # free_class
        baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            free_class=True, paid=True,
            _quantity=3
        )
        # direct paid
        baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            paid=True, free_class=False,
            _quantity=3
        )
        # block bookings
        for user in baker.make_recipe('booking.user', _quantity=3):
            block = baker.make_recipe(
                'booking.block', block_type__event_type=self.event.event_type,
                user=user
            )
            baker.make_recipe(
                'booking.booking', event=self.event, status="OPEN", block=block,
                paid=True
        )
        _add_user_email_addresses(Booking)
        self.assertEqual(Booking.objects.filter(event=self.event).count(), 12)

        self.client.force_login(self.staff_user)
        resp = self.client.post(self.event_url, {'confirm': 'Yes, cancel this event'})
        # sends one email per open booking and one to studio
        self.assertEqual(len(mail.outbox), 13)

    def test_emails_not_sent_to_users_with_already_cancelled_bookings(self):
        # cancelled
        baker.make_recipe(
            'booking.booking', event=self.event, status="CANCELLED", _quantity=3
        )
        # unpaid
        baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            paid=False,
            _quantity=3
        )
        # free_class
        baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            free_class=True, paid=True,
            _quantity=3
        )
        # direct paid
        baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            paid=True, free_class=False,
            _quantity=3
        )
        # block bookings
        for user in baker.make_recipe('booking.user', _quantity=3):
            block = baker.make_recipe(
                'booking.block', block_type__event_type=self.event.event_type,
                user=user
            )
            baker.make_recipe(
                'booking.booking', event=self.event, status="OPEN", block=block,
                paid=True
            )
        _add_user_email_addresses(Booking)
        self.assertEqual(Booking.objects.filter(event=self.event).count(), 15)

        self.client.force_login(self.staff_user)
        resp = self.client.post(self.event_url, {'confirm': 'Yes, cancel this event'})
        # sends one email per open booking (not already cancelled) and one to
        # studio
        self.assertEqual(len(mail.outbox), 13)

    def test_emails_sent_to_studio_on_cancelling_event(self):
        """
        Emails sent for direct paid and for free without block
        """
        # cancelled
        cancelled = baker.make_recipe(
            'booking.booking', event=self.event, status="CANCELLED", _quantity=3
        )
        # unpaid
        baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            paid=False,
            _quantity=3
        )
        # free_class wuth block
        blocktype = baker.make_recipe('booking.free_blocktype')
        block = baker.make(Block, block_type=blocktype)
        baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            free_class=True, paid=True, block=block
        )
        # block bookings
        for user in baker.make_recipe('booking.user', _quantity=3):
            block = baker.make_recipe(
                'booking.block', block_type__event_type=self.event.event_type,
                user=user
            )
            baker.make_recipe(
                'booking.booking', event=self.event, status="OPEN", block=block,
                paid=True
            )
        self.assertEqual(Booking.objects.filter(event=self.event).count(), 10)

        open_bookings = Booking.objects.filter(event=self.event, status='OPEN')
        _add_user_email_addresses(Booking)
        self.client.force_login(self.staff_user)
        resp = self.client.post(self.event_url, {'confirm': 'Yes, cancel this event'})

        # sends one email per open booking and one email to studio
        self.assertEqual(len(mail.outbox), 8)
        self.assertIn('(unpaid) - no action required', mail.outbox[-1].body)
        self.assertIn('(free class - block) - no action required', mail.outbox[-1].body)
        self.assertIn('(paid by block) - no action required', mail.outbox[-1].body)
        for booking in open_bookings:
            self.assertIn(mail.outbox[-1].body, booking.user.first_name)
        for booking in cancelled:
            self.assertNotIn(mail.outbox[-1].body, booking.user.first_name)

    def test_email_to_studio_for_direct_paid_bookings_content(self):
        """
        Notification email always sent to studio; lists all open bookings
        """
        # cancelled
        for i in range(2):
            user = baker.make_recipe(
                'booking.user', first_name="Cancelled",
                last_name="User" + str(i)
            )
            baker.make_recipe(
                'booking.booking', event=self.event, status="CANCELLED",
                user=user
            )
        # free class
        for i in range(2):
            user = baker.make_recipe(
                'booking.user', first_name="Free",
                last_name="User" + str(i)
            )
            baker.make_recipe(
                'booking.booking', event=self.event, status="OPEN",
                paid=True, free_class=True, user=user
            )
        # free class with block
        blocktype = baker.make_recipe('booking.free_blocktype')
        for i in range(2):
            user = baker.make_recipe(
                'booking.user', first_name="FreeBlock",
                last_name="User" + str(i)
            )
            block = baker.make(Block, block_type=blocktype, user=user)
            baker.make_recipe(
                'booking.booking', event=self.event, status="OPEN",
                paid=True, free_class=True, user=user, block=block
            )
        free_with_block = Booking.objects.filter(
            free_class=True, block__isnull=False
        )
        # unpaid
        for i in range(2):
            user = baker.make_recipe(
                'booking.user', first_name="Unpaid",
                last_name="User" + str(i)
            )
            baker.make_recipe(
                'booking.booking', event=self.event, status="OPEN",
                paid=False, user=user
            )
        # block
        for i in range(2):
            user = baker.make_recipe(
                'booking.user', first_name="Block",
                last_name="User" + str(i)
            )
            block = baker.make_recipe(
                'booking.block', block_type__event_type=self.event.event_type,
                user=user
            )
            baker.make_recipe(
                'booking.booking', event=self.event, status="OPEN", block=block,
                paid=True, user=user
            )
        # direct paid
        for i in range(2):
            user = baker.make_recipe(
                'booking.user', first_name="Direct",
                last_name="User" + str(i)
            )
            baker.make_recipe(
                'booking.booking', event=self.event, status="OPEN",
                paid=True, free_class=False, user=user
            )
        direct_bookings = Booking.objects.filter(
            event=self.event, paid=True, block=None, free_class=False
        )

        # deposit only paid
        for i in range(2):
            user = baker.make_recipe(
                'booking.user', first_name="Deposit",
                last_name="User" + str(i)
            )
            baker.make_recipe(
                'booking.booking', event=self.event, status="OPEN",
                paid=False, deposit_paid=True, free_class=False, user=user
            )
        deposit_only = Booking.objects.filter(
            event=self.event, paid=True, block=None, free_class=False
        )

        self.assertEqual(Booking.objects.filter(event=self.event).count(), 14)
        self.client.force_login(self.staff_user)
        resp = self.client.post(self.event_url, {'confirm': 'Yes, cancel this event'})
        # sends one email per open booking (not already cancelled) and one to
        # studio
        self.assertEqual(len(mail.outbox), 13)

        studio_email = mail.outbox[-1]
        self.assertEqual(studio_email.to, [settings.DEFAULT_STUDIO_EMAIL])
        self.assertIn('Direct User0', studio_email.body)
        self.assertIn('Direct User1', studio_email.body)
        self.assertIn('Free User0', studio_email.body)
        self.assertIn('Free User1', studio_email.body)
        self.assertNotIn('Cancelled User0', studio_email.body)
        self.assertNotIn('Cancelled User1', studio_email.body)
        self.assertIn('Unpaid User0', studio_email.body)
        self.assertIn('Unpaid User1', studio_email.body)
        self.assertIn('FreeBlock User0', studio_email.body)
        self.assertIn('FreeBlock User1', studio_email.body)
        self.assertIn('Block User0', studio_email.body)
        self.assertIn('Block User1', studio_email.body)
        self.assertIn('Deposit User0', studio_email.body)
        self.assertIn('Deposit User1', studio_email.body)

        refunds_due_ids = [
            booking.id for booking in
            list(direct_bookings) + list(free_with_block) + list(deposit_only)
            ]
        for id in refunds_due_ids:
            self.assertIn(
                '/studioadmin/confirm-refunded/{}'.format(id), studio_email.body
            )

    @patch('studioadmin.views.events.send_mail')
    def test_email_errors(self, mock_send):
        mock_send.side_effect = Exception('Error sending email')
        # direct paid
        baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            paid=True, free_class=False,
        )

        self.assertEqual(Booking.objects.filter(event=self.event).count(), 1)

        self.client.force_login(self.staff_user)
        resp = self.client.post(self.event_url, {'confirm': 'Yes, cancel this event'})
        # sends one error email per open booking and one to studio
        self.assertEqual(len(mail.outbox), 2)
        for email in mail.outbox:
            self.assertEqual(email.to, [settings.SUPPORT_EMAIL])
        self.assertEqual(
            mail.outbox[0].subject,
            '{} An error occurred! (cancel event - send notification email '
            'to user)'.format(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX)
        )
        self.assertEqual(
            mail.outbox[1].subject,
            '{} An error occurred! (cancel event - send refund notification '
            'email to studio)'.format(settings.ACCOUNT_EMAIL_SUBJECT_PREFIX)
        )

        self.event.refresh_from_db()
        self.assertTrue(self.event.cancelled)

    def test_transfer_blocks_for_CL(self):
        """
        cancelling a class creates transfer blocks for direct paid and free non
        block if transfer option selected (default)
        - no transfer blocks for block paid/unpaid/free block/deposit only paid

        """
        pole_class = baker.make_recipe('booking.future_PC')

        # cancelled
        baker.make_recipe(
            'booking.booking', event=pole_class, status="CANCELLED",
        )
        # free class
        free = baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN",
            paid=True, payment_confirmed=True, free_class=True
        )
        # unpaid
        baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN", paid=False
        )
        # block
        user = baker.make_recipe('booking.user')
        block = baker.make_recipe(
            'booking.block', block_type__event_type=pole_class.event_type,
            user=user
        )
        block_paid = baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN", block=block,
            paid=True, user=user, payment_confirmed=True
        )
        # free block class
        user = baker.make_recipe('booking.user')
        f_block = baker.make_recipe(
            'booking.block', block_type__event_type=pole_class.event_type,
            block_type__identifier='free', block_type__size=1, paid=True,
            user=user
        )
        free_block = baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN", block=f_block,
            paid=True, payment_confirmed=True, free_class=True
        )
        # direct paid
        direct_paid = baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN",
            deposit_paid=True,
            paid=True, free_class=False, payment_confirmed=True
        )
        # deposit only paid
        deposit_only_paid = baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN", paid=False,
            deposit_paid=True
        )

        self.client.force_login(self.staff_user)
        url = reverse(
            'studioadmin:cancel_event', kwargs={'slug': pole_class.slug}
        )
        self.client.post(
            url,
            {
                'direct_paid_action': 'transfer',
                'confirm': 'Yes, cancel this event'
            }
        )

        transfer_btypes = BlockType.objects.filter(identifier='transferred')
        self.assertEqual(transfer_btypes.count(), 1)

        transfer_blocks = Block.objects.filter(block_type=transfer_btypes[0])
        self.assertEqual(transfer_blocks.count(), 2)
        direct_paid_transfer = transfer_blocks.get(
            transferred_booking_id=direct_paid.id
        )
        free_transfer = transfer_blocks.get(transferred_booking_id=free.id)
        self.assertEqual(
            direct_paid_transfer.block_type.event_type, pole_class.event_type
        )

        self.assertEqual(
            free_transfer.block_type.event_type, pole_class.event_type
        )

        direct_paid.refresh_from_db()
        deposit_only_paid.refresh_from_db()
        block_paid.refresh_from_db()
        free.refresh_from_db()
        free_block.refresh_from_db()

        self.assertFalse(direct_paid.paid)
        self.assertFalse(direct_paid.deposit_paid)
        self.assertFalse(direct_paid.payment_confirmed)

        self.assertTrue(deposit_only_paid.deposit_paid, True)

        self.assertIsNone(block_paid.block)
        self.assertFalse(block_paid.paid)

        self.assertFalse(free.paid)
        self.assertFalse(free.deposit_paid)
        self.assertFalse(free.payment_confirmed)

        self.assertIsNone(free_block.block)
        self.assertFalse(free_block.paid)
        self.assertFalse(free_block.payment_confirmed)

        self.assertEqual(
            Booking.objects.filter(event=pole_class, status='OPEN').count(), 0
        )

    def test_transfer_blocks_for_RH(self):
        """
        cancelling a class creates transfer blocks for direct paid if transfer
        option selected (default)
        - no transfer blocks for block paid/unpaid/free/deposit only paid

        """
        room_hire = baker.make_recipe('booking.future_RH')

        # cancelled
        baker.make_recipe(
            'booking.booking', event=room_hire, status="CANCELLED",
        )
        # free class
        free = baker.make_recipe(
            'booking.booking', event=room_hire, status="OPEN",
            paid=True, payment_confirmed=True, free_class=True
        )
        # unpaid
        baker.make_recipe(
            'booking.booking', event=room_hire, status="OPEN", paid=False
        )
        # block
        user = baker.make_recipe('booking.user')
        block = baker.make_recipe(
            'booking.block', block_type__event_type=room_hire.event_type,
            user=user
        )
        block_paid = baker.make_recipe(
            'booking.booking', event=room_hire, status="OPEN", block=block,
            paid=True, user=user, payment_confirmed=True
        )
        # free block class
        user = baker.make_recipe('booking.user')
        f_block = baker.make_recipe(
            'booking.block', block_type__event_type=room_hire.event_type,
            block_type__identifier='free', block_type__size=1, paid=True,
            user=user
        )
        free_block = baker.make_recipe(
            'booking.booking', event=room_hire, status="OPEN", block=f_block,
            paid=True, payment_confirmed=True, free_class=True
        )
        # direct paid
        direct_paid = baker.make_recipe(
            'booking.booking', event=room_hire, status="OPEN",
            deposit_paid=True,
            paid=True, free_class=False, payment_confirmed=True
        )
        # deposit only paid
        deposit_only_paid = baker.make_recipe(
            'booking.booking', event=room_hire, status="OPEN", paid=False,
            deposit_paid=True
        )

        self.client.login(username=self.staff_user.username, password='test')
        url = reverse(
            'studioadmin:cancel_event', kwargs={'slug': room_hire.slug}
        )
        self.client.post(
            url,
            {
                'direct_paid_action': 'transfer',
                'confirm': 'Yes, cancel this event'
            }
        )

        transfer_btypes = BlockType.objects.filter(identifier='transferred')
        self.assertEqual(transfer_btypes.count(), 1)

        transfer_blocks = Block.objects.filter(block_type=transfer_btypes[0])
        self.assertEqual(transfer_blocks.count(), 2)

        direct_paid_transfers = transfer_blocks.get(
            transferred_booking_id=direct_paid.id
        )
        free_paid_transfers = transfer_blocks.get(
            transferred_booking_id=free.id
        )
        self.assertEqual(
            direct_paid_transfers.block_type.event_type, room_hire.event_type
        )
        self.assertEqual(
            free_paid_transfers.block_type.event_type, room_hire.event_type
        )
        direct_paid.refresh_from_db()
        deposit_only_paid.refresh_from_db()
        block_paid.refresh_from_db()
        free.refresh_from_db()
        free_block.refresh_from_db()

        self.assertFalse(direct_paid.paid)
        self.assertFalse(direct_paid.deposit_paid)
        self.assertFalse(direct_paid.payment_confirmed)

        self.assertTrue(deposit_only_paid.deposit_paid, True)

        self.assertIsNone(block_paid.block)
        self.assertFalse(block_paid.paid)
        self.assertFalse(block_paid.payment_confirmed)

        self.assertFalse(free.paid)
        self.assertFalse(free.deposit_paid)
        self.assertFalse(free.payment_confirmed)

        self.assertIsNone(free_block.block)
        self.assertFalse(free_block.paid)
        self.assertFalse(free_block.payment_confirmed)

        self.assertEqual(
            Booking.objects.filter(event=room_hire, status='OPEN').count(), 0
        )

    def test_transfer_blocks_for_EV(self):
        """
        cancelling an event (EV) does not create transfer blocks for any
        bookings even if transfer option selected (shouldn't happen but check
        anyway)
        """
        # cancelled
        baker.make_recipe(
            'booking.booking', event=self.event, status="CANCELLED",
        )
        # free class
        free = baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            paid=True, payment_confirmed=True, free_class=True
        )
        # unpaid
        baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN", paid=False
        )
        # block
        user = baker.make_recipe('booking.user')
        block = baker.make_recipe(
            'booking.block', block_type__event_type=self.event.event_type,
            user=user
        )
        block_paid = baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN", block=block,
            paid=True, user=user, payment_confirmed=True
        )
        # free block class
        user = baker.make_recipe('booking.user')
        f_block = baker.make_recipe(
            'booking.block', block_type__event_type=self.event.event_type,
            block_type__identifier='free', block_type__size=1, paid=True,
            user=user
        )
        free_block = baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN", block=f_block,
            paid=True, payment_confirmed=True, free_class=True
        )
        # direct paid
        direct_paid = baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            deposit_paid=True,
            paid=True, free_class=False, payment_confirmed=True
        )
        # deposit only paid
        deposit_only_paid = baker.make_recipe(
            'booking.booking', event=self.event, status="OPEN", paid=False,
            deposit_paid=True
        )

        open_booking_user_emails = [
            booking.user.email for booking in Booking.objects.filter(
                event=self.event, status='OPEN'
            )
         ]
        self.client.login(username=self.staff_user.username, password='test')
        url = reverse(
            'studioadmin:cancel_event', kwargs={'slug': self.event.slug}
        )
        self.client.post(
            url,
            {
                'direct_paid_action': 'transfer',
                'confirm': 'Yes, cancel this event'
            }
        )

        transfer_btypes = BlockType.objects.filter(identifier='transferred')
        self.assertEqual(transfer_btypes.count(), 0)

        direct_paid.refresh_from_db()
        deposit_only_paid.refresh_from_db()
        block_paid.refresh_from_db()
        free.refresh_from_db()
        free_block.refresh_from_db()

        self.assertTrue(direct_paid.paid)
        self.assertTrue(direct_paid.deposit_paid)
        self.assertTrue(direct_paid.payment_confirmed)

        self.assertTrue(deposit_only_paid.deposit_paid, True)

        self.assertTrue(free.paid)
        self.assertTrue(free.free_class)

        self.assertIsNone(block_paid.block)
        self.assertFalse(block_paid.paid)

        self.assertIsNone(free_block.block)
        self.assertFalse(free_block.paid)
        self.assertFalse(free_block.payment_confirmed)

        self.assertEqual(
            Booking.objects.filter(event=self.event, status='OPEN').count(), 0
        )

        emails_to = open_booking_user_emails + [settings.DEFAULT_STUDIO_EMAIL]
        # check emails sent correctly
        self.assertCountEqual(emails_to, [email.to[0] for email in mail.outbox])

    def test_cancel_CL_with_refund_option(self):
        """
        If refund option selected, transfer blocks not created for
        direct paid and direct paid remain paid and payment confirmed
        Free non block classes also remain free/paid/payment confirmed
        """
        pole_class = baker.make_recipe('booking.future_PC')

        # cancelled
        baker.make_recipe(
            'booking.booking', event=pole_class, status="CANCELLED",
        )
        # free class
        free = baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN",
            paid=True, payment_confirmed=True, free_class=True
        )
        # unpaid
        baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN", paid=False
        )
        # block
        user = baker.make_recipe('booking.user')
        block = baker.make_recipe(
            'booking.block', block_type__event_type=pole_class.event_type,
            user=user
        )
        block_paid = baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN", block=block,
            paid=True, user=user, payment_confirmed=True
        )
        # free block class
        user = baker.make_recipe('booking.user')
        f_block = baker.make_recipe(
            'booking.block', block_type__event_type=pole_class.event_type,
            block_type__identifier='free', block_type__size=1, paid=True,
            user=user
        )
        free_block = baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN", block=f_block,
            paid=True, payment_confirmed=True, free_class=True
        )
        # direct paid
        direct_paid = baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN",
            deposit_paid=True,
            paid=True, free_class=False, payment_confirmed=True
        )
        # deposit only paid
        deposit_only_paid = baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN", paid=False,
            deposit_paid=True
        )

        self.client.login(username=self.staff_user.username, password='test')
        url = reverse(
            'studioadmin:cancel_event', kwargs={'slug': pole_class.slug}
        )
        self.client.post(
            url,
            {
                'direct_paid_action': 'refund',
                'confirm': 'Yes, cancel this event'
            }
        )

        transfer_btypes = BlockType.objects.filter(identifier='transferred')
        self.assertEqual(transfer_btypes.count(), 0)

        direct_paid.refresh_from_db()
        deposit_only_paid.refresh_from_db()
        block_paid.refresh_from_db()
        free.refresh_from_db()
        free_block.refresh_from_db()

        self.assertTrue(direct_paid.paid)
        self.assertTrue(direct_paid.deposit_paid)
        self.assertTrue(direct_paid.payment_confirmed)

        self.assertTrue(free.paid)
        self.assertTrue(free.free_class)
        self.assertTrue(free.payment_confirmed)

        self.assertTrue(deposit_only_paid.deposit_paid, True)

        self.assertIsNone(block_paid.block)
        self.assertFalse(block_paid.paid)

        self.assertIsNone(free_block.block)
        self.assertFalse(free_block.paid)
        self.assertFalse(free_block.payment_confirmed)

        self.assertEqual(
            Booking.objects.filter(event=self.event, status='OPEN').count(), 0
        )

    def test_transfer_blocks_studio_email_sent(self):
        pole_class = baker.make_recipe('booking.future_PC')

        # free class
        baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN",
            paid=True, payment_confirmed=True, free_class=True
        )
        # unpaid
        baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN", paid=False
        )
        # block
        user = baker.make_recipe('booking.user')
        block = baker.make_recipe(
            'booking.block', block_type__event_type=pole_class.event_type,
            user=user
        )
        baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN", block=block,
            paid=True, user=user, payment_confirmed=True
        )
        # free block class
        user = baker.make_recipe('booking.user')
        f_block = baker.make_recipe(
            'booking.block', block_type__event_type=pole_class.event_type,
            block_type__identifier='free', block_type__size=1, paid=True,
            user=user
        )
        baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN", block=f_block,
            paid=True, payment_confirmed=True, free_class=True
        )
        # direct paid
        direct_paid = baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN",
            deposit_paid=True,
            paid=True, free_class=False, payment_confirmed=True
        )
        _add_user_email_addresses(Booking)

        self.client.login(username=self.staff_user.username, password='test')
        url = reverse(
            'studioadmin:cancel_event', kwargs={'slug': pole_class.slug}
        )
        self.client.post(
            url,
            {
                'direct_paid_action': 'transfer',
                'confirm': 'Yes, cancel this event'
            }
        )

        cancelled_bookings = Booking.objects.filter(event=pole_class).count()
        emails = mail.outbox
        # emails sent to users and studio
        self.assertEqual(len(emails), cancelled_bookings + 1)

    def test_transfer_blocks_studio_email_sent_for_deposit_only_paid(self):
        pole_class = baker.make_recipe('booking.future_PC')

        # free class
        baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN",
            paid=True, payment_confirmed=True, free_class=True
        )
        # unpaid
        baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN", paid=False
        )
        # block
        user = baker.make_recipe('booking.user')
        block = baker.make_recipe(
            'booking.block', block_type__event_type=pole_class.event_type,
            user=user
        )
        baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN", block=block,
            paid=True, user=user, payment_confirmed=True
        )
        # free block class
        user = baker.make_recipe('booking.user')
        f_block = baker.make_recipe(
            'booking.block', block_type__event_type=pole_class.event_type,
            block_type__identifier='free', block_type__size=1, paid=True,
            user=user
        )
        baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN", block=f_block,
            paid=True, payment_confirmed=True, free_class=True
        )
        # direct paid
        baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN",
            deposit_paid=True,
            paid=True, free_class=False, payment_confirmed=True
        )

        # deposit only paid
        baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN", paid=False,
            deposit_paid=True
        )
        _add_user_email_addresses(Booking)

        self.client.login(username=self.staff_user.username, password='test')
        url = reverse(
            'studioadmin:cancel_event', kwargs={'slug': pole_class.slug}
        )
        self.client.post(
            url,
            {
                'direct_paid_action': 'transfer',
                'confirm': 'Yes, cancel this event'
            }
        )

        cancelled_bookings = Booking.objects.filter(event=pole_class).count()
        emails = mail.outbox
        # emails sent to users plus studio for deposit paid
        self.assertEqual(len(emails), cancelled_bookings + 1)

    def test_booking_with_expired_block(self):
        """
        Test that transfer credit is created for bookings booked with block
        that's now expired
        """
        pole_class = baker.make_recipe('booking.future_PC')

        # block
        user = baker.make_recipe('booking.user')
        block = baker.make_recipe(
            'booking.block', block_type__event_type=pole_class.event_type,
            user=user
        )
        self.assertFalse(block.expired)
        block_paid = baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN", block=block,
            paid=True, user=user, payment_confirmed=True
        )
        self.assertEqual(block.bookings_made(), 1)

        # expired block
        user1 = baker.make_recipe('booking.user')
        expired_block = baker.make_recipe(
            'booking.block', block_type__event_type=pole_class.event_type,
            user=user1, start_date=timezone.now() - timedelta(100),
            block_type__duration=1
        )
        self.assertTrue(expired_block.expired)
        expired_block_paid = baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN",
            block=expired_block,
            paid=True, user=user1, payment_confirmed=True
        )
        self.assertEqual(expired_block.bookings_made(), 1)

        self.client.login(username=self.staff_user.username, password='test')
        url = reverse(
            'studioadmin:cancel_event', kwargs={'slug': pole_class.slug}
        )
        self.client.post(
            url,
            {
                'direct_paid_action': 'transfer',
                'confirm': 'Yes, cancel this event'
            }
        )

        transfer_btypes = BlockType.objects.filter(identifier='transferred')
        self.assertEqual(transfer_btypes.count(), 1)

        # transfer block made for the expired block booking only
        transfer_blocks = Block.objects.filter(block_type=transfer_btypes[0])
        self.assertEqual(transfer_blocks.count(), 1)

        block.refresh_from_db()
        expired_block.refresh_from_db()
        self.assertEqual(block.bookings_made(), 0)
        self.assertEqual(expired_block.bookings_made(), 0)

        block_paid.refresh_from_db()
        expired_block_paid.refresh_from_db()

        self.assertFalse(block_paid.paid)
        self.assertFalse(block_paid.deposit_paid)
        self.assertFalse(block_paid.payment_confirmed)

        self.assertFalse(expired_block_paid.paid)
        self.assertFalse(expired_block_paid.deposit_paid)
        self.assertFalse(expired_block_paid.payment_confirmed)

        self.assertEqual(
            Booking.objects.filter(event=pole_class, status='OPEN').count(), 0
        )

    def test_booking_with_block_that_expires_in_less_than_one_month(self):
        """
        Test that blocks that expire in <1 month show a warning in the email to
        users
        """
        pole_class = baker.make_recipe('booking.future_PC')

        # block
        user = baker.make_recipe('booking.user', email='block@user.com')
        block = baker.make_recipe(
            'booking.block', block_type__event_type=pole_class.event_type,
            user=user
        )
        self.assertFalse(block.expired)
        baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN", block=block,
            paid=True, user=user, payment_confirmed=True
        )
        self.assertEqual(block.bookings_made(), 1)

        # block expiring soon
        user1 = baker.make_recipe('booking.user', email='expiringblock@user.com')
        expiring_block = baker.make_recipe(
            'booking.block', block_type__event_type=pole_class.event_type,
            user=user1, start_date=timezone.now() - timedelta(25),
            block_type__duration=1
        )
        self.assertFalse(expiring_block.expired)
        baker.make_recipe(
            'booking.booking', event=pole_class, status="OPEN",
            block=expiring_block,
            paid=True, user=user1, payment_confirmed=True
        )
        self.assertEqual(expiring_block.bookings_made(), 1)

        self.client.login(username=self.staff_user.username, password='test')
        url = reverse(
            'studioadmin:cancel_event', kwargs={'slug': pole_class.slug}
        )
        self.client.post(
            url,
            {
                'direct_paid_action': 'transfer',
                'confirm': 'Yes, cancel this event'
            }
        )

        self.assertFalse(BlockType.objects.filter(identifier='transferred').exists())

        block.refresh_from_db()
        expiring_block.refresh_from_db()
        self.assertEqual(block.bookings_made(), 0)
        self.assertEqual(expiring_block.bookings_made(), 0)

        emails = mail.outbox
        email_dict = {email.to[0]: email for email in emails}
        block_user_email = email_dict['block@user.com']
        expiringblock_user_email = email_dict['expiringblock@user.com']

        self.assertIn(
            'YOUR BLOCK EXPIRES ON {}'.format(
                expiring_block.expiry_date.strftime('%d %b %Y').upper()
            ),
            expiringblock_user_email.body
        )
        self.assertNotIn(
            'YOUR BLOCK EXPIRES ON', block_user_email.body
        )


class OpenAllClassesTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.url = reverse("studioadmin:open_all_events", args=("lessons",))

    def test_open_all_events(self):
        self.client.login(username=self.staff_user.username, password='test')
        baker.make_recipe('booking.future_PC', booking_open=False, payment_open=False, visible_on_site=False, _quantity=5)
        assert Event.objects.count() == 5
        assert Event.objects.filter(booking_open=False, payment_open=False, visible_on_site=False).count() == 5
        self.client.get(self.url)
        assert Event.objects.count() == 5
        assert Event.objects.filter(booking_open=True, payment_open=True, visible_on_site=True).count() == 5

    def test_open_all_events_does_not_affect_events(self):
        self.client.login(username=self.staff_user.username, password='test')
        baker.make_recipe('booking.future_PC', booking_open=False, payment_open=False, _quantity=3)
        baker.make_recipe('booking.future_EV', booking_open=False, payment_open=False, _quantity=3)
        assert Event.objects.count() == 6
        assert Event.objects.filter(booking_open=False, payment_open=False).count() == 6
        self.client.get(self.url)
        assert Event.objects.count() == 6
        assert Event.objects.filter(booking_open=True, payment_open=True).count() == 3
        for event in Event.objects.filter(event_type__event_type='EV'):
            assert event.booking_open is False
            assert event.payment_open is False


class CloneEventTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.client.login(username=self.staff_user.username, password='test')

    def test_clone_event(self):
        event = baker.make_recipe('booking.future_PC', name="Test", booking_open=True, payment_open=True)
        baker.make_recipe('booking.booking', event=event)
        url = reverse("studioadmin:clone_event", args=(event.slug,))

        assert Event.objects.count() == 1
        assert event.bookings.count() == 1
        self.client.get(url)

        assert Event.objects.count() == 2
        cloned = Event.objects.latest("id")
        assert cloned.booking_open is False
        assert cloned.payment_open is False
        assert cloned.visible_on_site is False
        assert cloned.bookings.exists() is False
        assert event.bookings.count() == 1
        assert cloned.name == "[CLONED] Test"

        self.client.get(url)
        assert Event.objects.count() == 3
        cloned = Event.objects.latest("id")
        assert cloned.name == "[CLONED] Test_1"

        self.client.get(url)
        assert Event.objects.count() == 4
        cloned = Event.objects.latest("id")
        assert cloned.name == "[CLONED] Test_2"

        event.name = "Test_test_suffix"
        event.save()
        url = reverse("studioadmin:clone_event", args=(event.slug,))
        self.client.get(url)
        assert Event.objects.count() == 5
        cloned = Event.objects.latest("id")
        assert cloned.name == "[CLONED] Test_test_suffix"

    def test_clone_event_with_categories(self):
        event = baker.make_recipe('booking.future_PC', name="Test", booking_open=True, payment_open=True)
        baker.make_recipe('booking.booking', event=event)
        url = reverse("studioadmin:clone_event", args=(event.slug,))
        category = baker.make(FilterCategory, category="foo")
        category1 = baker.make(FilterCategory, category="bar")
        category2 = baker.make(FilterCategory, category="foobar")
        assert Event.objects.count() == 1
        assert event.bookings.count() == 1
        event.categories.add(category, category1)
        self.client.get(url)

        assert Event.objects.count() == 2
        cloned = Event.objects.latest("id")
        
        assert set(cloned.categories.values_list("category", flat=True)) == {"foo", "bar"}


@pytest.mark.django_db
def test_edit_event_get(client):
    user = create_configured_user("staff", "staff@example.com", "test", staff=True)
    event = baker.make_recipe(
            'booking.future_EV',
            date=timezone.now().replace(second=0, microsecond=0) + timedelta(2)
        )
    url = reverse(
            'studioadmin:eventedit', kwargs={'pk': event.pk}
        )
    client.force_login(user)
    resp = client.get(url)
    assert resp.status_code == 200
    form = resp.context["form"]
    assert form.initial == {
        'booking_open': event.booking_open, 
        'payment_open': event.payment_open, 
        'visible_on_site': event.visible_on_site
    }

@pytest.mark.django_db
def test_edit_event_post_no_change(client):
    user = create_configured_user("staff", "staff@example.com", "test", staff=True)
    event = baker.make_recipe(
            'booking.future_EV',
            date=timezone.now().replace(second=0, microsecond=0) + timedelta(2)
        )
    url = reverse(
            'studioadmin:eventedit', kwargs={'pk': event.pk}
        )
    client.force_login(user)
    resp = client.post(
        url,
        {
            'id': event.id,
            'booking_open': event.booking_open, 
            'payment_open': event.payment_open, 
            'visible_on_site': event.visible_on_site
        }
    )
    assert resp.status_code == 204
    assert not resp.has_header('HX-Refresh')


@pytest.mark.django_db
def test_edit_event_post_with_change(client):
    user = create_configured_user("staff", "staff@example.com", "test", staff=True)
    event = baker.make_recipe(
            'booking.future_EV',
            date=timezone.now().replace(second=0, microsecond=0) + timedelta(2),
            visible_on_site=True
        )
    url = reverse(
            'studioadmin:eventedit', kwargs={'pk': event.pk}
        )
    client.force_login(user)
    resp = client.post(
        url,
        {
            'id': event.id,
            'booking_open': event.booking_open, 
            'payment_open': event.payment_open, 
            'visible_on_site': False
        }
    )
    assert resp.status_code == 204
    assert resp.has_header('HX-Refresh')
    event.refresh_from_db()
    assert not event.visible_on_site