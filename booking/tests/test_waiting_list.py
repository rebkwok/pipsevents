from model_mommy import mommy

from django.conf import settings
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from django.core.urlresolvers import reverse
from django.test import TestCase, override_settings

from booking.models import Booking, WaitingListUser
from booking.views import BookingListView, BookingCreateView, \
    BookingDeleteView, BookingUpdateView, update_booking_cancelled, \
    EventListView, EventDetailView
from booking.tests.helpers import _create_session, TestSetupMixin
from studioadmin.tests.test_views import TestPermissionMixin
from studioadmin.views import user_bookings_view_old


class WaitingListTests(TestSetupMixin, TestCase):

    def _get_event_list(self, user, ev_type):
        url = reverse('booking:events')
        request = self.factory.get(url)
        request.user = user
        view = EventListView.as_view()
        return view(request, ev_type=ev_type)

    def _get_event_detail(self, user, event, ev_type):
        url = reverse('booking:event_detail', args=[event.slug])
        request = self.factory.get(url)
        request.user = user
        view = EventDetailView.as_view()
        return view(request, slug=event.slug, ev_type=ev_type)

    def _get_booking_list(self, user):
        url = reverse('booking:bookings')
        request = self.factory.get(url)
        request.user = user
        view = BookingListView.as_view()
        return view(request)

    def _get_booking_update(self, user, booking):
        url = reverse('booking:update_booking', args=[booking.id])
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

        view = BookingUpdateView.as_view()
        return view(request, pk=booking.id)

    def _get_booking_update_cancelled(self, user, booking):
        url = reverse('booking:update_booking_cancelled', args=[booking.id])
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

        return update_booking_cancelled(request, pk=booking.id)

    def _get_booking_create(self, user, event, extra_data={}):
        url = reverse('booking:book_event', kwargs={'event_slug': event.slug})
        store = _create_session()
        data = {'event': event.id}
        data.update(extra_data)
        request = self.factory.get(url, data)
        request.session = store
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        view = BookingCreateView.as_view()
        return view(request, event_slug=event.slug)

    def _post_booking_create(self, user, event, form_data={}):
        url = reverse('booking:book_event', kwargs={'event_slug': event.slug})
        store = _create_session()
        form_data['event'] = event.id
        request = self.factory.post(url, form_data)
        request.session = store
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        view = BookingCreateView.as_view()
        return view(request, event_slug=event.slug)

    def _booking_delete(self, user, booking):
        url = reverse('booking:delete_booking', args=[booking.id])
        session = _create_session()
        request = self.factory.delete(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        view = BookingDeleteView.as_view()
        return view(request, pk=booking.id)

    def test_waiting_list_button_on_events_list(self):
        """
        Test that a full event displays the 'Join Waiting List' button on the
        events list page
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        resp = self._get_event_list(self.user, "lessons")
        resp.render()
        self.assertIn('book_button', str(resp.content))
        self.assertNotIn('join_waiting_list_button', str(resp.content))

        mommy.make_recipe('booking.booking', event=event)
        resp = self._get_event_list(self.user, "lessons")
        resp.render()
        self.assertIn('join_waiting_list_button', str(resp.content))
        self.assertNotIn('book_button', str(resp.content))

    def test_event_list_for_booked_full_event(self):
        """
        Test that a full event that the user is already booked for does not
        display 'Join waiting list'
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        mommy.make_recipe('booking.booking', event=event, user=self.user)
        resp = self._get_event_list(self.user, "lessons")
        self.assertEquals(list(resp.context_data['booked_events']), [event.id])
        resp.render()
        self.assertNotIn('book_button', str(resp.content))
        self.assertNotIn('join_waiting_list_button', str(resp.content))

    def test_event_list_already_on_waiting_list_full_event(self):
        """
        Test that a full event that the user is already on the waiting list for
        displays 'On waiting list'
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=3)
        mommy.make_recipe(
            'booking.waiting_list_user', event=event, user=self.user
        )
        resp = self._get_event_list(self.user, "lessons")
        self.assertEquals(
            list(resp.context_data['waiting_list_events']), [event.id]
        )

        resp.render()
        self.assertNotIn('book_button', str(resp.content))
        self.assertNotIn('join_waiting_list_button', str(resp.content))
        self.assertIn('leave_waiting_list_button', str(resp.content))

    def test_waiting_list_events_context(self):
        wlevent = mommy.make_recipe('booking.future_PC', max_participants=2)
        events = mommy.make_recipe('booking.future_PC', _quantity=5)
        event = events[0]
        mommy.make_recipe('booking.booking', event=wlevent, _quantity=2)
        mommy.make_recipe(
            'booking.waiting_list_user', event=wlevent, user=self.user
        )
        mommy.make_recipe('booking.booking', event=event, user=self.user)

        resp = self._get_event_list(self.user, "lessons")
        self.assertEquals(
            list(resp.context_data['waiting_list_events']), [wlevent.id]
        )
        self.assertEquals(
            list(resp.context_data['booked_events']), [event.id]
        )

    def test_event_list_already_on_waiting_list_not_full_event(self):
        """
        Test that a not full event that the user is already on the waiting list
        for displays 'Book' button
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        mommy.make_recipe(
            'booking.waiting_list_user', event=event, user=self.user
        )
        resp = self._get_event_list(self.user, "lessons")
        self.assertEquals(
            list(resp.context_data['waiting_list_events']), [event.id]
        )

        resp.render()
        self.assertIn('book_button', str(resp.content))
        self.assertNotIn('join_waiting_list_button', str(resp.content))
        self.assertNotIn('leave_waiting_list_button', str(resp.content))

    def test_waiting_list_button_on_event_detail_list(self):
        """
        Test that a full event displays the 'Join Waiting List' button on the
        event detail page
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        resp = self._get_event_detail(self.user, event, "lesson")
        resp.render()
        self.assertIn('book_button', str(resp.content))
        self.assertNotIn('join_waiting_list_button', str(resp.content))

        mommy.make_recipe('booking.booking', event=event)
        resp = self._get_event_detail(self.user, event, "lesson")
        resp.render()
        self.assertIn('join_waiting_list_button', str(resp.content))
        self.assertNotIn('book_button', str(resp.content))

    def test_event_detail_for_booked_full_event(self):
        """
        Test that a full event that the user is already booked for does not
        display 'Join waiting list'
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        mommy.make_recipe('booking.booking', event=event, user=self.user)
        resp = self._get_event_detail(self.user, event, "lesson")
        self.assertTrue(resp.context_data['booked'])
        self.assertFalse(resp.context_data['waiting_list'])
        resp.render()
        self.assertNotIn('book_button', str(resp.content))
        self.assertNotIn('join_waiting_list_button', str(resp.content))

    def test_event_detail_already_on_waiting_list_full_event(self):
        """
        Test that a full event that the user is already on the waiting list for
        displays 'On waiting list'
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=3)
        mommy.make_recipe(
            'booking.waiting_list_user', event=event, user=self.user
        )
        resp = self._get_event_detail(self.user, event,  "lesson")
        self.assertTrue(resp.context_data['waiting_list'])
        resp.render()
        self.assertNotIn('book_button', str(resp.content))
        self.assertNotIn('join_waiting_list_button', str(resp.content))
        self.assertIn('leave_waiting_list_button', str(resp.content))

    def test_event_detail_already_on_waiting_list_not_full_event(self):
        """
        Test that a not full event that the user is already on the waiting list
        for displays 'book_button' button
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        mommy.make_recipe(
            'booking.waiting_list_user', event=event, user=self.user
        )
        resp = self._get_event_detail(self.user, event, "lesson")
        self.assertTrue(resp.context_data['waiting_list'])
        resp.render()
        self.assertIn('book_button', str(resp.content))
        self.assertNotIn('join_waiting_list_button', str(resp.content))
        self.assertNotIn('leave_waiting_list_button', str(resp.content))

    def test_booking_list_cancelled_booking(self):
        """
        Test that a cancelled booking shows 'join waiting list' button if
        event is full
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        mommy.make_recipe(
            'booking.booking', event=event, user=self.user, status='CANCELLED'
        )
        resp = self._get_booking_list(self.user)
        resp.render()
        self.assertIn('rebook_button', str(resp.content))

        mommy.make_recipe('booking.booking', event=event)
        resp = self._get_booking_list(self.user)
        resp.render()
        self.assertNotIn('rebook_button', str(resp.content))
        self.assertNotIn('leave_waiting_list_button', str(resp.content))
        self.assertIn('join_waiting_list_button', str(resp.content))

    def test_booking_list_cancelled_booking_already_on_waiting_list(self):
        """
        Test that a cancelled booking shows 'on waiting list' button if
        event is full and user already on the waiting list
        """
        event = mommy.make_recipe(
            'booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        mommy.make_recipe(
            'booking.booking', event=event, user=self.user, status='CANCELLED'
        )
        mommy.make_recipe(
            'booking.waiting_list_user', user=self.user, event=event
        )
        resp = self._get_booking_list(self.user)
        resp.render()
        # user is on waiting list, but event not full; show "Rebook"
        self.assertIn('rebook', str(resp.content))

        mommy.make_recipe('booking.booking', event=event)
        resp = self._get_booking_list(self.user)
        resp.render()
        # user is on waiting list, event is full; show "On waiting list"
        self.assertIn('leave_waiting_list_button', str(resp.content))
        self.assertNotIn('rebook_button', str(resp.content))
        self.assertNotIn('join_waiting_list_button', str(resp.content))

    def test_cancelled_booking_for_non_bookable_not_full_event(self):
        """
        Regression test: if an event is cancelled, bookings on it are
        cancelled.  If it's reopened, booking_open and payment_open are set to
        False.  Cancelled bookings are still listed on booking page but can't
        be rebooked.  Previously this was incorrectly showing 'join waiting
        list' button.  Should show disabled 'rebook' buttong
        """
        # event is not full but booking_open is False, so it's not bookable
        event = mommy.make_recipe(
            'booking.future_PC', max_participants=3, booking_open=False
        )
        mommy.make_recipe(
            'booking.booking', event=event, user=self.user, status='CANCELLED'
        )
        resp = self._get_booking_list(self.user)
        self.assertIn('rebook_button_disabled', resp.rendered_content)

    def test_join_waiting_list(self):
        """
        Test that joining waiting list add WaitingListUser to event and
        redirects to bookings list
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=3)

        self.assertEqual(WaitingListUser.objects.count(), 0)
        resp = self._get_booking_create(
            self.user, event,
            {
                'join waiting list': ['Join waiting list'],
                'bookings': ['bookings']
            }
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:bookings'))

        waiting_list = WaitingListUser.objects.filter(event=event)
        self.assertEqual(len(waiting_list), 1)
        self.assertEqual(waiting_list[0].user, self.user)

    def test_join_waiting_list_from_event_view(self):
        """
        Test that joining waiting list from event view ('bookings' not in GET)
        adds WaitingListUser to event and redirects to events list
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=3)

        self.assertEqual(WaitingListUser.objects.count(), 0)
        resp = self._get_booking_create(
            self.user, event,
            {
                'join waiting list': ['Join waiting list'],
            }
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:lessons'))

        waiting_list = WaitingListUser.objects.filter(event=event)
        self.assertEqual(len(waiting_list), 1)
        self.assertEqual(waiting_list[0].user, self.user)

    def test_leave_waiting_list(self):
        """
        Test that leaving waiting list removes WaitingListUser to event and
        redirects to bookings list
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=3)
        mommy.make_recipe(
            'booking.waiting_list_user', user=self.user, event=event
        )
        self.assertEqual(WaitingListUser.objects.count(), 1)
        resp = self._get_booking_create(
            self.user, event,
            {
                'leave waiting list': ['Leave waiting list'],
                'bookings': ['bookings']
            }
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:bookings'))

        self.assertEqual(WaitingListUser.objects.count(), 0)

    def test_leave_waiting_list_from_event_view(self):
        """
        Test that leaving waiting list from event view ('bookings' not in GET)
        removes WaitingListUser from event and
        redirects to events list
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=3)
        mommy.make_recipe(
            'booking.waiting_list_user', user=self.user, event=event
        )
        self.assertEqual(WaitingListUser.objects.count(), 1)
        resp = self._get_booking_create(
            self.user, event,
            {
                'leave waiting list': ['Leave waiting list'],
            }
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:lessons'))

        self.assertEqual(WaitingListUser.objects.count(), 0)

    def test_try_to_leave_waiting_list_when_not_on_it(self):
        """
        Test that leaving waiting list when not on it just redirects to
        bookings page
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=3)
        self.assertEqual(WaitingListUser.objects.count(), 0)
        resp = self._get_booking_create(
            self.user, event,
            {
                'leave waiting list': ['Leave waiting list'],
                'bookings': ['bookings']
            }
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:bookings'))

        self.assertEqual(WaitingListUser.objects.count(), 0)

    def test_already_on_waiting_list(self):
        """
        Test that trying to join waiting list when already on it does add
        another WaitingListUser and redirects to events list
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=3)
        # create waiting list user for this user and event
        mommy.make_recipe(
            'booking.waiting_list_user', user=self.user, event=event
        )
        self.assertEqual(WaitingListUser.objects.count(), 1)
        resp = self._get_booking_create(
            self.user, event, {
                'join waiting list': ['Join waiting list'],
                'bookings': ['bookings']
            }
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:bookings'))
        waiting_list = WaitingListUser.objects.filter(event=event)
        # still only one waiting list user
        self.assertEqual(len(waiting_list), 1)

    def test_booking_when_already_on_waiting_list(self):
        """
        Test that when booking, a user is removed from the waiting list
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        # create waiting list user for this user and event
        mommy.make_recipe(
            'booking.waiting_list_user', user=self.user, event=event
        )
        self.assertEqual(WaitingListUser.objects.count(), 1)
        self.assertEqual(Booking.objects.filter(event=event).count(), 2)
        resp = self._post_booking_create(self.user, event)
        waiting_list = WaitingListUser.objects.filter(event=event)
        # user now removed from waiting list
        self.assertEqual(len(waiting_list), 0)
        self.assertEqual(Booking.objects.filter(event=event).count(), 3)
        booking = Booking.objects.filter(event=event).last()
        self.assertEqual(booking.user, self.user)

    def test_booking_only_removes_current_user_from_waiting_list(self):
        """
        Test that when booking, a user is removed from the waiting list but
        other users remain on the waiting list
        """
        event = mommy.make_recipe('booking.future_PC', max_participants=3)
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        # create waiting list user for this user and event
        mommy.make_recipe(
            'booking.waiting_list_user', user=self.user, event=event
        )
        mommy.make_recipe(
            'booking.waiting_list_user', event=event, _quantity=5
        )
        waiting_list = WaitingListUser.objects.filter(event=event)
        self.assertEqual(waiting_list.count(), 6)
        self.assertEqual(Booking.objects.filter(event=event).count(), 2)
        resp = self._post_booking_create(self.user, event)

        # user now removed from waiting list
        waiting_list = WaitingListUser.objects.filter(event=event)
        self.assertEqual(waiting_list.count(), 5)
        self.assertEqual(Booking.objects.filter(event=event).count(), 3)
        booking = Booking.objects.filter(event=event).last()
        self.assertEqual(booking.user, self.user)

        waiting_list_users = [wluser.user for wluser in waiting_list]
        self.assertNotIn(self.user, waiting_list_users)

    def test_update_cancelled_booking(self):
        """
        If booking is cancelled and we try to go to update page, we
        redirect to update_booking_cancelled, which shows rebook
        button
        """
        event = mommy.make_recipe('booking.future_PC')
        booking = mommy.make_recipe(
            'booking.booking',
            user=self.user, event=event, status='CANCELLED'
        )

        resp = self._get_booking_update(self.user, booking)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url,
            reverse(
                'booking:update_booking_cancelled', args=[booking.id]
            )
        )

        resp = self._get_booking_update_cancelled(self.user, booking)
        self.assertIn('rebook_button', str(resp.content))

    def test_update_cancelled_booking_full_event(self):
        """
        If booking is cancelled and we try to go to update page, we
        redirect to update_booking_cancelled, which shows join waiting
        list button if the event is full
        """
        event = mommy.make_recipe(
            'booking.future_PC',
            max_participants=3
        )
        mommy.make_recipe(
            'booking.booking', event=event, _quantity=3
        )
        booking = mommy.make_recipe(
            'booking.booking',
            user=self.user, event=event, status='CANCELLED'
        )

        resp = self._get_booking_update(self.user, booking)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url,
            reverse(
                'booking:update_booking_cancelled', args=[booking.id]
            )
        )

        resp = self._get_booking_update_cancelled(self.user, booking)
        self.assertIn('join_waiting_list_button', str(resp.content))

    def test_deleting_booking_emails_waiting_list(self):
        """
        Test that when a user cancels from a full booking, any
        users on the waiting list are emailed by bcc
        """
        event = mommy.make_recipe(
            'booking.future_PC',
            max_participants=3
        )
        mommy.make_recipe(
            'booking.booking', event=event, _quantity=2
        )
        booking = mommy.make_recipe(
            'booking.booking',
            user=self.user, event=event
        )
        for i in range(3):
            mommy.make_recipe(
                'booking.waiting_list_user', event=event,
                user__email='test{}@test.com'.format(i)
            )

        self.assertEqual(
            Booking.objects.filter(event=event, status='OPEN').count(),
            3
        )
        self._booking_delete(self.user, booking)
        self.assertEqual(
            Booking.objects.filter(event=event, status='OPEN').count(),
            2
        )
        # 2 emails are sent on cancelling; cancel email to user and
        # a single email with bcc to waiting list users
        self.assertEqual(len(mail.outbox), 2)
        wl_email = mail.outbox[1]
        self.assertEqual(
            sorted(wl_email.bcc),
            ['test0@test.com', 'test1@test.com', 'test2@test.com']
        )

    @override_settings(AUTO_BOOK_EMAILS=['foo@test.com'])
    def test_auto_book_user_on_waiting_list(self):
        """
        Test that emails listed in AUTO_BOOK_EMAILS are automatically booked
        if on waiting list
        """
        event = mommy.make_recipe(
            'booking.future_PC',
            max_participants=3
        )
        mommy.make_recipe(
            'booking.booking', event=event, _quantity=2
        )
        booking = mommy.make_recipe(
            'booking.booking',
            user=self.user, event=event
        )
        for i in range(3):
            mommy.make_recipe(
                'booking.waiting_list_user', event=event,
                user__email='test{}@test.com'.format(i)
            )

        self.assertEqual(
            Booking.objects.filter(event=event, status='OPEN').count(),
            3
        )
        self._booking_delete(self.user, booking)
        # Now there are only 2 booking; no auto-bookings made
        self.assertEqual(
            Booking.objects.filter(event=event, status='OPEN').count(),
            2
        )

        # foo@test.com on waiting list
        mommy.make_recipe(
            'booking.waiting_list_user', event=event,
            user__email='foo@test.com'
        )

        # make and delete booking again
        booking.status = 'OPEN'
        booking.save()
        self.assertEqual(
            Booking.objects.filter(event=event, status='OPEN').count(),
            3
        )

        self._booking_delete(self.user, booking)
        # there are still 3 bookings because foo@test.com has been auto-booked
        self.assertEqual(
            Booking.objects.filter(event=event, status='OPEN').count(),
            3
        )
        event.refresh_from_db()

        self.assertIn(
            'foo@test.com',
            [booking.user.email for booking in event.bookings.all()]
        )

        # 4 emails in mail box;
        # First booking cancellation: cancel email to user and
        # a single email with bcc to waiting list users
        # 2nd cancellation: cancel email to user, one email to auto booked
        #     user, no waiting list email
        self.assertEqual(len(mail.outbox), 4)
        auto_book_email = mail.outbox[3]
        self.assertEqual(auto_book_email.to, ['foo@test.com'])
        self.assertEqual(
            auto_book_email.subject,
            '{} You have been booked into {}'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, event
            )
        )

    @override_settings(AUTO_BOOK_EMAILS=['foo@test.com', 'bar@test.com'])
    def test_auto_book_only_first_user(self):
        """
        Test that only one auto booking is made, and only for the first email
        in the AUTO_BOOK_EMAILS list
        """
        event = mommy.make_recipe(
            'booking.future_PC',
            max_participants=3
        )
        mommy.make_recipe(
            'booking.booking', event=event, _quantity=2
        )
        booking = mommy.make_recipe(
            'booking.booking',
            user=self.user, event=event
        )
        for i in range(3):
            mommy.make_recipe(
                'booking.waiting_list_user', event=event,
                user__email='test{}@test.com'.format(i)
            )
        for email in settings.AUTO_BOOK_EMAILS:
            mommy.make_recipe(
                'booking.waiting_list_user', event=event,
                user__email=email
            )

        self.assertEqual(
            Booking.objects.filter(event=event, status='OPEN').count(),
            3
        )
        self._booking_delete(self.user, booking)
        # there are still 3 bookings because foo@test.com has been auto-booked
        self.assertEqual(
            Booking.objects.filter(event=event, status='OPEN').count(),
            3
        )
        event.refresh_from_db()
        # only the first email in the list is autobooked
        self.assertNotIn(
            'bar@test.com',
            [booking.user.email for booking in event.bookings.all()]
        )
        self.assertIn(
            'bar@test.com',
            [wl.user.email for wl in event.waitinglistusers.all()]
        )
        self.assertNotIn(
            'foo@test.com',
            [wl.user.email for wl in event.waitinglistusers.all()]
        )

    @override_settings(AUTO_BOOK_EMAILS=['foo@test.com'])
    def test_auto_book_user_already_booked(self):
        """
        Test that if autobook user is already booked, the next autobook user
        on the list is booked instead.  If no more autobook users, send the
        waiting list email.
        """
        auto_book_user = mommy.make_recipe(
            'booking.user', email='foo@test.com'
        )
        event = mommy.make_recipe(
            'booking.future_PC', name='Test event',
            max_participants=3
        )
        # Full event, and booked by an auto book user
        mommy.make_recipe('booking.booking', event=event)
        mommy.make_recipe('booking.booking', event=event, user=auto_book_user)
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event
        )
        for i in range(3):
            mommy.make_recipe(
                'booking.waiting_list_user', event=event,
                user__email='test{}@test.com'.format(i)
            )

        # auto book user is also on waiting list
        mommy.make_recipe(
            'booking.waiting_list_user', event=event, user=auto_book_user
        )

        self.assertEqual(
            Booking.objects.filter(event=event, status='OPEN').count(),
            3
        )
        self.assertEqual(
            WaitingListUser.objects.filter(event=event).count(), 4
        )
        self._booking_delete(self.user, booking)

        # there are now only 2 bookings because foo@test.com is already booked
        self.assertEqual(
            Booking.objects.filter(event=event, status='OPEN').count(),
            2
        )
        # Auto book user removed from waiting list
        self.assertEqual(
            WaitingListUser.objects.filter(event=event).count(), 3
        )

        # 2 emails in waiting list: cancel email and waitinglist email
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(
            mail.outbox[0].subject,
            "{} Booking for {} cancelled".format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, event.name
            )
        )
        self.assertIn(
            "A space has become available for {}".format(event),
            mail.outbox[1].body
        )

    @override_settings(AUTO_BOOK_EMAILS=['foo@test.com', 'bar@test.com'])
    def test_first_auto_book_user_already_booked(self):
        """
        Test that if autobook user is already booked, the next autobook user
        on the list is booked instead.  If no more autobook users, send the
        waiting list email.
        """
        auto_book_user = mommy.make_recipe(
            'booking.user', email='foo@test.com'
        )
        event = mommy.make_recipe(
            'booking.future_PC', name='Test event',
            max_participants=3
        )
        # Full event, and booked by first auto book user
        mommy.make_recipe('booking.booking', event=event)
        mommy.make_recipe('booking.booking', event=event, user=auto_book_user)
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event
        )
        for i in range(3):
            mommy.make_recipe(
                'booking.waiting_list_user', event=event,
                user__email='test{}@test.com'.format(i)
            )

        # both auto book users are on waiting list
        mommy.make_recipe(
            'booking.waiting_list_user', event=event, user=auto_book_user
        )
        mommy.make_recipe(
            'booking.waiting_list_user', event=event,
            user__email='bar@test.com'
        )

        self.assertEqual(
            Booking.objects.filter(event=event, status='OPEN').count(),
            3
        )
        self.assertEqual(
            WaitingListUser.objects.filter(event=event).count(), 5
        )
        self._booking_delete(self.user, booking)

        # there are still 3 bookings because bar@test.com has been autobooked
        self.assertEqual(
            Booking.objects.filter(event=event, status='OPEN').count(),
            3
        )
        # Both auto book users removed from waiting list
        self.assertEqual(
            WaitingListUser.objects.filter(event=event).count(), 3
        )

        # 2 emails in waiting list: cancel email and autobook email
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(
            mail.outbox[0].subject,
            "{} Booking for {} cancelled".format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, event.name
            )
        )
        self.assertEqual(
           mail.outbox[1].subject,
           "{} You have been booked into {}".format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, event
            )
        )
        self.assertEqual(
           mail.outbox[1].to, ['bar@test.com']
        )

    @override_settings(AUTO_BOOK_EMAILS=['foo@test.com'])
    def test_auto_book_user_has_cancelled_booking(self):
        """
        Test that if autobook user has previously booked and cancelled,
        their booking is reopened
        """
        auto_book_user = mommy.make_recipe(
            'booking.user', email='foo@test.com'
        )
        event = mommy.make_recipe(
            'booking.future_PC', name='Test event',
            max_participants=3
        )

        # Full event, and booked/cancelled by an auto book user
        mommy.make_recipe(
            'booking.booking', event=event, user=auto_book_user,
            status='CANCELLED'
        )
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event
        )
        for i in range(3):
            mommy.make_recipe(
                'booking.waiting_list_user', event=event,
                user__email='test{}@test.com'.format(i)
            )

        # auto book user is also on waiting list
        mommy.make_recipe(
            'booking.waiting_list_user', event=event, user=auto_book_user
        )

        self.assertEqual(
            Booking.objects.filter(event=event, status='OPEN').count(),
            3
        )
        self.assertEqual(
            WaitingListUser.objects.filter(event=event).count(), 4
        )
        self._booking_delete(self.user, booking)

        # there are still 3 bookings because foo@test.com has been repopened
        self.assertEqual(
            Booking.objects.filter(event=event, status='OPEN').count(),
            3
        )
        # Auto book user removed from waiting list
        self.assertEqual(
            WaitingListUser.objects.filter(event=event).count(), 3
        )

        # 2 emails in waiting list: cancel email and autobook email
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(
            mail.outbox[0].subject,
            "{} Booking for {} cancelled".format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, event.name
            )
        )
        self.assertEqual(
            mail.outbox[1].subject,
            "{} You have been booked into {}".format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, event
            )
        )
        self.assertEqual(mail.outbox[1].to, ['foo@test.com'])

    @override_settings(AUTO_BOOK_EMAILS=['foo@test.com'])
    def test_admin_link_in_auto_book_user_emails(self):
        """Test only show admin link in email if autobook user is superuser"""
        auto_book_user = mommy.make_recipe(
            'booking.user', email='foo@test.com'
        )
        event = mommy.make_recipe(
            'booking.future_PC', name='Test event',
            max_participants=3
        )

        # Full event
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        booking = mommy.make_recipe(
            'booking.booking', user=self.user, event=event
        )
        # auto book user is on waiting list
        mommy.make_recipe(
            'booking.waiting_list_user', event=event, user=auto_book_user
        )

        self.assertEqual(
            Booking.objects.filter(event=event, status='OPEN').count(),
            3
        )
        self._booking_delete(self.user, booking)

        # there are still 3 bookings because foo@test.com has been booked
        self.assertEqual(
            Booking.objects.filter(event=event, status='OPEN').count(),
            3
        )

        # 2 emails in waiting list: cancel email and autobook email
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[1].to, ['foo@test.com'])
        self.assertIn('Pay for this booking', mail.outbox[1].body)
        self.assertIn('Cancel this booking', mail.outbox[1].body)
        self.assertNotIn('Your admin page', mail.outbox[1].body)

        # make autobook user superuser
        auto_book_user.is_superuser = True
        auto_book_user.save()
        # delete booking, rebook self.user and add autobook user to WL again
        Booking.objects.get(event=event, user=auto_book_user).delete()
        booking.status = 'OPEN'
        booking.save()
        mommy.make_recipe(
            'booking.waiting_list_user', event=event, user=auto_book_user
        )

        self._booking_delete(self.user, booking)
        # 4 emails in waiting list: original 2, plus second
        # cancel email and autobook email
        self.assertEqual(len(mail.outbox), 4)
        self.assertEqual(mail.outbox[3].to, ['foo@test.com'])
        self.assertIn('Pay for this booking', mail.outbox[3].body)
        self.assertIn('Cancel this booking', mail.outbox[3].body)
        self.assertIn('Your admin page', mail.outbox[3].body)


