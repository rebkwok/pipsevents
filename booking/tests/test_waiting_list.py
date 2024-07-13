from model_bakery import baker

from django.conf import settings
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from django.urls import reverse
from django.test import TestCase, override_settings

from booking.models import Booking, WaitingListUser
from common.tests.helpers import _create_session, TestSetupMixin
from studioadmin.tests.test_views import TestPermissionMixin
from studioadmin.views import user_bookings_view_old


class WaitingListTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.events_url = reverse('booking:events')
        cls.classes_url = reverse('booking:lessons')
        cls.bookings_url = reverse('booking:bookings')

    def setUp(self):
        super().setUp()
        self.client.login(username=self.user, password="test")

    def event_url(self, event, ev_type):
        return reverse(f'booking:{ev_type}_detail', args=[event.slug])

    def _booking_delete(self, booking):
        url = reverse('booking:delete_booking', args=[booking.id])
        self.client.post(url)

    def test_waiting_list_button_on_events_list(self):
        """
        Test that a full event displays the 'Join Waiting List' button on the
        events list page
        """
        event = baker.make_recipe('booking.future_PC', max_participants=3)
        baker.make_recipe('booking.booking', event=event, _quantity=2)
        resp = self.client.get(self.classes_url)
        resp.render()
        assert 'book_button' in str(resp.content)
        assert 'join_waiting_list_button' not in str(resp.content)

        baker.make_recipe('booking.booking', event=event)
        resp = self.client.get(self.classes_url)
        resp.render()
        assert 'book_button' not in str(resp.content)
        assert 'join_waiting_list_button' in str(resp.content)

    def test_event_list_for_booked_full_event(self):
        """
        Test that a full event that the user is already booked for does not
        display 'Join waiting list'
        """
        event = baker.make_recipe('booking.future_PC', max_participants=3)
        baker.make_recipe('booking.booking', event=event, _quantity=2)
        baker.make_recipe('booking.booking', event=event, user=self.user)
        resp = self.client.get(self.classes_url)
        assert list(resp.context_data['booked_events']) == [event.id]
        resp.render()
        assert 'book_button' not in str(resp.content)
        assert 'join_waiting_list_button' not in str(resp.content)

    def test_event_list_already_on_waiting_list_full_event(self):
        """
        Test that a full event that the user is already on the waiting list for
        displays 'On waiting list'
        """
        event = baker.make_recipe('booking.future_PC', max_participants=3)
        baker.make_recipe('booking.booking', event=event, _quantity=3)
        baker.make_recipe(
            'booking.waiting_list_user', event=event, user=self.user
        )
        resp = self.client.get(self.classes_url)
        assert list(resp.context_data['waiting_list_events']) == [event.id]
        resp.render()
        assert 'book_button' not in str(resp.content)
        assert 'join_waiting_list_button', str(resp.content)
        assert 'leave_waiting_list_button' in str(resp.content)

    def test_waiting_list_events_context(self):
        wlevent = baker.make_recipe('booking.future_PC', max_participants=2)
        events = baker.make_recipe('booking.future_PC', _quantity=5)
        event = events[0]
        baker.make_recipe('booking.booking', event=wlevent, _quantity=2)
        baker.make_recipe(
            'booking.waiting_list_user', event=wlevent, user=self.user
        )
        baker.make_recipe('booking.booking', event=event, user=self.user)

        resp = self.client.get(self.classes_url)
        assert list(resp.context_data['waiting_list_events']) == [wlevent.id]
        assert list(resp.context_data['booked_events']) == [event.id]

    def test_event_list_already_on_waiting_list_not_full_event(self):
        """
        Test that a not full event that the user is already on the waiting list
        for displays 'Book' button
        """
        event = baker.make_recipe('booking.future_PC', max_participants=3)
        baker.make_recipe('booking.booking', event=event, _quantity=2)
        baker.make_recipe(
            'booking.waiting_list_user', event=event, user=self.user
        )
        resp = self.client.get(self.classes_url)
        assert list(resp.context_data['waiting_list_events']) == [event.id]
        resp.render()
        assert 'book_button' in str(resp.content)
        assert 'join_waiting_list_button' not in str(resp.content)
        assert 'leave_waiting_list_button' not in str(resp.content)

    def test_waiting_list_button_on_event_detail_list(self):
        """
        Test that a full event displays the 'Join Waiting List' button on the
        event detail page
        """
        event = baker.make_recipe('booking.future_PC', max_participants=3)
        baker.make_recipe('booking.booking', event=event, _quantity=2)
        resp = self.client.get(self.event_url(event, "lesson"))
        resp.render()
        assert 'book_button' in str(resp.content)
        assert 'join_waiting_list_button' not in str(resp.content)

        baker.make_recipe('booking.booking', event=event)
        resp = self.client.get(self.event_url(event, "lesson"))
        resp.render()
        assert 'join_waiting_list_button' in str(resp.content)
        assert 'book_button' not in str(resp.content)

    def test_event_detail_for_booked_full_event(self):
        """
        Test that a full event that the user is already booked for does not
        display 'Join waiting list'
        """
        event = baker.make_recipe('booking.future_PC', max_participants=3)
        baker.make_recipe('booking.booking', event=event, _quantity=2)
        baker.make_recipe('booking.booking', event=event, user=self.user)
        resp = self.client.get(self.event_url(event, "lesson"))
        assert resp.context_data['booked']
        assert resp.context_data['on_waiting_list'] is False
        resp.render()
        assert 'book_button' not in str(resp.content)
        assert 'join_waiting_list_button' not in str(resp.content)

    def test_event_detail_already_on_waiting_list_full_event(self):
        """
        Test that a full event that the user is already on the waiting list for
        displays 'On waiting list'
        """
        event = baker.make_recipe('booking.future_PC', max_participants=3)
        baker.make_recipe('booking.booking', event=event, _quantity=3)
        baker.make_recipe(
            'booking.waiting_list_user', event=event, user=self.user
        )
        resp = self.client.get(self.event_url(event, "lesson"))
        assert resp.context_data['on_waiting_list']
        resp.render()
        assert 'book_button' not in str(resp.content)
        assert 'join_waiting_list_button' not in str(resp.content)
        assert 'leave_waiting_list_button' in str(resp.content)

    def test_event_detail_already_on_waiting_list_not_full_event(self):
        """
        Test that a not full event that the user is already on the waiting list
        for displays 'book_button' button
        """
        event = baker.make_recipe('booking.future_PC', max_participants=3)
        baker.make_recipe('booking.booking', event=event, _quantity=2)
        baker.make_recipe(
            'booking.waiting_list_user', event=event, user=self.user
        )
        resp = self.client.get(self.event_url(event, "lesson"))
        assert resp.context_data['on_waiting_list']
        resp.render()
        assert 'book_button' in str(resp.content)
        assert 'join_waiting_list_button' not in str(resp.content)
        assert 'leave_waiting_list_button' not in str(resp.content)

    def test_booking_list_cancelled_booking(self):
        """
        Test that a cancelled booking shows 'join waiting list' button if
        event is full
        """
        event = baker.make_recipe('booking.future_PC', max_participants=3)
        baker.make_recipe('booking.booking', event=event, _quantity=2)
        baker.make_recipe(
            'booking.booking', event=event, user=self.user, status='CANCELLED'
        )
        resp = self.client.get(self.bookings_url)
        resp.render()
        assert 'book_button' in str(resp.content)

        baker.make_recipe('booking.booking', event=event)
        resp = self.client.get(self.bookings_url)
        resp.render()
        assert 'book_button' not in str(resp.content)
        assert 'leave_waiting_list_button' not in str(resp.content)
        assert 'join_waiting_list_button' in str(resp.content)

    def test_booking_list_cancelled_booking_already_on_waiting_list(self):
        """
        Test that a cancelled booking shows 'on waiting list' button if
        event is full and user already on the waiting list
        """
        event = baker.make_recipe(
            'booking.future_PC', max_participants=3)
        baker.make_recipe('booking.booking', event=event, _quantity=2)
        baker.make_recipe(
            'booking.booking', event=event, user=self.user, status='CANCELLED'
        )
        baker.make_recipe(
            'booking.waiting_list_user', user=self.user, event=event
        )
        resp = self.client.get(self.bookings_url)
        resp.render()
        # user is on waiting list, but event not full; show "Rebook"
        assert 'Rebook' in str(resp.content)

        baker.make_recipe('booking.booking', event=event)
        resp = self.client.get(self.bookings_url)
        resp.render()
        # user is on waiting list, event is full; show "On waiting list"
        assert 'leave_waiting_list_button' in str(resp.content)
        assert 'book_button' not in str(resp.content)
        assert 'join_waiting_list_button' not in str(resp.content)

    def test_cancelled_booking_for_non_bookable_not_full_event(self):
        """
        Regression test: if an event is cancelled, bookings on it are
        cancelled.  If it's reopened, booking_open and payment_open are set to
        False.  Cancelled bookings are still listed on booking page but can't
        be rebooked.  Previously this was incorrectly showing 'join waiting
        list' button.  Should show disabled 'rebook' buttong
        """
        # event is not full but booking_open is False, so it's not bookable
        event = baker.make_recipe(
            'booking.future_PC', max_participants=3, booking_open=False
        )
        baker.make_recipe(
            'booking.booking', event=event, user=self.user, status='CANCELLED'
        )
        resp = self.client.get(self.bookings_url)
        assert 'rebook_button_disabled' in resp.rendered_content

    def test_update_cancelled_booking(self):
        """
        If booking is cancelled and we try to go to update page, we
        redirect to update_booking_cancelled
        """
        event = baker.make_recipe('booking.future_PC')
        booking = baker.make_recipe(
            'booking.booking',
            user=self.user, event=event, status='CANCELLED'
        )

        url = reverse('booking:update_booking', args=(booking.id,))
        resp = self.client.get(url)
        assert resp.status_code == 302
        assert resp.url == reverse('booking:update_booking_cancelled', args=[booking.id])

    def test_update_cancelled_booking_full_event(self):
        """
        If booking is cancelled and we try to go to update page, we
        redirect to update_booking_cancelled, which shows the event is full
        """
        event = baker.make_recipe(
            'booking.future_PC',
            max_participants=3
        )
        baker.make_recipe(
            'booking.booking', event=event, _quantity=3
        )
        booking = baker.make_recipe(
            'booking.booking',
            user=self.user, event=event, status='CANCELLED'
        )

        url = reverse('booking:update_booking', args=(booking.id,))
        resp = self.client.get(url)
        assert resp.status_code == 302

        update_booking_cancelled_url = reverse(
            'booking:update_booking_cancelled', args=[booking.id]
        )
        assert resp.url == update_booking_cancelled_url

        resp = self.client.get(update_booking_cancelled_url)
        assert "This class is now full" in str(resp.content)

    def test_deleting_booking_emails_waiting_list(self):
        """
        Test that when a user cancels from a full booking, any
        users on the waiting list are emailed by bcc
        """
        event = baker.make_recipe(
            'booking.future_PC',
            max_participants=3
        )
        baker.make_recipe(
            'booking.booking', event=event, _quantity=2
        )
        booking = baker.make_recipe(
            'booking.booking',
            user=self.user, event=event
        )
        for i in range(3):
            baker.make_recipe(
                'booking.waiting_list_user', event=event,
                user__email='test{}@test.com'.format(i)
            )

        assert Booking.objects.filter(event=event, status='OPEN').count() == 3
        self._booking_delete(booking)
        assert Booking.objects.filter(event=event, status='OPEN').count() == 2
        # 2 emails are sent on cancelling; cancel email to user (unpaid booking) and
        # a single email with bcc to waiting list users
        assert len(mail.outbox) == 2
        wl_email = mail.outbox[1]
        assert sorted(wl_email.bcc) == ['test0@test.com', 'test1@test.com', 'test2@test.com']

    @override_settings(AUTO_BOOK_EMAILS=['foo@test.com'])
    def test_auto_book_user_on_waiting_list(self):
        """
        Test that emails listed in AUTO_BOOK_EMAILS are automatically booked
        if on waiting list
        """
        event = baker.make_recipe(
            'booking.future_PC',
            max_participants=3
        )
        baker.make_recipe(
            'booking.booking', event=event, _quantity=2
        )
        booking = baker.make_recipe(
            'booking.booking',
            user=self.user, event=event
        )
        for i in range(3):
            baker.make_recipe(
                'booking.waiting_list_user', event=event,
                user__email='test{}@test.com'.format(i)
            )

        assert Booking.objects.filter(event=event, status='OPEN').count() == 3
        self._booking_delete(booking)
        # Now there are only 2 booking; no auto-bookings made
        assert Booking.objects.filter(event=event, status='OPEN').count() == 2

        # foo@test.com on waiting list
        baker.make_recipe(
            'booking.waiting_list_user', event=event,
            user__email='foo@test.com'
        )

        # reopen and cancel booking again
        booking.status = "OPEN"
        booking.save()
        assert Booking.objects.filter(event=event, status='OPEN').count() == 3

        self._booking_delete(booking)
        # there are still 3 bookings because foo@test.com has been auto-booked
        assert Booking.objects.filter(event=event, status='OPEN').count() == 3
        event.refresh_from_db()

        assert 'foo@test.com' in [booking.user.email for booking in event.bookings.all()]

        # 4 emails in mail box;
        # First booking cancellation: 1 cancel email plus single email with bcc to waiting list users
        # 2nd cancellation: 1 cancel email, one email to auto booked user, no waiting list email
        assert len(mail.outbox) == 4
        auto_book_email = mail.outbox[-1]
        assert auto_book_email.to == ['foo@test.com']
        assert auto_book_email.subject == f'{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} You have been booked into {event}'

    @override_settings(AUTO_BOOK_EMAILS=['foo@test.com', 'bar@test.com'])
    def test_auto_book_only_first_user(self):
        """
        Test that only one auto booking is made, and only for the first email
        in the AUTO_BOOK_EMAILS list
        """
        event = baker.make_recipe(
            'booking.future_PC',
            max_participants=3
        )
        baker.make_recipe(
            'booking.booking', event=event, _quantity=2
        )
        booking = baker.make_recipe(
            'booking.booking',
            user=self.user, event=event
        )
        for i in range(3):
            baker.make_recipe(
                'booking.waiting_list_user', event=event,
                user__email='test{}@test.com'.format(i)
            )
        for email in settings.AUTO_BOOK_EMAILS:
            baker.make_recipe(
                'booking.waiting_list_user', event=event,
                user__email=email
            )

        assert Booking.objects.filter(event=event, status='OPEN').count() == 3
        self._booking_delete(booking)
        # there are still 3 bookings because foo@test.com has been auto-booked
        assert Booking.objects.filter(event=event, status='OPEN').count() == 3
        event.refresh_from_db()
        # only the first email in the list is autobooked
        assert 'bar@test.com' not in [booking.user.email for booking in event.bookings.all()]
        assert 'bar@test.com' in [wl.user.email for wl in event.waitinglistusers.all()]
        assert 'foo@test.com' not in [wl.user.email for wl in event.waitinglistusers.all()]

    @override_settings(AUTO_BOOK_EMAILS=['foo@test.com'])
    def test_auto_book_user_already_booked(self):
        """
        Test that if autobook user is already booked, the next autobook user
        on the list is booked instead.  If no more autobook users, send the
        waiting list email.
        """
        auto_book_user = baker.make_recipe(
            'booking.user', email='foo@test.com'
        )
        event = baker.make_recipe(
            'booking.future_PC', name='Test event',
            max_participants=3
        )
        # Full event, and booked by an auto book user
        baker.make_recipe('booking.booking', event=event)
        baker.make_recipe('booking.booking', event=event, user=auto_book_user)
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event
        )
        for i in range(3):
            baker.make_recipe(
                'booking.waiting_list_user', event=event,
                user__email='test{}@test.com'.format(i)
            )

        # auto book user is also on waiting list
        baker.make_recipe(
            'booking.waiting_list_user', event=event, user=auto_book_user
        )

        assert Booking.objects.filter(event=event, status='OPEN').count() == 3
        assert WaitingListUser.objects.filter(event=event).count() == 4
        self._booking_delete(booking)

        # there are now only 2 bookings because foo@test.com is already booked
        assert Booking.objects.filter(event=event, status='OPEN').count() == 2
        # Auto book user removed from waiting list
        assert WaitingListUser.objects.filter(event=event).count() == 3

        # 1 emails: waitinglist email (cancel email and watchlist email)
        assert len(mail.outbox) == 2
        assert f"A space has become available for {event}" in mail.outbox[1].body

    @override_settings(AUTO_BOOK_EMAILS=['foo@test.com', 'bar@test.com'])
    def test_first_auto_book_user_already_booked(self):
        """
        Test that if autobook user is already booked, the next autobook user
        on the list is booked instead.  If no more autobook users, send the
        waiting list email.
        """
        auto_book_user = baker.make_recipe(
            'booking.user', email='foo@test.com'
        )
        event = baker.make_recipe(
            'booking.future_PC', name='Test event',
            max_participants=3
        )
        # Full event, and booked by first auto book user
        baker.make_recipe('booking.booking', event=event)
        baker.make_recipe('booking.booking', event=event, user=auto_book_user)
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event
        )
        for i in range(3):
            baker.make_recipe(
                'booking.waiting_list_user', event=event,
                user__email='test{}@test.com'.format(i)
            )

        # both auto book users are on waiting list
        baker.make_recipe(
            'booking.waiting_list_user', event=event, user=auto_book_user
        )
        baker.make_recipe(
            'booking.waiting_list_user', event=event,
            user__email='bar@test.com'
        )

        assert Booking.objects.filter(event=event, status='OPEN').count() == 3
        assert WaitingListUser.objects.filter(event=event).count() == 5
        self._booking_delete(booking)

        # there are still 3 bookings because bar@test.com has been autobooked
        assert Booking.objects.filter(event=event, status='OPEN').count() == 3
        # Both auto book users removed from waiting list
        assert WaitingListUser.objects.filter(event=event).count() == 3

        # 1 email: cancel email and autobook email
        assert len(mail.outbox) == 2
        assert mail.outbox[1].subject == f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} You have been booked into {event}"
        assert mail.outbox[1].to == ['bar@test.com']

    @override_settings(AUTO_BOOK_EMAILS=['foo@test.com'])
    def test_auto_book_user_has_cancelled_booking(self):
        """
        Test that if autobook user has previously booked and cancelled,
        their booking is reopened
        """
        auto_book_user = baker.make_recipe(
            'booking.user', email='foo@test.com'
        )
        event = baker.make_recipe(
            'booking.future_PC', name='Test event',
            max_participants=3
        )

        # Full event, and booked/cancelled by an auto book user
        baker.make_recipe(
            'booking.booking', event=event, user=auto_book_user,
            status='CANCELLED'
        )
        baker.make_recipe('booking.booking', event=event, _quantity=2)
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event
        )
        for i in range(3):
            baker.make_recipe(
                'booking.waiting_list_user', event=event,
                user__email='test{}@test.com'.format(i)
            )

        # auto book user is also on waiting list
        baker.make_recipe(
            'booking.waiting_list_user', event=event, user=auto_book_user
        )

        assert Booking.objects.filter(event=event, status='OPEN').count() ==3
        assert WaitingListUser.objects.filter(event=event).count() == 4
        self._booking_delete(booking)

        # there are still 3 bookings because foo@test.com has been repopened
        assert Booking.objects.filter(event=event, status='OPEN').count() == 3

        # Auto book user removed from waiting list
        assert WaitingListUser.objects.filter(event=event).count() == 3

        # 2 emails in waiting list: cancel and autobook email
        assert len(mail.outbox) == 2

        assert mail.outbox[1].subject == f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} You have been booked into {event}"
        assert mail.outbox[1].to == ['foo@test.com']

    @override_settings(AUTO_BOOK_EMAILS=['foo@test.com'])
    def test_admin_link_in_auto_book_user_emails(self):
        """Test only show admin link in email if autobook user is superuser"""
        auto_book_user = baker.make_recipe(
            'booking.user', email='foo@test.com'
        )
        event = baker.make_recipe(
            'booking.future_PC', name='Test event',
            max_participants=3
        )

        # Full event
        baker.make_recipe('booking.booking', event=event, _quantity=2)
        booking = baker.make_recipe(
            'booking.booking', user=self.user, event=event
        )
        # auto book user is on waiting list
        baker.make_recipe(
            'booking.waiting_list_user', event=event, user=auto_book_user
        )

        assert Booking.objects.filter(event=event, status='OPEN').count() == 3
        self._booking_delete(booking)

        # there are still 3 bookings because foo@test.com has been booked
        assert Booking.objects.filter(event=event, status='OPEN').count() == 3

        # 2 emails in waiting list: cancel email for unpaid booking and autobook email
        assert len(mail.outbox) == 2
        assert mail.outbox[1].to == ['foo@test.com']
        assert 'Pay for this booking' in mail.outbox[1].body
        assert 'Cancel this booking' in mail.outbox[1].body
        assert 'Your admin page' not in mail.outbox[1].body

        # make autobook user superuser
        auto_book_user.is_superuser = True
        auto_book_user.save()
        # delete booking, rebook self.user and add autobook user to WL again
        Booking.objects.get(event=event, user=auto_book_user).delete()
        booking.status = "OPEN"
        booking.save()
        baker.make_recipe(
            'booking.waiting_list_user', event=event, user=auto_book_user
        )

        self._booking_delete(booking)
        # 4 emails in waiting list: original 2, plus second 2 for cancel and autobook
        assert len(mail.outbox) == 4
        assert mail.outbox[-1].to == ['foo@test.com']
        for text in ['Pay for this booking', 'Cancel this booking', 'Your admin page']:
            assert text in  mail.outbox[-1].body


class ToggleWaitingListTests(TestSetupMixin, TestCase):

    def test_join_waiting_list(self):
        """
        Test that joining waiting list add WaitingListUser to event
        """
        event = baker.make_recipe('booking.future_PC', max_participants=3)
        assert WaitingListUser.objects.count() == 0

        self.client.login(username=self.user.username, password='test')

        url = reverse('booking:toggle_waiting_list', args=[event.id])
        resp = self.client.get(url)

        assert resp.status_code == 200

        waiting_list = WaitingListUser.objects.filter(event=event)
        assert len(waiting_list) == 1
        assert waiting_list[0].user == self.user

    def test_leave_waiting_list(self):
        event = baker.make_recipe('booking.future_PC', max_participants=3)
        baker.make_recipe('booking.waiting_list_user', event=event, user=self.user)

        assert WaitingListUser.objects.count() == 1

        self.client.login(username=self.user.username, password='test')

        url = reverse('booking:toggle_waiting_list', args=[event.id])
        resp = self.client.get(url)

        assert resp.status_code == 200

        waiting_list = WaitingListUser.objects.filter(event=event)
        assert len(waiting_list) == 0
