# -*- coding: utf-8 -*-
import pytz

from datetime import timedelta

from mock import patch

from model_mommy import mommy

from django.conf import settings
from django.core.urlresolvers import reverse
from django.core import mail
from django.test import TestCase
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone

from booking.models import Event, Booking
from booking.tests.helpers import _create_session, format_content
from studioadmin.views import (
    cancel_event_view,
    event_admin_list,
    EventAdminCreateView,
    EventAdminUpdateView,
)
from studioadmin.tests.test_views.helpers import TestPermissionMixin


class EventAdminListViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(EventAdminListViewTests, self).setUp()
        self.event = mommy.make_recipe('booking.future_EV', cost=7)

    def _get_response(self, user, ev_type, url=None):
        if not url:
            url = reverse('studioadmin:events')
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return event_admin_list(request, ev_type=ev_type)

    def _post_response(self, user, ev_type, form_data, url=None):
        if not url:
            url = reverse('studioadmin:events')
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return event_admin_list(request, ev_type=ev_type)

    def formset_data(self, extra_data={}):

        data = {
            'form-TOTAL_FORMS': 1,
            'form-INITIAL_FORMS': 1,
            'form-0-id': str(self.event.id),
            'form-0-max-participants': self.event.max_participants,
            'form-0-booking_open': self.event.booking_open,
            'form-0-payment_open': self.event.payment_open,
            'form-0-advance_payment_required': self.event.advance_payment_required
            }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse('studioadmin:events')
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user, ev_type='events')
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_cannot_access(self):
        """
        test that the page redirects if user is in the instructor group but is
        not a staff user
        """
        resp = self._get_response(self.instructor_user, ev_type='events')
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user, ev_type='events')
        self.assertEquals(resp.status_code, 200)

    def test_events_url_shows_only_events(self):
        events = mommy.make_recipe('booking.future_EV', _quantity=5)
        events.append(self.event)
        resp = self._get_response(self.staff_user, ev_type='events')

        eventsformset = resp.context_data['eventformset']

        self.assertEqual(
            sorted([ev.id for ev in eventsformset.queryset]),
            sorted([ev.id for ev in events])
        )
        self.assertIn('Scheduled Events', resp.rendered_content)

    def test_classes_url_shows_excludes_events(self):
        classes = mommy.make_recipe('booking.future_PC', _quantity=5)
        url = reverse('studioadmin:lessons')
        resp = self._get_response(self.staff_user, ev_type='classes', url=url)
        eventsformset = resp.context_data['eventformset']

        self.assertEqual(
            sorted([ev.id for ev in eventsformset.queryset]),
            sorted([ev.id for ev in classes])
        )
        self.assertIn('Scheduled Classes', resp.rendered_content)

    def test_classes_url_shows_room_hire_with_classes(self):
        classes = mommy.make_recipe('booking.future_PC', _quantity=5)
        room_hires = mommy.make_recipe('booking.future_RH', _quantity=5)
        url = reverse('studioadmin:lessons')
        resp = self._get_response(self.staff_user, ev_type='classes', url=url)
        eventsformset = resp.context_data['eventformset']

        self.assertEqual(
            sorted([ev.id for ev in eventsformset.queryset]),
            sorted([ev.id for ev in classes + room_hires])
        )
        self.assertEqual(Event.objects.count(), 11)
        self.assertEqual(eventsformset.queryset.count(), 10)

        self.assertIn('Scheduled Classes', resp.rendered_content)

    def test_past_filter(self):
        past_evs = mommy.make_recipe('booking.past_event', _quantity=5)
        resp = self._post_response(
            self.staff_user, 'events', {'past': 'Show past'}
        )

        eventsformset = resp.context_data['eventformset']
        self.assertEqual(
            sorted([ev.id for ev in eventsformset.queryset]),
            sorted([ev.id for ev in past_evs])
        )
        self.assertEqual(Event.objects.count(), 6)
        self.assertEqual(eventsformset.queryset.count(), 5)

        self.assertIn('Past Events', resp.rendered_content)
        self.assertNotIn('Scheduled Events',resp.rendered_content)

    def test_classes_past_filter(self):
        past_classes = mommy.make_recipe('booking.past_class', _quantity=5)
        resp = self._post_response(
            self.staff_user, 'lessons', {'past': 'Show past'}
        )

        eventsformset = resp.context_data['eventformset']
        self.assertEqual(
            sorted([ev.id for ev in eventsformset.queryset]),
            sorted([ev.id for ev in past_classes])
        )
        self.assertEqual(Event.objects.count(), 6)
        self.assertEqual(eventsformset.queryset.count(), 5)

        self.assertIn(
            'Past Classes', format_content(resp.rendered_content)
        )

    def test_upcoming_filter(self):
        past_evs = mommy.make_recipe('booking.past_event', _quantity=5)
        resp = self._post_response(
            self.staff_user, 'events', {'upcoming': 'Show upcoming'}
        )
        eventsformset = resp.context_data['eventformset']
        self.assertEqual(
            sorted([ev.id for ev in eventsformset.queryset]),
            [self.event.id]
        )
        self.assertEqual(Event.objects.count(), 6)
        self.assertEqual(eventsformset.queryset.count(), 1)

        self.assertIn('Scheduled Events', resp.rendered_content)
        self.assertNotIn('Past Events', resp.rendered_content)

    def test_cancel_button_shown_for_events_with_bookings(self):
        """
        Test delete checkbox is not shown for events with bookings; cancel
        button shown instead
        :return:
        """
        event = mommy.make_recipe('booking.future_EV')
        mommy.make_recipe('booking.booking', event=event)
        self.assertEquals(event.bookings.all().count(), 1)
        self.assertEquals(self.event.bookings.all().count(), 0)

        resp = self._get_response(self.staff_user, 'events')
        self.assertIn(
            'class="delete-checkbox studioadmin-list" '
            'id="DELETE_0" name="form-0-DELETE"',
            resp.rendered_content
        )
        self.assertNotIn('id="DELETE_1" name="form-1-DELETE"',
            resp.rendered_content
        )
        self.assertIn('cancel_button', resp.rendered_content)

    def test_can_delete(self):
        self.assertEquals(Event.objects.all().count(), 1)
        formset_data = self.formset_data({
            'form-0-DELETE': 'on'
            })
        self._post_response(self.staff_user, 'events', formset_data)
        self.assertEquals(Event.objects.all().count(), 0)

    def test_can_update_existing_event(self):
        self.assertTrue(self.event.booking_open)
        formset_data = self.formset_data({
            'form-0-booking_open': 'false'
            })
        self._post_response(self.staff_user, 'events', formset_data)
        self.event.refresh_from_db()
        self.assertFalse(self.event.booking_open)

    def test_submitting_valid_form_redirects_back_to_correct_url(self):
        resp = self._post_response(
            self.staff_user, 'events', self.formset_data()
        )
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('studioadmin:events'))

        resp = self._post_response(
            self.staff_user, 'lessons', self.formset_data(),
            url=reverse('studioadmin:lessons')
        )
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('studioadmin:lessons'))


class EventAdminUpdateViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(EventAdminUpdateViewTests, self).setUp()
        self.event = mommy.make_recipe(
            'booking.future_EV',
            date=timezone.now().replace(second=0, microsecond=0) + timedelta(2)
        )

    def _get_response(self, user, event_slug, ev_type, url=None):
        if url is None:
            url = reverse(
                'studioadmin:edit_event', kwargs={'slug': event_slug}
            )
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

        view = EventAdminUpdateView.as_view()
        return view(request, slug=event_slug, ev_type=ev_type)

    def _post_response(self, user, event_slug, ev_type, form_data={}, url=None):
        if url is None:
            url = reverse(
                'studioadmin:edit_event', kwargs={'slug': event_slug}
            )
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

        view = EventAdminUpdateView.as_view()
        return view(request, slug=event_slug, ev_type=ev_type)

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
            'allow_booking_cancellation': True
        }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse(
            'studioadmin:edit_event', kwargs={'slug': self.event.slug}
        )
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user, self.event.slug, 'EV')
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_cannot_access(self):
        """
        test that the page redirects if user is in the instructor group but is
        not a staff user
        """
        resp = self._get_response(self.instructor_user, self.event.slug, 'EV')
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user, self.event.slug, 'EV')
        self.assertEquals(resp.status_code, 200)

    def test_edit_event_refers_to_events_on_page_and_menu(self):
        resp = self._get_response(self.staff_user, self.event.slug, 'event')
        self.assertEquals(resp.context_data['sidenav_selection'], 'events')
        self.assertEquals(resp.context_data['type'], 'event')
        resp.render()
        self.assertIn(
            self.event.name, str(resp.content), "Content not found"
        )

    def test_edit_class_refers_to_classes_on_page_and_menu(self):
        event = mommy.make_recipe('booking.future_PC')
        resp = self._get_response(
            self.staff_user, event.slug, 'lesson',
            url=reverse('studioadmin:edit_lesson', kwargs={'slug': event.slug})
        )
        self.assertEquals(resp.context_data['sidenav_selection'], 'lessons')
        self.assertEquals(resp.context_data['type'], 'class')
        resp.render()
        self.assertIn(
            event.name, str(resp.content), "Content not found"
            )

    def test_submitting_valid_event_form_redirects_back_to_events_list(self):
        form_data = self.form_data(event=self.event)
        resp = self._post_response(
            self.staff_user, self.event.slug, 'event', form_data
        )
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('studioadmin:events'))

    def test_submitting_valid_class_form_redirects_back_to_classes_list(self):
        event = mommy.make_recipe('booking.future_PC')
        form_data = self.form_data(event=event)
        resp = self._post_response(
            self.staff_user, event.slug, 'lesson', form_data,
            url=reverse('studioadmin:edit_lesson', kwargs={'slug': event.slug})
        )
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('studioadmin:lessons'))

    def test_no_changes(self):
        form_data = self.form_data(
            event=self.event, extra_data={
                'cost': self.event.cost,
                'booking_open': self.event.booking_open
            }
        )
        self.assertTrue(
            self.client.login(
                username=self.staff_user.username, password='test'
            )
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
        resp = self._post_response(
            self.staff_user, self.event.slug, 'event', form_data
        )
        event = Event.objects.get(id=self.event.id)
        self.assertFalse(event.booking_open)

    def test_submitting_with_no_changes_does_not_change_event(self):
        form_data = self.form_data(self.event)

        resp = self._post_response(
            self.staff_user, self.event.slug, 'event', form_data
        )
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


class EventAdminCreateViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(EventAdminCreateViewTests, self).setUp()
        self.event_type_OE = mommy.make_recipe('booking.event_type_OE')
        self.event_type_PC = mommy.make_recipe('booking.event_type_PC')

    def _get_response(self, user, ev_type, url=None):
        if url is None:
            url = reverse('studioadmin:add_event')
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

        view = EventAdminCreateView.as_view()
        return view(request, ev_type=ev_type)

    def _post_response(self, user, ev_type, form_data, url=None):
        if url is None:
            url = reverse('studioadmin:add_event')
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

        view = EventAdminCreateView.as_view()
        return view(request, ev_type=ev_type)

    def form_data(self, extra_data={}):
        data = {
            'name': 'test_event',
            'event_type': self.event_type_OE.id,
            'date': '15 Jun 2015 18:00',
            'contact_email': 'test@test.com',
            'contact_person': 'test',
            'cancellation_period': 24,
            'location': 'Watermelon Studio',
            'allow_booking_cancellation': True
        }
        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse('studioadmin:add_event')
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user, 'EV')
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_cannot_access(self):
        """
        test that the page redirects if user is in the instructor group but is
        not a staff user
        """
        resp = self._get_response(self.instructor_user, 'EV')
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user, 'EV')
        self.assertEquals(resp.status_code, 200)

    def test_add_event_refers_to_events_on_page(self):
        resp = self._get_response(self.staff_user, 'event')
        self.assertEquals(resp.context_data['sidenav_selection'], 'add_event')
        self.assertEquals(resp.context_data['type'], 'event')
        resp.render()
        self.assertIn(
            'Adding new event', str(resp.content), "Content not found"
        )

    def test_add_class_refers_to_classes_on_page(self):
        resp = self._get_response(
            self.staff_user, 'lesson', url=reverse('studioadmin:add_lesson')
        )
        self.assertEquals(resp.context_data['sidenav_selection'], 'add_lesson')
        self.assertEquals(resp.context_data['type'], 'class')
        resp.render()
        self.assertIn(
            'Adding new class', str(resp.content), "Content not found"
        )

    def test_submitting_valid_event_form_redirects_back_to_events_list(self):
        form_data = self.form_data()
        resp = self._post_response(self.staff_user, 'event', form_data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:events'))

    def test_submitting_valid_class_form_redirects_back_to_classes_list(self):
        form_data = self.form_data(
            extra_data={'event_type': self.event_type_PC.id}
        )
        resp = self._post_response(
            self.staff_user, 'lesson', form_data,
            url=reverse('studioadmin:add_lesson')
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:lessons'))

    def test_can_add_event(self):
        self.assertEqual(Event.objects.count(), 0)
        form_data = self.form_data()
        resp = self._post_response(self.staff_user, 'event', form_data)
        self.assertEqual(Event.objects.count(), 1)
        event = Event.objects.first()
        self.assertEqual(event.name, 'test_event')

    def test_submitting_form_with_errors_formats_field_names(self):
        self.assertEqual(Event.objects.count(), 0)
        form_data = self.form_data({'contact_email': 'test.com'})
        resp = self._post_response(self.staff_user, 'event', form_data)

        self.assertEqual(Event.objects.count(), 0)
        self.assertIn(
            'Contact Email: Enter a valid email', resp.rendered_content
        )


class CancelEventTests(TestPermissionMixin, TestCase):

    def setUp(self):
        self.event = mommy.make_recipe(
            'booking.future_EV', cost=10, booking_open=True, payment_open=True
        )
        self.lesson = mommy.make_recipe(
            'booking.future_PC', cost=10, booking_open=True, payment_open=True
        )
        super(CancelEventTests, self).setUp()

    def _get_response(self, user, event):
        url = reverse('studioadmin:cancel_event', kwargs={'slug': event.slug})
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return cancel_event_view(request, event.slug)

    def _post_response(self, user, event, form_data):
        url = reverse('studioadmin:cancel_event', kwargs={'slug': event.slug})
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return cancel_event_view(request, event.slug)

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse(
            'studioadmin:cancel_event', kwargs={'slug': self.event.slug}
        )
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user, self.event)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user, self.event)
        self.assertEquals(resp.status_code, 200)

    def test_get_cancel_page_with_no_bookings(self):
        # no open bookings displayed on page
        resp = self._get_response(self.staff_user, self.event)
        self.assertEqual(resp.context_data['open_bookings'], [])

    def test_get_cancel_page_with_cancelled_bookings_only(self):
        # no open bookings displayed on page
        mommy.make_recipe(
            'booking.booking', event=self.event, status="CANCELLED", _quantity=3
        )

        resp = self._get_response(self.staff_user, self.event)
        self.assertEqual(resp.context_data['open_bookings'], [])

    def test_get_cancel_page_open_unpaid_bookings(self):
        # open bookings displayed on page, not in due_refunds list
        bookings = mommy.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            paid=False,
            _quantity=3
        )
        resp = self._get_response(self.staff_user, self.event)
        self.assertEqual(
            sorted([bk.id for bk in resp.context_data['open_bookings']]),
            sorted([bk.id for bk in bookings])
        )
        self.assertEqual(resp.context_data['open_direct_paid_bookings'], [])

    def test_get_cancel_page_open_block_paid_bookings(self):
        # open bookings displayed on page, not in due_refunds list

        users = mommy.make_recipe('booking.user', _quantity=3)
        for user in users:
            block = mommy.make_recipe(
                'booking.block', block_type__event_type=self.event.event_type,
                user=user
            )
            mommy.make_recipe(
                'booking.booking', event=self.event, status="OPEN", block=block,
                paid=True
        )
        bookings = Booking.objects.all()

        resp = self._get_response(self.staff_user, self.event)
        self.assertEqual(
            sorted([bk.id for bk in resp.context_data['open_bookings']]),
            sorted([bk.id for bk in bookings])
        )
        self.assertEqual(resp.context_data['open_direct_paid_bookings'], [])

    def test_get_cancel_page_open_free_class_bookings(self):
        # open bookings displayed on page, not in due_refunds list
        bookings = mommy.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            free_class=True, paid=True,
            _quantity=3
        )
        resp = self._get_response(self.staff_user, self.event)
        self.assertEqual(
            sorted([bk.id for bk in resp.context_data['open_bookings']]),
            sorted([bk.id for bk in bookings])
        )
        self.assertEqual(resp.context_data['open_direct_paid_bookings'], [])

    def test_get_cancel_page_open_direct_paid_bookings(self):
        # open bookings displayed on page, in due_refunds list
        bookings = mommy.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            paid=True, free_class=False,
            _quantity=3
        )
        resp = self._get_response(self.staff_user, self.event)
        self.assertEqual(
            sorted([bk.id for bk in resp.context_data['open_bookings']]),
            sorted([bk.id for bk in bookings])
        )
        self.assertEqual(
            sorted(
                [bk.id for bk in resp.context_data['open_direct_paid_bookings']]
            ),
            sorted([bk.id for bk in bookings])
        )

    def test_get_cancel_page_multiple_bookings(self):
        # multiple bookings, cancelled not displayed at all; all open displayed
        # in open_bookings list, only direct paid displayed in due_refunds list

        cancelled_bookings = mommy.make_recipe(
            'booking.booking', event=self.event, status="CANCELLED", _quantity=3
        )
        unpaid_bookings = mommy.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            paid=False,
            _quantity=3
        )
        free_class_bookings = mommy.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            free_class=True, paid=True,
            _quantity=3
        )
        direct_paid_bookings = mommy.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            paid=True, free_class=False,
            _quantity=3
        )
        for user in mommy.make_recipe('booking.user', _quantity=3):
            block = mommy.make_recipe(
                'booking.block', block_type__event_type=self.event.event_type,
                user=user
            )
            mommy.make_recipe(
                'booking.booking', event=self.event, status="OPEN", block=block,
                paid=True
        )
        block_bookings = list(Booking.objects.all().exclude(block=None))

        self.assertEqual(Booking.objects.filter(event=self.event).count(), 15)

        resp = self._get_response(self.staff_user, self.event)
        self.assertEqual(
            sorted([bk.id for bk in resp.context_data['open_bookings']]),
            sorted(
                [bk.id for bk in unpaid_bookings + free_class_bookings +
                                  direct_paid_bookings + block_bookings]
            )
        )
        self.assertEqual(
            sorted(
                [bk.id for bk in resp.context_data['open_direct_paid_bookings']]
            ),
            sorted([bk.id for bk in direct_paid_bookings])
        )

    def test_cancelling_event_sets_booking_and_payment_closed(self):
        """
        Cancelling and event sets cancelled to True, booking_open and
        payment_open to False
        """
        self.assertTrue(self.event.booking_open)
        self.assertTrue(self.event.payment_open)
        self.assertFalse(self.event.cancelled)

        self._post_response(
            self.staff_user, self.event, {'confirm': 'Yes, cancel this event'}
        )
        self.event.refresh_from_db()
        self.assertFalse(self.event.booking_open)
        self.assertFalse(self.event.payment_open)
        self.assertTrue(self.event.cancelled)


    def test_cancelling_event_cancels_open_block_bookings(self):
        """
        Cancelling changes block bookings to no block, not paid, not payment
        confirmed
        """
        for user in mommy.make_recipe('booking.user', _quantity=3):
            block = mommy.make_recipe(
                'booking.block', block_type__event_type=self.event.event_type,
                user=user
            )
            mommy.make_recipe(
                'booking.booking', event=self.event, status="OPEN", block=block,
                paid=True
        )

        for booking in Booking.objects.filter(event=self.event):
            self.assertIsNotNone(booking.block)
            self.assertEqual(booking.status, 'OPEN')

        self._post_response(
            self.staff_user, self.event, {'confirm': 'Yes, cancel this event'}
        )
        for booking in Booking.objects.filter(event=self.event):
            self.assertIsNone(booking.block)
            self.assertEqual(booking.status, 'CANCELLED')

    def test_cancelling_event_cancels_free_class_bookings(self):
        """
        Cancelling changes free class to not free class, not paid, not payment
        confirmed
        """
        mommy.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            free_class=True, paid=True,
            _quantity=3
        )
        for booking in Booking.objects.filter(event=self.event):
            self.assertTrue(booking.free_class)
            self.assertEqual(booking.status, 'OPEN')

        self._post_response(
            self.staff_user, self.event, {'confirm': 'Yes, cancel this event'}
        )

        for booking in Booking.objects.filter(event=self.event):
            self.assertFalse(booking.free_class)
            self.assertFalse(booking.paid)
            self.assertFalse(booking.payment_confirmed)
            self.assertEqual(booking.status, 'CANCELLED')

    def test_cancelling_event_cancels_direct_paid_bookings(self):
        """
        Cancelling changes direct paid classes to cancelled but does not change
         payment status
        """
        mommy.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            paid=True, payment_confirmed=True, free_class=False,
            _quantity=3
        )
        for booking in Booking.objects.filter(event=self.event):
            self.assertTrue(booking.paid)
            self.assertTrue(booking.payment_confirmed)
            self.assertEqual(booking.status, 'OPEN')

        self._post_response(
            self.staff_user, self.event, {'confirm': 'Yes, cancel this event'}
        )

        for booking in Booking.objects.filter(event=self.event):
            self.assertTrue(booking.paid)
            self.assertTrue(booking.payment_confirmed)
            self.assertEqual(booking.status, 'CANCELLED')

    def test_cancelling_event_redirects_to_events_list(self):
        resp = self._post_response(
            self.staff_user, self.event, {'confirm': 'Yes, cancel this event'}
        )
        self.event.refresh_from_db()
        self.assertTrue(self.event.cancelled)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:events'))

    def test_cancelling_class_redirects_to_classes_list(self):
        resp = self._post_response(
            self.staff_user, self.lesson, {'confirm': 'Yes, cancel this event'}
        )
        self.lesson.refresh_from_db()
        self.assertTrue(self.lesson.cancelled)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:lessons'))

    def test_can_abort_cancel_event_request(self):
        resp = self._post_response(
            self.staff_user, self.event, {'cancel': 'No, take me back'}
        )
        self.assertFalse(self.event.cancelled)
        self.assertTrue(self.event.booking_open)
        self.assertTrue(self.event.payment_open)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:events'))

    def test_can_abort_cancel_class_request(self):
        resp = self._post_response(
            self.staff_user, self.lesson, {'cancel': 'No, take me back'}
        )
        self.assertFalse(self.lesson.cancelled)
        self.assertTrue(self.lesson.booking_open)
        self.assertTrue(self.lesson.payment_open)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:lessons'))

    def test_open_bookings_on_aborted_cancel_request_remain_open(self):
        mommy.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            _quantity=3
        )
        self._post_response(
            self.staff_user, self.event, {'cancel': 'No, take me back'}
        )
        self.assertFalse(self.event.cancelled)
        for booking in Booking.objects.filter(event=self.event):
            self.assertEqual(booking.status, 'OPEN')

    def test_emails_sent_to_all_users_with_open_bookings(self):
        # unpaid
        mommy.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            paid=False,
            _quantity=3
        )
        # free_class
        mommy.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            free_class=True, paid=True,
            _quantity=3
        )
        # direct paid
        mommy.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            paid=True, free_class=False,
            _quantity=3
        )
        # block bookings
        for user in mommy.make_recipe('booking.user', _quantity=3):
            block = mommy.make_recipe(
                'booking.block', block_type__event_type=self.event.event_type,
                user=user
            )
            mommy.make_recipe(
                'booking.booking', event=self.event, status="OPEN", block=block,
                paid=True
        )

        self.assertEqual(Booking.objects.filter(event=self.event).count(), 12)

        self._post_response(
            self.staff_user, self.event, {'confirm': 'Yes, cancel this event'}
        )
        # sends one email per open booking and one to studio
        self.assertEquals(len(mail.outbox), 13)

    def test_emails_not_sent_to_users_with_already_cancelled_bookings(self):
        # cancelled
        mommy.make_recipe(
            'booking.booking', event=self.event, status="CANCELLED", _quantity=3
        )
        # unpaid
        mommy.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            paid=False,
            _quantity=3
        )
        # free_class
        mommy.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            free_class=True, paid=True,
            _quantity=3
        )
        # direct paid
        mommy.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            paid=True, free_class=False,
            _quantity=3
        )
        # block bookings
        for user in mommy.make_recipe('booking.user', _quantity=3):
            block = mommy.make_recipe(
                'booking.block', block_type__event_type=self.event.event_type,
                user=user
            )
            mommy.make_recipe(
                'booking.booking', event=self.event, status="OPEN", block=block,
                paid=True
            )
        self.assertEqual(Booking.objects.filter(event=self.event).count(), 15)

        self._post_response(
            self.staff_user, self.event, {'confirm': 'Yes, cancel this event'}
        )
        # sends one email per open booking (not already cancelled) and one to
        # studio
        self.assertEquals(len(mail.outbox), 13)

    def test_emails_sent_to_studio_for_direct_paid_bookings_only(self):
        # cancelled
        mommy.make_recipe(
            'booking.booking', event=self.event, status="CANCELLED", _quantity=3
        )
        # unpaid
        mommy.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            paid=False,
            _quantity=3
        )
        # free_class
        mommy.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            free_class=True, paid=True,
            _quantity=3
        )
        # block bookings
        for user in mommy.make_recipe('booking.user', _quantity=3):
            block = mommy.make_recipe(
                'booking.block', block_type__event_type=self.event.event_type,
                user=user
            )
            mommy.make_recipe(
                'booking.booking', event=self.event, status="OPEN", block=block,
                paid=True
            )
        self.assertEqual(Booking.objects.filter(event=self.event).count(), 12)

        self._post_response(
            self.staff_user, self.event, {'confirm': 'Yes, cancel this event'}
        )
        # sends one email per open booking (not already cancelled). No email to
        # studio as no direct paid bookings
        self.assertEquals(len(mail.outbox), 9)

    def test_email_to_studio_for_direct_paid_bookings_content(self):
        # cancelled
        for i in range(2):
            user = mommy.make_recipe(
                'booking.user', first_name="Cancelled",
                last_name="User" + str(i)
            )
            mommy.make_recipe(
                'booking.booking', event=self.event, status="CANCELLED",
                user=user
            )
        # free class
        for i in range(2):
            user = mommy.make_recipe(
                'booking.user', first_name="Free",
                last_name="User" + str(i)
            )
            mommy.make_recipe(
                'booking.booking', event=self.event, status="OPEN",
                paid=True, free_class=True, user=user
            )
        # unpaid
        for i in range(2):
            user = mommy.make_recipe(
                'booking.user', first_name="Unpaid",
                last_name="User" + str(i)
            )
            mommy.make_recipe(
                'booking.booking', event=self.event, status="OPEN",
                paid=False, user=user
            )
        # block
        for i in range(2):
            user = mommy.make_recipe(
                'booking.user', first_name="Block",
                last_name="User" + str(i)
            )
            block = mommy.make_recipe(
                'booking.block', block_type__event_type=self.event.event_type,
                user=user
            )
            mommy.make_recipe(
                'booking.booking', event=self.event, status="OPEN", block=block,
                paid=True, user=user
            )
        # direct paid
        for i in range(2):
            user = mommy.make_recipe(
                'booking.user', first_name="Direct",
                last_name="User" + str(i)
            )
            mommy.make_recipe(
                'booking.booking', event=self.event, status="OPEN",
                paid=True, free_class=False, user=user
            )
        direct_bookings = Booking.objects.filter(
            event=self.event, paid=True, block=None, free_class=False
        )

        self.assertEqual(Booking.objects.filter(event=self.event).count(), 10)
        self._post_response(
            self.staff_user, self.event, {'confirm': 'Yes, cancel this event'}
        )
        # sends one email per open booking (not already cancelled) and one to
        # studio
        self.assertEqual(len(mail.outbox), 9)

        studio_email = mail.outbox[-1]
        self.assertEqual(studio_email.to, [settings.DEFAULT_STUDIO_EMAIL])
        self.assertIn('Direct User0', studio_email.body)
        self.assertIn('Direct User1', studio_email.body)
        self.assertNotIn('Cancelled User0', studio_email.body)
        self.assertNotIn('Cancelled User1', studio_email.body)
        self.assertNotIn('Unpaid User0', studio_email.body)
        self.assertNotIn('Unpaid User1', studio_email.body)
        self.assertNotIn('Free User0', studio_email.body)
        self.assertNotIn('Free User1', studio_email.body)
        self.assertNotIn('Block User0', studio_email.body)
        self.assertNotIn('Block User1', studio_email.body)

        direct_bookings_ids = [booking.id for booking in direct_bookings]
        for id in direct_bookings_ids:
            self.assertIn(
                '/studioadmin/confirm-refunded/{}'.format(id), studio_email.body
            )

    @patch('studioadmin.views.events.send_mail')
    def test_email_errors(self, mock_send):
        mock_send.side_effect = Exception('Error sending email')
        # direct paid
        mommy.make_recipe(
            'booking.booking', event=self.event, status="OPEN",
            paid=True, free_class=False,
        )

        self.assertEqual(Booking.objects.filter(event=self.event).count(), 1)

        self._post_response(
            self.staff_user, self.event, {'confirm': 'Yes, cancel this event'}
        )
        # sends one error email per open booking and one to studio
        self.assertEquals(len(mail.outbox), 2)
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