class WaitingListStudioadminUserBookingListTests(TestPermissionMixin, TestCase):

    def _post_response(self, user, user_id, form_data):
        # helper function to create test bookings; uses the old
        # admin user booking view
        url = reverse(
            'studioadmin:user_bookings_list',
            kwargs={'user_id': user_id}
        )
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return user_bookings_view_old(request, user_id)

    def test_cancel_booking_for_full_event(self):
        """
        Cancelling a booking for a full event emails users on the
        waiting list
        """

        # make full event
        event = mommy.make_recipe(
            'booking.future_PC', max_participants=3)
        bookings = mommy.make_recipe(
            'booking.booking', event=event, _quantity=3
        )
        booking_to_cancel = bookings[0]

        # make some waiting list users
        for i in range(3):
            mommy.make_recipe(
                'booking.waiting_list_user', event=event,
                user__email='test{}@test.com'.format(i)
            )

        data = {
            'bookings-TOTAL_FORMS': 1,
            'bookings-INITIAL_FORMS': 1,
            'bookings-0-id': booking_to_cancel.id,
            'bookings-0-event': booking_to_cancel.event.id,
            'bookings-0-status': 'CANCELLED',
            'bookings-0-paid': booking_to_cancel.paid,
            }

        self.assertEqual(booking_to_cancel.status, 'OPEN')

        self._post_response(
            self.staff_user, booking_to_cancel.user.id,
            form_data=data
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            sorted(mail.outbox[0].bcc),
            ['test0@test.com', 'test1@test.com', 'test2@test.com']
        )

        booking_to_cancel.refresh_from_db()
        self.assertEqual(booking_to_cancel.status, 'CANCELLED')

    def test_cancel_booking_for_non_full_event(self):
        """
        Cancelling a booking for a not full event does not email
        users on the waiting list
        """

        # make not full event
        event = mommy.make_recipe(
            'booking.future_PC', max_participants=3)
        bookings = mommy.make_recipe(
            'booking.booking', event=event, _quantity=2
        )
        booking_to_cancel = bookings[0]

        # make some waiting list users
        mommy.make_recipe(
            'booking.waiting_list_user', event=event, _quantity=3
        )

        data = {
            'bookings-TOTAL_FORMS': 1,
            'bookings-INITIAL_FORMS': 1,
            'bookings-0-id': booking_to_cancel.id,
            'bookings-0-event': booking_to_cancel.event.id,
            'bookings-0-status': 'CANCELLED',
            'bookings-0-paid': booking_to_cancel.paid,
            }

        self.assertEqual(booking_to_cancel.status, 'OPEN')

        self._post_response(
            self.staff_user, booking_to_cancel.user.id,
            form_data=data
        )
        self.assertEqual(len(mail.outbox), 0)

        booking_to_cancel.refresh_from_db()
        self.assertEqual(booking_to_cancel.status, 'CANCELLED')

    def test_create_booking_for_user_on_waiting_list(self):
        """
        Creating a booking for a user on the waiting list for an
        event removes the user from the waiting list
        """

        # make full event
        event = mommy.make_recipe(
            'booking.future_PC', max_participants=3)

        # add self.user to waiting list users
        mommy.make_recipe(
            'booking.waiting_list_user', event=event,
            user=self.user
        )

        data = {
            'bookings-TOTAL_FORMS': 1,
            'bookings-INITIAL_FORMS': 0,
            'bookings-0-event': event.id,
            'bookings-0-status': 'OPEN',
            'bookings-0-paid': 'on',
            }

        self.assertEqual(Booking.objects.count(), 0)
        self.assertEqual(WaitingListUser.objects.count(), 1)
        self._post_response(
            self.staff_user, self.user.id, form_data=data
        )
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(WaitingListUser.objects.count(), 0)
