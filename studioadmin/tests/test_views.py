import pytz

from datetime import datetime, timedelta
from mock import Mock, patch
from model_mommy import mommy

from django.core.urlresolvers import reverse
from django.core import mail
from django.test import TestCase, RequestFactory
from django.test.client import Client
from django.contrib.auth.models import User, Permission
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone

from activitylog.models import ActivityLog
from booking.models import Event, Booking, Block, BlockType
from booking.tests.helpers import set_up_fb, _create_session, setup_view
from studioadmin.forms import SimpleBookingRegisterFormSet
from studioadmin.views import (
    ActivityLogListView,
    ConfirmPaymentView,
    ConfirmRefundView,
    event_admin_list,
    EventAdminCreateView,
    EventAdminUpdateView,
    EventRegisterListView,
    event_waiting_list_view,
    register_view,
    timetable_admin_list,
    TimetableSessionUpdateView,
    TimetableSessionCreateView,
    upload_timetable_view,
    UserListView,
    BlockListView,
    choose_users_to_email,
    email_users_view,
    user_blocks_view,
    user_bookings_view,
    url_with_querystring
    )

from timetable.models import Session


class TestPermissionMixin(object):

    def setUp(self):
        set_up_fb()
        self.client = Client()
        self.factory = RequestFactory()
        self.user = mommy.make_recipe('booking.user')
        self.staff_user = mommy.make_recipe('booking.user')
        self.staff_user.is_staff = True
        self.staff_user.save()


class ConfirmPaymentViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(ConfirmPaymentViewTests, self).setUp()
        self.booking = mommy.make_recipe(
            'booking.booking', user=self.user,
            paid=False,
            payment_confirmed=False)

    def _get_response(self, user, booking):
        url = reverse('studioadmin:confirm-payment', args=[booking.id])
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

        view = ConfirmPaymentView.as_view()
        return view(request, pk=booking.id)

    def _post_response(self, user, booking, form_data):
        url = reverse('studioadmin:confirm-payment', args=[booking.id])
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

        view = ConfirmPaymentView.as_view()
        return view(request, pk=booking.id)

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse('studioadmin:confirm-payment', args=[self.booking.id])
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user, self.booking)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user, self.booking)
        self.assertEquals(resp.status_code, 200)

    def test_with_unpaid_booking(self):
        """
        Change an unpaid booking to paid and confirmed
        """
        self.assertFalse(self.booking.paid)
        self.assertFalse(self.booking.payment_confirmed)

        form_data = {
            'paid': 'true',
            'payment_confirmed': 'true'
        }
        resp = self._post_response(self.staff_user, self.booking, form_data)
        booking = Booking.objects.get(id=self.booking.id)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)

        self.assertEquals(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("paid and confirmed", email.body)

    def test_confirm_payment(self):
        """
        Changing payment_confirmed to True also sets booking to paid
        """
        self.assertFalse(self.booking.paid)
        self.assertFalse(self.booking.payment_confirmed)

        form_data = {
            'payment_confirmed': 'true'
        }
        resp = self._post_response(self.staff_user, self.booking, form_data)
        booking = Booking.objects.get(id=self.booking.id)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)

        self.assertEquals(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("paid and confirmed", email.body)

    def test_changing_paid_to_unpaid(self):
        """
        Changing a previously paid booking to unpaid also sets
        payment_confirmed to False
        """
        self.booking.paid = True
        self.booking.payment_confirmed = True
        self.booking.save()
        self.assertTrue(self.booking.paid)
        self.assertTrue(self.booking.payment_confirmed)

        form_data = {
            'paid': 'false',
            'payment_confirmed': 'true'
        }
        resp = self._post_response(self.staff_user, self.booking, form_data)
        booking = Booking.objects.get(id=self.booking.id)
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)

        self.assertEquals(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("not paid", email.body)

    def test_changing_payment_confirmed_only(self):
        """
        Changing a previously unpaid booking to confirmed also sets
        paid to True
        """
        self.booking.save()
        self.assertFalse(self.booking.paid)
        self.assertFalse(self.booking.payment_confirmed)

        form_data = {
            'paid': 'false',
            'payment_confirmed': 'true'
        }
        resp = self._post_response(self.staff_user, self.booking, form_data)
        booking = Booking.objects.get(id=self.booking.id)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)

    def test_payment_not_confirmed(self):
        form_data = {
            'paid': 'true',
            'payment_confirmed': 'false'
        }
        resp = self._post_response(self.staff_user, self.booking, form_data)
        booking = Booking.objects.get(id=self.booking.id)
        self.assertTrue(booking.paid)
        self.assertFalse(booking.payment_confirmed)

        self.assertEquals(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("paid - payment not confirmed yet", email.body)

    def test_no_changes(self):
        form_data = {
            'paid': 'false',
            'payment_confirmed': 'false'
        }
        resp = self._post_response(self.staff_user, self.booking, form_data)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('studioadmin:users'))


class ConfirmRefundViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(ConfirmRefundViewTests, self).setUp()
        self.booking = mommy.make_recipe(
            'booking.booking', user=self.user,
            paid=True,
            payment_confirmed=True)

    def _get_response(self, user, booking):
        url = reverse('studioadmin:confirm-refund', args=[booking.id])
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

        view = ConfirmRefundView.as_view()
        return view(request, pk=booking.id)

    def _post_response(self, user, booking, form_data):
        url = reverse('studioadmin:confirm-refund', args=[booking.id])
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

        view = ConfirmRefundView.as_view()
        return view(request, pk=booking.id)

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse('studioadmin:confirm-refund', args=[self.booking.id])
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user, self.booking)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user, self.booking)
        self.assertEquals(resp.status_code, 200)

    def test_confirm_refund_for_paid_booking(self):
        """
        test that the page can be accessed by a staff user
        """
        self.assertTrue(self.booking.paid)
        self.assertTrue(self.booking.payment_confirmed)
        resp = self._post_response(
            self.staff_user, self.booking, form_data={'confirmed': ['Confirm']}
            )
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('studioadmin:users'))
        booking = Booking.objects.get(id=self.booking.id)
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)
        self.assertEqual(len(mail.outbox), 1)

    def test_cancel_confirm_form(self):
        """
        test that page redirects without changes if cancel button used
        """
        self.assertTrue(self.booking.paid)
        self.assertTrue(self.booking.payment_confirmed)
        resp = self._post_response(
            self.staff_user, self.booking, form_data={'cancelled': ['Cancel']}
            )
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('studioadmin:users'))
        booking = Booking.objects.get(id=self.booking.id)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)
        self.assertEqual(len(mail.outbox), 0)


class EventRegisterListViewTests(TestPermissionMixin, TestCase):

    def _get_response(self, user, ev_type, url=None):
        if not url:
            url = reverse('studioadmin:event_register_list')
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        view = EventRegisterListView.as_view()
        return view(request, ev_type=ev_type)

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse('studioadmin:event_register_list')
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user, 'events')
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user, 'events')
        self.assertEquals(resp.status_code, 200)

    def test_event_context(self):
        resp = self._get_response(self.staff_user, 'events')
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context_data['type'], 'events')
        self.assertEquals(
            resp.context_data['sidenav_selection'], 'events_register'
            )
        self.assertIn("Events", resp.rendered_content)

    def test_lesson_context(self):
        url = reverse('studioadmin:class_register_list')
        resp = self._get_response(self.staff_user, 'lessons', url=url)
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.context_data['type'], 'lessons')
        self.assertEquals(
            resp.context_data['sidenav_selection'], 'lessons_register'
            )
        self.assertIn("Classes", resp.rendered_content)

    def test_event_register_list_shows_future_events_only(self):
        mommy.make_recipe('booking.future_EV', _quantity=4)
        mommy.make_recipe('booking.past_event', _quantity=4)
        resp = self._get_response(self.staff_user, 'events')
        self.assertEquals(len(resp.context_data['events']), 4)

    def test_event_register_list_shows_events_only(self):
        mommy.make_recipe('booking.future_EV', _quantity=4)
        mommy.make_recipe('booking.future_PC', _quantity=5)
        resp = self._get_response(self.staff_user, 'events')
        self.assertEquals(len(resp.context_data['events']), 4)

    def test_class_register_list_shows_classes_only(self):
        mommy.make_recipe('booking.future_EV', _quantity=4)
        mommy.make_recipe('booking.future_PC', _quantity=5)
        url = reverse('studioadmin:class_register_list')
        resp = self._get_response(self.staff_user, 'lessons', url=url)
        self.assertEquals(len(resp.context_data['events']), 5)


class EventRegisterViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(EventRegisterViewTests, self).setUp()
        self.event = mommy.make_recipe('booking.future_EV')
        self.booking1 = mommy.make_recipe('booking.booking', event=self.event)
        self.booking2 = mommy.make_recipe('booking.booking', event=self.event)

    def _get_response(
            self, user, event_slug,
            status_choice='OPEN', print=False, ev_type='event'
            ):
        if not print:
            url = reverse(
                'studioadmin:{}_register'.format(ev_type),
                args=[event_slug, status_choice]
                )
        else:
            url = reverse(
                'studioadmin:{}_register_print'.format(ev_type),
                args=[event_slug, status_choice]
                )

        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return register_view(
            request,
            event_slug,
            status_choice=status_choice,
            print_view=print)

    def _post_response(
            self, user, event_slug, form_data,
            status_choice='OPEN', print=False, ev_type='event'
            ):
        if not print:
            url = reverse(
                'studioadmin:{}_register'.format(ev_type),
                args=[event_slug, status_choice]
                )
        else:
            url = reverse(
                'studioadmin:{}_register_print'.format(ev_type),
                args=[event_slug, status_choice]
                )

        session = _create_session()
        request = self.factory.post(url, data=form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return register_view(
            request,
            event_slug,
            status_choice=status_choice,
            print_view=print)

    def formset_data(self, extra_data={}, status_choice='OPEN'):

        data = {
            'bookings-TOTAL_FORMS': 2,
            'bookings-INITIAL_FORMS': 2,
            'bookings-0-id': self.booking1.id,
            'bookings-0-user': self.booking1.user.id,
            'bookings-0-paid': self.booking1.paid,
            'bookings-0-attended': self.booking1.attended,
            'bookings-1-id': self.booking2.id,
            'bookings-1-user': self.booking2.user.id,
            'bookings-1-paid': self.booking2.paid,
            'bookings-1-attended': self.booking2.attended,
            'status_choice': status_choice
            }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse(
            'studioadmin:event_register',
            args=[self.event.slug, 'OPEN']
            )
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user, self.event.slug)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user, self.event.slug)
        self.assertEquals(resp.status_code, 200)

    def test_status_choice_filter(self):
        open_bookings = mommy.make_recipe(
            'booking.booking', event=self.event, status='OPEN', _quantity=5
            )
        cancelled_bookings = mommy.make_recipe(
            'booking.booking',
            event=self.event,
            status='CANCELLED',
            _quantity=5
            )
        resp = self._get_response(
            self.staff_user, self.event.slug, status_choice='ALL'
        )
        # 10 plus 2 created in setup
        self.assertEquals(len(resp.context_data['formset'].forms), 12)

        resp = self._get_response(
            self.staff_user, self.event.slug, status_choice='OPEN'
        )
        # 5 open plus 2 created in setup
        forms = resp.context_data['formset'].forms
        self.assertEquals(len(forms), 7)
        self.assertEquals(
            set([form.instance.status for form in forms]), {'OPEN'}
            )

        resp = self._get_response(
            self.staff_user, self.event.slug, status_choice='CANCELLED'
        )
        forms = resp.context_data['formset'].forms
        self.assertEquals(len(forms), 5)
        self.assertEquals(
            set([form.instance.status for form in forms]), {'CANCELLED'}
            )

    def test_can_update_booking(self):
        self.assertFalse(self.booking1.paid)
        self.assertFalse(self.booking2.attended)

        formset_data = self.formset_data({
            'bookings-0-paid': True,
            'bookings-1-attended': True,
            'formset_submitted': 'Save changes'
        })

        self._post_response(
            self.staff_user, self.event.slug,
            formset_data, status_choice='OPEN'
        )

        booking1 = Booking.objects.get(id=self.booking1.id)
        self.assertTrue(booking1.paid)
        booking2 = Booking.objects.get(id=self.booking2.id)
        self.assertTrue(booking2.attended)

    def test_can_select_block_for_existing_booking(self):
        self.assertFalse(self.booking1.block)
        block_type = mommy.make(
            BlockType, event_type=self.event.event_type
        )
        block = mommy.make_recipe(
            'booking.block', block_type=block_type, user=self.user, paid=True
        )
        self.assertTrue(block.active_block())

        formset_data = self.formset_data({
            'bookings-0-block': block.id,
            'formset_submitted': 'Save changes'
        })
        self._post_response(
            self.staff_user, self.event.slug,
            formset_data, status_choice='OPEN'
        )
        booking = Booking.objects.get(id=self.booking1.id)
        self.assertEqual(booking.block, block)

    def test_can_add_new_booking(self):

        user = mommy.make_recipe('booking.user')
        formset_data = self.formset_data({
            'bookings-TOTAL_FORMS': 3,
            'bookings-2-user': user.id,
            'bookings-2-paid': True,
            'bookings-2-attended': True,
            'bookings-2-status': 'OPEN'
        })
        self.assertEqual(Booking.objects.all().count(), 2)
        self._post_response(
            self.staff_user, self.event.slug,
            formset_data, status_choice='OPEN'
        )
        self.assertEqual(Booking.objects.all().count(), 3)
        booking = Booking.objects.last()
        self.assertTrue(booking.paid)
        self.assertTrue(booking.attended)

    def test_printable_version_does_not_show_status_filter(self):
        resp = self._get_response(
            self.staff_user, self.event.slug, print=False,
            status_choice='OPEN'
        )
        resp.render()
        self.assertIn(
            '<select id="id_status_choice" name="status_choice">',
            str(resp.content),
        )
        resp = self._get_response(
            self.staff_user, self.event.slug, print=True,
            status_choice='OPEN'
        )
        resp.render()
        self.assertNotIn(
            '<select id="id_status_choice" name="status_choice">',
            str(resp.content),
        )
        self.assertIn(
            'id="print-button"',
            str(resp.content),
        )

    def test_selecting_printable_version_redirects_to_print_view(self):
        resp = self._post_response(
            self.staff_user, self.event.slug,
            form_data=self.formset_data({'print': 'printable version'}),
            print=False,
            status_choice='OPEN'
        )

        self.assertEquals(resp.status_code, 302)
        self.assertEquals(
            resp.url,
            reverse(
                'studioadmin:event_register_print',
            args=[self.event.slug, 'OPEN']
            )
        )

    def test_submitting_form_for_classes_redirects_to_class_register(self):
        event = mommy.make_recipe('booking.future_PC')
        bookings = mommy.make_recipe(
            'booking.booking', event=event, status='OPEN', _quantity=2
        )

        form_data = self.formset_data({
            'bookings-0-id': bookings[0].id,
            'bookings-0-user': bookings[0].user.id,
            'bookings-0-paid': bookings[0].paid,
            'bookings-0-attended': bookings[0].attended,
            'bookings-1-id': bookings[1].id,
            'bookings-1-user': bookings[1].user.id,
            'bookings-1-paid': bookings[1].paid,
            'bookings-1-attended': bookings[1].attended,
        })

        resp = self._post_response(
            self.staff_user, event.slug,
            form_data=form_data,
            print=False,
            ev_type='class',
            status_choice='OPEN'
        )
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(
            resp.url,
            reverse(
                'studioadmin:class_register',
            args=[event.slug, 'OPEN']
            )
        )

    def test_submitting_form_for_events_redirects_to_event_register(self):
        resp = self._post_response(
            self.staff_user, self.event.slug,
            form_data=self.formset_data(),
            print=False,
            ev_type='event',
            status_choice='OPEN'
        )
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(
            resp.url,
            reverse(
                'studioadmin:event_register',
            args=[self.event.slug, 'OPEN']
            )
        )

    def test_number_of_extra_lines_displayed(self):
        """
        Test form shows extra lines correctly
        """
        # if there is a max_participants, and filter is 'OPEN',
        # show extra lines to this number
        mommy.make('booking.booking', event=self.event, status='CANCELLED')
        self.event.max_participants = 10
        self.event.save()
        self.assertEqual(self.event.spaces_left(), 8)
        resp = self._get_response(
            self.staff_user, self.event.slug,
            status_choice='OPEN'
        )
        self.assertEqual(resp.context_data['extra_lines'], 8)

        # if there is a max_participants, and filter is not 'OPEN',
        # show extra lines to this number, plus the number of cancelled
        # bookings (extra lines is always equal to number of spaces left).
        self.assertEqual(self.event.spaces_left(), 8)
        self.assertEqual(
            Booking.objects.filter(
                event=self.event, status='CANCELLED'
            ).count(), 1
        )
        resp = self._get_response(
            self.staff_user, self.event.slug,
            status_choice='ALL'
        )
        self.assertEqual(resp.context_data['extra_lines'], 8)

        # if no max_participants, and open bookings < 15, show extra lines for
        # up to 15 open bookings
        self.event.max_participants = None
        self.event.save()
        resp = self._get_response(
            self.staff_user, self.event.slug,
            status_choice='OPEN'
        )
        open_bookings = [
            booking for booking in self.event.bookings.all()
            if booking.status == 'OPEN'
        ]
        self.assertEqual(len(open_bookings), 2)
        cancelled_bookings = [
            booking for booking in self.event.bookings.all()
            if booking.status == 'CANCELLED'
        ]
        self.assertEqual(len(cancelled_bookings), 1)
        self.assertEqual(resp.context_data['extra_lines'], 13)

        # if 15 or more bookings, just show 2 extra lines
        mommy.make_recipe('booking.booking', event=self.event, _quantity=12)
        resp = self._get_response(
            self.staff_user, self.event.slug,
            status_choice='OPEN'
        )
        self.assertEqual(resp.context_data['extra_lines'], 2)


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

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user, ev_type='events')
        self.assertEquals(resp.status_code, 200)

    def test_events_url_shows_only_events(self):
        classes = mommy.make_recipe('booking.future_PC')
        resp = self._get_response(self.staff_user, ev_type='events')
        self.assertIn('Scheduled Events', str(resp.content))


    def test_classes_url_shows_only_classes(self):
        classes = mommy.make_recipe('booking.future_PC')
        url = reverse('studioadmin:lessons')
        resp = self._get_response(self.staff_user, ev_type='classes', url=url)
        self.assertIn('Scheduled Classes', str(resp.content))

    def test_past_filter(self):
        resp = self._post_response(
            self.staff_user, 'events', {'past': 'Show past'}
        )
        self.assertIn('Past Events', str(resp.content))
        self.assertNotIn('Scheduled Events', str(resp.content))

    def test_upcoming_filter(self):
        resp = self._post_response(
            self.staff_user, 'events', {'upcoming': 'Show upcoming'}
        )
        self.assertIn('Scheduled Events', str(resp.content))
        self.assertNotIn('Past Events', str(resp.content))

    def test_delete_checkbox_disabled_for_events_with_bookings(self):
        event = mommy.make_recipe('booking.future_EV')
        mommy.make_recipe('booking.booking', event=event)
        self.assertEquals(event.bookings.all().count(), 1)
        self.assertEquals(self.event.bookings.all().count(), 0)

        formset_data = self.formset_data({
            'form-TOTAL_FORMS': 2,
            'form-INITIAL_FORMS': 2,
            'form-1-id': str(event.id),
            'form-1-max-participants': '10',
            'form-1-booking_open': 'on',
            'form-1-payment_open': 'on',
            }
        )
        resp = self._get_response(self.staff_user, 'events')
        self.assertIn(
            'class="delete-checkbox studioadmin-list" '
            'id="DELETE_0" name="form-0-DELETE"',
            str(resp.content)
        )
        self.assertIn(
            'disabled="disabled" id="DELETE_1" name="form-1-DELETE"',
            str(resp.content)
        )

    def test_can_delete(self):
        self.assertEquals(Event.objects.all().count(), 1)
        formset_data = self.formset_data({
            'form-0-DELETE': 'on'
            })
        resp = self._post_response(self.staff_user, 'events', formset_data)
        self.assertEquals(Event.objects.all().count(), 0)

    def test_can_update_existing_event(self):
        self.assertTrue(self.event.booking_open)
        formset_data = self.formset_data({
            'form-0-booking_open': 'false'
            })
        resp = self._post_response(self.staff_user, 'events', formset_data)
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
        self.event = mommy.make_recipe('booking.future_EV')

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
            'location': event.location
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
            'location': 'Watermelon Studio'
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


class TimetableAdminListViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(TimetableAdminListViewTests, self).setUp()
        self.session = mommy.make_recipe('booking.mon_session', cost=10)

    def _get_response(self, user):
        url = reverse('studioadmin:timetable')
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return timetable_admin_list(request)

    def _post_response(self, user, form_data):
        url = reverse('studioadmin:timetable')
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return timetable_admin_list(request)

    def formset_data(self, extra_data={}):

        data = {
            'form-TOTAL_FORMS': 1,
            'form-INITIAL_FORMS': 1,
            'form-0-id': self.session.id,
            'form-0-booking_open': self.session.booking_open,
            'form-0-payment_open': self.session.payment_open,
            'form-0-advance_payment_required': self.session.advance_payment_required
            }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse('studioadmin:timetable')
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user)
        self.assertEquals(resp.status_code, 200)

    def test_can_delete_sessions(self):
        mommy.make_recipe('booking.tue_session', _quantity=2)
        mommy.make_recipe('booking.wed_session', _quantity=2)
        self.assertEqual(Session.objects.count(), 5)

        data = {
            'form-TOTAL_FORMS': 5,
            'form-INITIAL_FORMS': 5,
            }

        for i, session in enumerate(Session.objects.all()):
            data['form-{}-id'.format(i)] = session.id
            data['form-{}-cost'.format(i)] = session.cost
            data['form-{}-max_participants'.format(i)] = session.max_participants
            data['form-{}-booking_open'.format(i)] = session.booking_open
            data['form-{}-payment_open'.format(i)] = session.payment_open

        data['form-0-DELETE'] = 'on'

        self._post_response(self.staff_user, data)
        self.assertEqual(Session.objects.count(), 4)

    def test_can_update_existing_session(self):
        self.assertEqual(self.session.advance_payment_required, True)

        self._post_response(
            self.staff_user, self.formset_data(
                extra_data={'form-0-advance_payment_required': False}
            )
        )
        self.session.refresh_from_db()
        self.assertEqual(self.session.advance_payment_required, False)

    def test_submitting_valid_form_redirects_back_to_timetable(self):
        resp = self._post_response(
            self.staff_user, self.formset_data()
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:timetable'))


class TimetableSessionUpdateViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(TimetableSessionUpdateViewTests, self).setUp()
        self.session = mommy.make_recipe('booking.mon_session')

    def _get_response(self, user, ttsession):
        url = reverse('studioadmin:edit_session', args=[ttsession.id])
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        view = TimetableSessionUpdateView.as_view()
        return view(request, pk=ttsession.id)

    def _post_response(self, user, ttsession, form_data):
        url = reverse('studioadmin:edit_session', args=[ttsession.id])
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

        view = TimetableSessionUpdateView.as_view()
        return view(request, pk=ttsession.id)

    def form_data(self, ttsession, extra_data={}):
        data = {
            'id': ttsession.id,
            'name': ttsession.name,
            'event_type': ttsession.event_type.id,
            'day': ttsession.day,
            'time': ttsession.time.strftime('%H:%M'),
            'contact_email': ttsession.contact_email,
            'contact_person': ttsession.contact_person,
            'cancellation_period': ttsession.cancellation_period,
            'location': ttsession.location
        }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse('studioadmin:edit_session', args=[self.session.id])
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user, self.session)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user, self.session)
        self.assertEquals(resp.status_code, 200)

    def test_submitting_valid_session_form_redirects_back_to_timetable(self):
        resp = self._post_response(
            self.staff_user, self.session, self.form_data(self.session)
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:timetable'))

    def test_context_data(self):
        resp = self._get_response(self.staff_user, self.session)
        self.assertEqual(resp.context_data['sidenav_selection'], 'timetable')
        self.assertEqual(resp.context_data['session_day'], 'Monday')

    def test_can_edit_session_data(self):
        self.assertEqual(self.session.day, '01MON')
        resp = self._post_response(
            self.staff_user, self.session,
            self.form_data(self.session, extra_data={'day': '03WED'})
        )
        session = Session.objects.get(id=self.session.id)
        self.assertEqual(session.day, '03WED')

    def test_submitting_with_no_changes_does_not_change_session(self):
        self._post_response(
            self.staff_user, self.session, self.form_data(self.session)
        )
        ttsession = Session.objects.get(id=self.session.id)

        self.assertEqual(self.session.id, ttsession.id)
        self.assertEqual(self.session.name, ttsession.name)
        self.assertEqual(self.session.event_type, ttsession.event_type)
        self.assertEqual(self.session.day, ttsession.day)
        self.assertEqual(
            self.session.time.strftime('%H:%M'),
            ttsession.time.strftime('%H:%M')
        )
        self.assertEqual(self.session.contact_email, ttsession.contact_email)
        self.assertEqual(self.session.contact_person, ttsession.contact_person)
        self.assertEqual(
            self.session.cancellation_period,
            ttsession.cancellation_period
        )
        self.assertEqual(self.session.location, ttsession.location)


class TimetableSessionCreateViewTests(TestPermissionMixin, TestCase):

    def _get_response(self, user):
        url = reverse('studioadmin:add_session')
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

        view = TimetableSessionCreateView.as_view()
        return view(request)

    def _post_response(self, user, form_data):
        url = reverse('studioadmin:add_session')
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

        view = TimetableSessionCreateView.as_view()
        return view(request)

    def form_data(self, extra_data={}):
        ev_type = mommy.make_recipe('booking.event_type_PC')
        data = {
            'name': 'test_event',
            'event_type': ev_type.id,
            'day': '01MON',
            'time': '18:00',
            'contact_email': 'test@test.com',
            'contact_person': 'test',
            'cancellation_period': 24,
            'location': 'Watermelon Studio'
        }
        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse('studioadmin:add_session')
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user)
        self.assertEquals(resp.status_code, 200)

    def test_submitting_valid_session_form_redirects_back_to_timetable(self):
        resp = self._post_response(self.staff_user, self.form_data())
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('studioadmin:timetable'))

    def test_context_data(self):
        resp = self._get_response(self.staff_user)
        self.assertEqual(resp.context_data['sidenav_selection'], 'add_session')

    def test_can_add_event(self):
        self.assertEqual(Session.objects.count(), 0)
        resp = self._post_response(self.staff_user, self.form_data())
        self.assertEqual(Session.objects.count(), 1)
        ttsession = Session.objects.first()
        self.assertEqual(ttsession.name, 'test_event')


class UploadTimetableTests(TestPermissionMixin, TestCase):

    def _get_response(self, user):
        url = reverse('studioadmin:upload_timetable')
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return upload_timetable_view(request)

    def _post_response(self, user, form_data):
        url = reverse('studioadmin:upload_timetable')
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return upload_timetable_view(request)

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse('studioadmin:upload_timetable')
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user)
        self.assertEquals(resp.status_code, 200)

    @patch('studioadmin.forms.timezone')
    def test_events_are_created(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 6, 1, 0, 0, tzinfo=timezone.utc
        )
        mommy.make_recipe('booking.mon_session', _quantity=5)
        self.assertEqual(Event.objects.count(), 0)
        form_data = {
            'start_date': 'Mon 08 Jun 2015',
            'end_date': 'Sun 14 Jun 2015'
        }
        self._post_response(self.staff_user, form_data)
        self.assertEqual(Event.objects.count(), 5)
        event_names = [event.name for event in Event.objects.all()]
        session_names =  [session.name for session in Session.objects.all()]
        self.assertEqual(sorted(event_names), sorted(session_names))

    @patch('studioadmin.forms.timezone')
    def test_does_not_create_duplicate_sessions(self, mock_tz):
        mock_tz.now.return_value = datetime(
            2015, 6, 1, 0, 0, tzinfo=timezone.utc
        )
        mommy.make_recipe('booking.mon_session', _quantity=5)
        self.assertEqual(Event.objects.count(), 0)
        form_data = {
            'start_date': 'Mon 08 Jun 2015',
            'end_date': 'Sun 14 Jun 2015'
        }
        self._post_response(self.staff_user, form_data)
        self.assertEqual(Event.objects.count(), 5)

        mommy.make_recipe('booking.tue_session', _quantity=2)
        self.assertEqual(Session.objects.count(), 7)
        self._post_response(self.staff_user, form_data)
        self.assertEqual(Event.objects.count(), 7)


class UserListViewTests(TestPermissionMixin, TestCase):

    def _get_response(self, user, form_data={}):
        url = reverse('studioadmin:users')
        session = _create_session()
        request = self.factory.get(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        view = UserListView.as_view()
        return view(request)

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse('studioadmin:users')
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user)
        self.assertEquals(resp.status_code, 200)

    def test_all_users_are_displayed(self):
        mommy.make_recipe('booking.user', _quantity=6)
        # 8 users total, incl self.user and self.staff_user
        self.assertEqual(User.objects.count(), 8)
        resp = self._get_response(self.staff_user)
        self.assertEqual(
            list(resp.context_data['users']), list(User.objects.all())
        )

    def test_display_regular_students(self):
        not_reg_student = mommy.make_recipe('booking.user')
        reg_student = mommy.make_recipe('booking.user')
        perm = Permission.objects.get(codename='is_regular_student')
        reg_student.user_permissions.add(perm)
        reg_student.save()

        resp = self._get_response(self.staff_user)
        resp.render()
        self.assertIn(
            'id="regular_student_button" value="{}">Yes'.format(reg_student.id),
            str(resp.content)
        )
        self.assertIn(
            'id="regular_student_button" value="{}">No'.format(not_reg_student.id),
            str(resp.content)
        )

    def test_change_regular_student(self):
        not_reg_student = mommy.make_recipe('booking.user')
        reg_student = mommy.make_recipe('booking.user')
        perm = Permission.objects.get(codename='is_regular_student')
        reg_student.user_permissions.add(perm)
        reg_student.save()

        self.assertTrue(reg_student.has_perm('booking.is_regular_student'))
        self._get_response(
            self.staff_user, {'change_user': [reg_student.id]}
        )
        changed_student = User.objects.get(id=reg_student.id)
        self.assertFalse(changed_student.has_perm('booking.is_regular_student'))

        self.assertFalse(not_reg_student.has_perm('booking.is_regular_student'))
        self._get_response(
            self.staff_user, {'change_user': [not_reg_student.id]}
        )
        changed_student = User.objects.get(id=not_reg_student.id)
        self.assertTrue(changed_student.has_perm('booking.is_regular_student'))


class BlockListViewTests(TestPermissionMixin, TestCase):

    def _get_response(self, user, form_data={}):
        url = reverse('studioadmin:blocks')
        session = _create_session()
        request = self.factory.get(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        view = BlockListView.as_view()
        return view(request)

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse('studioadmin:blocks')
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user)
        self.assertEquals(resp.status_code, 200)

    def test_current_blocks_returned_on_get(self):
        active_blocks = mommy.make_recipe(
            'booking.block', _quantity=3, paid=True
        )
        unpaid_blocks = mommy.make_recipe(
            'booking.block', paid=False, _quantity=3
        )
        current_blocks = active_blocks + unpaid_blocks
        full_block = mommy.make_recipe(
            'booking.block', paid=False, block_type__size=1
        )
        mommy.make_recipe('booking.booking', block=full_block)

        resp = self._get_response(self.staff_user)
        self.assertEqual(
            list(resp.context_data['blocks']),
            list(Block.objects.filter(
                id__in=[block.id for block in current_blocks]
            ))
        )

    def test_block_status_filter(self):
        active_blocks = mommy.make_recipe(
            'booking.block', _quantity=3, paid=True
        )
        unpaid_blocks = mommy.make_recipe(
            'booking.block', _quantity=3, paid=False
        )
        current_blocks = active_blocks + unpaid_blocks
        expired_blocks = mommy.make_recipe(
            'booking.block', paid=True,
            start_date=datetime(2000, 1, 1, tzinfo=timezone.utc),
            block_type__duration=1,
            _quantity=3
        )
        unpaid_expired_blocks = mommy.make_recipe(
            'booking.block', paid=False,
            start_date=datetime(2000, 1, 1, tzinfo=timezone.utc),
            block_type__duration=1,
            _quantity=3
        )
        full_blocks = mommy.make_recipe(
            'booking.block', paid=True,
            block_type__size=1,
            _quantity=3
        )
        for block in full_blocks:
            mommy.make_recipe('booking.booking', block=block)

        # all blocks
        resp = self._get_response(
            self.staff_user, form_data={'block_status': 'all'}
        )
        self.assertEqual(
            list(resp.context_data['blocks']),
            list(Block.objects.all())
        )
        # active blocks are paid and not expired
        resp = self._get_response(
            self.staff_user, form_data={'block_status': 'active'}
        )
        self.assertEqual(
            list(resp.context_data['blocks']),
            list(Block.objects.filter(id__in=[block.id for block in active_blocks]))
        )

        # unpaid blocks are unpaid but not expired; should not show any
        # from unpaid_expired_blocks
        resp = self._get_response(
            self.staff_user, form_data={'block_status': 'unpaid'}
        )
        self.assertEqual(
            list(resp.context_data['blocks']),
            list(Block.objects.filter(id__in=[block.id for block in unpaid_blocks]))
        )

        #current blocks are paid or unpaid, not expired, not full
        resp = self._get_response(
            self.staff_user, form_data={'block_status': 'current'}
        )
        self.assertEqual(
            list(resp.context_data['blocks']),
            list(Block.objects.filter(id__in=[block.id for block in current_blocks]))
        )

        # expired blocks are past expiry date or full
        resp = self._get_response(
            self.staff_user, form_data={'block_status': 'expired'}
        )
        expired = expired_blocks + unpaid_expired_blocks + full_blocks
        self.assertEqual(
            list(resp.context_data['blocks']),
            list(Block.objects.filter(id__in=[block.id for block in expired]))
        )

class ChooseUsersToEmailTests(TestPermissionMixin, TestCase):

    def _get_response(self, user):
        url = reverse('studioadmin:choose_email_users')
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return choose_users_to_email(request)

    def _post_response(self, user, form_data):
        url = reverse('studioadmin:choose_email_users')
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return choose_users_to_email(request)

    def formset_data(self, extra_data={}):

        data = {
            'form-TOTAL_FORMS': 1,
            'form-INITIAL_FORMS': 1,
            'form-0-id': str(self.user.id),
            }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse('studioadmin:choose_email_users')
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user)
        self.assertEquals(resp.status_code, 200)

    def test_filter_users_by_event_booked(self):
        mommy.make_recipe('booking.user', _quantity=2)
        event = mommy.make_recipe('booking.future_EV')
        mommy.make_recipe('booking.booking', user=self.user, event=event)
        form_data = self.formset_data(
            {'filter': 'Show Students', 'filter-events': [event.id]}
        )
        resp = self._post_response(self.staff_user, form_data)

        self.assertEqual(User.objects.count(), 4)

        usersformset = resp.context_data['usersformset']
        self.assertEqual(len(usersformset.forms), 1)

        user = usersformset.forms[0]
        self.assertEqual(user.instance, self.user)

    def test_filter_users_by_class_booked(self):
        mommy.make_recipe('booking.user', _quantity=2)
        pole_class = mommy.make_recipe('booking.future_PC')
        mommy.make_recipe('booking.booking', user=self.user, event=pole_class)
        form_data = self.formset_data(
            {'filter': 'Show Students', 'filter-lessons': [pole_class.id]}
        )
        resp = self._post_response(self.staff_user, form_data)

        self.assertEqual(User.objects.count(), 4)

        usersformset = resp.context_data['usersformset']
        self.assertEqual(len(usersformset.forms), 1)

        user = usersformset.forms[0]
        self.assertEqual(user.instance, self.user)

    def test_filter_with_no_events_selected(self):
        mommy.make_recipe('booking.user', _quantity=2)
        pole_class = mommy.make_recipe('booking.future_PC')
        mommy.make_recipe('booking.booking', user=self.user, event=pole_class)
        form_data = self.formset_data(
            {
                'filter': 'Show Students',
                'filter-lessons': [''],
                'filter-events': ['']}
        )
        resp = self._post_response(self.staff_user, form_data)

        self.assertEqual(User.objects.count(), 4)

        usersformset = resp.context_data['usersformset']
        self.assertEqual(len(usersformset.forms), 4)

        users = [form.instance for form in usersformset.forms]
        self.assertEqual(set(users), set(User.objects.all()))

    def test_filter_users_by_multiple_events_and_classes(self):
        new_user1 = mommy.make_recipe('booking.user')
        new_user2 = mommy.make_recipe('booking.user')
        event = mommy.make_recipe('booking.future_EV')
        pole_class = mommy.make_recipe('booking.future_PC')
        mommy.make_recipe('booking.booking', user=self.user, event=pole_class)
        mommy.make_recipe('booking.booking', user=new_user1, event=event)
        form_data = self.formset_data(
            {
                'filter': 'Show Students',
                'filter-lessons': [pole_class.id],
                'filter-events': [event.id]}
        )
        resp = self._post_response(self.staff_user, form_data)

        self.assertEqual(User.objects.count(), 4)

        usersformset = resp.context_data['usersformset']
        self.assertEqual(len(usersformset.forms), 2)

        users = [form.instance for form in usersformset.forms]
        self.assertEqual(set(users), set([self.user, new_user1]))

    def test_users_for_cancelled_bookings_not_shown(self):
        new_user = mommy.make_recipe('booking.user')
        event = mommy.make_recipe('booking.future_EV')
        mommy.make_recipe(
            'booking.booking', user=self.user, event=event, status='CANCELLED'
        )
        mommy.make_recipe('booking.booking', user=new_user, event=event)
        form_data = self.formset_data(
            {
                'filter': 'Show Students',
                'filter-events': [event.id]}
        )
        resp = self._post_response(self.staff_user, form_data)

        usersformset = resp.context_data['usersformset']
        self.assertEqual(len(usersformset.forms), 1)

        user = usersformset.forms[0].instance
        self.assertEqual(user, new_user)

    def test_filter_users_with_multiple_bookings(self):
        new_user = mommy.make_recipe('booking.user')
        events = mommy.make_recipe('booking.future_EV', _quantity=3)
        for event in events:
            mommy.make_recipe('booking.booking', user=new_user, event=event)
        form_data = self.formset_data(
            {
                'filter': 'Show Students',
                'filter-events': [event.id for event in events]}
        )
        resp = self._post_response(self.staff_user, form_data)

        self.assertEqual(User.objects.count(), 3)
        self.assertEqual(Booking.objects.filter(user=new_user).count(), 3)
        usersformset = resp.context_data['usersformset']
        # user has 3 bookings, for each of the selected events, but is only
        # displayed once
        self.assertEqual(len(usersformset.forms), 1)

        user = usersformset.forms[0].instance
        self.assertEqual(user, new_user)


class EmailUsersTests(TestPermissionMixin, TestCase):

    def _get_response(
        self, user, users_to_email, event_ids=[], lesson_ids=[]
    ):
        url = url_with_querystring(
            reverse('studioadmin:email_users_view'),
            events=event_ids, lessons=lesson_ids
        )
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.session['users_to_email'] = users_to_email
        request.session['events'] = event_ids
        request.session['lessons'] = lesson_ids
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return email_users_view(request)

    def _post_response(
        self, user, users_to_email, form_data, event_ids=[], lesson_ids=[]
    ):
        url = url_with_querystring(
            reverse('studioadmin:email_users_view'),
            events=event_ids, lessons=lesson_ids
        )
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.session['users_to_email'] = users_to_email
        request.session['events'] = event_ids
        request.session['lessons'] = lesson_ids
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return email_users_view(request)

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse('studioadmin:email_users_view')
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user, [self.user.id])
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user, [self.user.id])
        self.assertEquals(resp.status_code, 200)

    def test_users_and_events_in_context(self):
        event = mommy.make_recipe('booking.future_EV', name='Test Event')
        lesson = mommy.make_recipe('booking.future_PC', name='Test Class')
        resp = self._get_response(
            self.staff_user, [self.user.id],
            event_ids=[event.id], lesson_ids=[lesson.id]
        )
        self.assertEqual([ev for ev in resp.context_data['events']], [event])
        self.assertEqual(
            [lsn for lsn in resp.context_data['lessons']], [lesson]
        )
        self.assertEqual(
            [user for user in resp.context_data['users_to_email']], [self.user]
        )

    def test_subject_is_autopoulated(self):
        event = mommy.make_recipe('booking.future_EV')
        lesson = mommy.make_recipe('booking.future_PC')
        resp = self._get_response(
            self.staff_user, [self.user.id],
            event_ids=[event.id], lesson_ids=[lesson.id]
        )
        form = resp.context_data['form']
        self.assertEqual(
            form.initial['subject'], "; ".join([str(event), str(lesson)])
        )

    def test_emails_sent(self):
        event = mommy.make_recipe('booking.future_EV')
        resp = self._post_response(
            self.staff_user, [self.user.id],
            event_ids=[event.id], lesson_ids=[],
            form_data={
                'subject': 'Test email',
                'message': 'Test message',
                'from_address': 'test@test.com'}
        )
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.body, 'Test message')
        self.assertEqual(email.subject, '[watermelon studio bookings] Test email')

    def test_cc_email_sent(self):
        resp = self._post_response(
            self.staff_user, [self.user.id],
            event_ids=[], lesson_ids=[],
            form_data={
                'subject': 'Test email',
                'message': 'Test message',
                'from_address': 'test@test.com',
                'cc': True}
        )
        self.assertEqual(len(mail.outbox), 2)
        email_to = [mail.to[0] for mail in mail.outbox]
        self.assertEqual(
            sorted(email_to), ['test@test.com', self.user.email]
        )


class UserBookingsViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(UserBookingsViewTests, self).setUp()
        self.future_user_bookings = mommy.make_recipe(
            'booking.booking', user=self.user, paid=True,
            payment_confirmed=True, event__date=timezone.now()+timedelta(3),
            status='OPEN',
            _quantity=2
        )
        self.past_user_bookings = mommy.make_recipe(
            'booking.booking', user=self.user, paid=True,
            payment_confirmed=True, event__date=timezone.now()-timedelta(3),
            status='OPEN',
            _quantity=2
        )
        self.future_cancelled_bookings = mommy.make_recipe(
            'booking.booking', user=self.user, paid=True,
            payment_confirmed=True, event__date=timezone.now()+timedelta(3),
            status='CANCELLED',
            _quantity=2
        )
        self.past_cancelled_bookings = mommy.make_recipe(
            'booking.booking', user=self.user, paid=True,
            payment_confirmed=True, event__date=timezone.now()-timedelta(3),
            status='CANCELLED',
            _quantity=2
        )
        mommy.make_recipe(
            'booking.booking', paid=True,
            payment_confirmed=True, event__date=timezone.now()+timedelta(3),
            _quantity=2
        )

    def formset_data(self, extra_data={}):
        data = {
            'bookings-TOTAL_FORMS': 2,
            'bookings-INITIAL_FORMS': 2,
            'bookings-0-id': self.future_user_bookings[0].id,
            'bookings-0-event': self.future_user_bookings[0].event.id,
            'bookings-0-status': self.future_user_bookings[0].status,
            'bookings-0-paid': self.future_user_bookings[0].paid,
            'bookings-1-id': self.future_user_bookings[1].id,
            'bookings-1-event': self.future_user_bookings[1].event.id,
            'bookings-1-status': self.future_user_bookings[1].status,
            'bookings-1-paid': self.future_user_bookings[1].paid,
            }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def _get_response(self, user, user_id, booking_status='future'):
        url = reverse(
            'studioadmin:user_bookings_list',
            kwargs={'user_id': user_id, 'booking_status': booking_status}
        )
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return user_bookings_view(
            request, user_id, booking_status=booking_status
        )

    def _post_response(
        self, user, user_id, form_data, booking_status='future'
        ):
        url = reverse(
            'studioadmin:user_bookings_list',
            kwargs={'user_id': user_id, 'booking_status': booking_status}
        )
        form_data['booking_status'] = [booking_status]
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return user_bookings_view(
            request, user_id, booking_status=booking_status
        )

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse(
            'studioadmin:user_bookings_list',
            kwargs={'user_id': self.user.id, 'booking_status': 'future'}
        )
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user, self.user.id)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user, self.user.id)
        self.assertEquals(resp.status_code, 200)

    def test_view_users_bookings(self):
        """
        Test only user's bookings for future events shown by default
        """
        self.assertEqual(Booking.objects.count(), 10)
        resp = self._get_response(self.staff_user, self.user.id)
        # get all but last form (last form is the empty extra one)
        booking_forms = resp.context_data['userbookingformset'].forms[:-1]
        # show future bookings, both open and cancelled
        self.assertEqual(
            len(booking_forms),
            len(self.future_user_bookings) + len(self.future_cancelled_bookings)
        )

        self.assertEqual(
            [booking.instance for booking in booking_forms],
            self.future_user_bookings + self.future_cancelled_bookings
        )

    def test_filter_bookings_by_booking_status(self):

        # future bookings
        resp = self._get_response(self.staff_user, self.user.id, 'future')
        # get all but last form (last form is the empty extra one)
        booking_forms = resp.context_data['userbookingformset'].forms[:-1]
        self.assertEqual(len(booking_forms), 4)
        self.assertEqual(
            [booking.instance for booking in booking_forms],
            self.future_user_bookings + self.future_cancelled_bookings
        )

        # past bookings
        resp = self._get_response(self.staff_user, self.user.id, 'past')
        # get all but last form (last form is the empty extra one)
        booking_forms = resp.context_data['userbookingformset'].forms[:-1]
        self.assertEqual(len(booking_forms), 4)
        self.assertEqual(
            [booking.instance for booking in booking_forms],
            self.past_user_bookings + self.past_cancelled_bookings
        )

    def test_can_update_booking(self):
        self.assertTrue(self.future_user_bookings[0].paid)
        form_data = self.formset_data({'bookings-0-paid': False,
        'formset_submitted': 'Submit'})

        self._post_response(self.staff_user, self.user.id, form_data=form_data)
        booking = Booking.objects.get(id=self.future_user_bookings[0].id)
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)

    def test_can_add_booking(self):
        self.assertEqual(Booking.objects.count(), 10)
        event = mommy.make_recipe('booking.future_EV')
        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-2-event': event.id,
                'bookings-2-status': 'OPEN'
            }
        )
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )
        self.assertEqual(Booking.objects.count(), 11)

        bookings = Booking.objects.filter(event=event)
        self.assertEqual(len(bookings), 1)

        booking = bookings[0]
        self.assertEqual(booking.user, self.user)

    def test_changing_booking_status_updates_payment_status_also(self):
        self.assertEqual(self.future_user_bookings[0].status, 'OPEN')
        self.assertTrue(self.future_user_bookings[0].paid)
        self.assertTrue(self.future_user_bookings[0].payment_confirmed)
        form_data = self.formset_data(
            {
                'bookings-0-status': 'CANCELLED'
            }
        )
        self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )

        booking = Booking.objects.get(id=self.future_user_bookings[0].id)
        self.assertEqual(booking.status, 'CANCELLED')
        self.assertFalse(booking.paid)
        self.assertFalse(booking.payment_confirmed)

    def test_can_assign_booking_to_available_block(self):
        booking = mommy.make_recipe(
            'booking.booking',
            event__date=timezone.now()+timedelta(2),
            user=self.user,
            paid=False,
            payment_confirmed=False
        )
        block = mommy.make_recipe(
            'booking.block', block_type__event_type=booking.event.event_type,
            user=self.user
        )
        self.assertFalse(booking.block)
        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-INITIAL_FORMS': 3,
                'bookings-2-id': booking.id,
                'bookings-2-event': booking.event.id,
                'bookings-2-status': booking.status,
                'bookings-2-block': block.id
            }
        )
        self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )

        booking = Booking.objects.get(id=booking.id)
        self.assertEqual(booking.block, block)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)

    def test_create_new_block_booking(self):
        event1 = mommy.make_recipe('booking.future_EV')
        block1 = mommy.make_recipe(
            'booking.block', block_type__event_type=event1.event_type,
            user=self.user
        )

        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-2-event': event1.id,
                'bookings-2-status': 'OPEN',
                'bookings-2-block': block1.id
            }
        )
        self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )
        booking = Booking.objects.get(event=event1)
        self.assertEqual(booking.block, block1)


    def test_cannot_create_new_block_booking_with_wrong_blocktype(self):
        event1 = mommy.make_recipe('booking.future_EV')
        event2 = mommy.make_recipe('booking.future_EV')

        block1 = mommy.make_recipe(
            'booking.block', block_type__event_type=event1.event_type,
            user=self.user
        )
        block2 = mommy.make_recipe(
            'booking.block', block_type__event_type=event2.event_type,
            user=self.user
        )
        self.assertEqual(Booking.objects.count(), 10)
        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-2-event': event1.id,
                'bookings-2-status': 'OPEN',
                'bookings-2-block': block2.id
            }
        )
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )
        errors = resp.context_data['userbookingformset'].errors
        self.assertIn(
            {
                'block': ['{} (type "{}") can only be block-booked with a ' \
                          '"{}" block type.'.format(
                    event1, event1.event_type, event1.event_type
                )] \
            },
            errors)
        bookings = Booking.objects.filter(event=event1)
        self.assertEqual(len(bookings), 0)
        self.assertEqual(Booking.objects.count(), 10)

    def test_cannot_overbook_block(self):
        event_type = mommy.make_recipe('booking.event_type_PC')
        event = mommy.make_recipe('booking.future_EV', event_type=event_type)
        event1 = mommy.make_recipe('booking.future_EV', event_type=event_type)
        block = mommy.make_recipe(
            'booking.block', block_type__event_type=event_type,
            block_type__size=1,
            user=self.user
        )
        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-2-event': event.id,
                'bookings-2-status': 'OPEN',
                'bookings-2-block': block.id
            }
        )

        # create new booking with this block
        self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )
        self.assertEqual(Booking.objects.count(), 11)
        bookings = Booking.objects.filter(event=event)
        self.assertEqual(len(bookings), 1)
        new_booking = bookings[0]
        self.assertEqual(new_booking.block, block)

        # block is now full
        block = Block.objects.get(id=block.id)
        self.assertTrue(block.full)

        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 4,
                'bookings-INITIAL_FORMS': 3,
                'bookings-2-id': new_booking.id,
                'bookings-2-event': event.id,
                'bookings-2-status': new_booking.status,
                'bookings-3-event': event1.id,
                'bookings-3-block': block.id,
                'bookings-3-status': 'OPEN'
            }
        )
        # try to create new booking with this block
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )
        errors = resp.context_data['userbookingformset'].errors
        self.assertIn(
            {
                'block': ['Block selected for {} is now full. ' \
                            'Add another block for this user or confirm ' \
                            'payment was made directly.'.format(event1)] \
            },
            errors)

    def test_cannot_create_new_block_booking_when_no_available_blocktype(self):
        event1 = mommy.make_recipe('booking.future_EV')
        event2 = mommy.make_recipe('booking.future_PC')

        block1 = mommy.make_recipe(
            'booking.block', block_type__event_type=event1.event_type,
            user=self.user
        )

        self.assertEqual(Booking.objects.count(), 10)
        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-2-event': event2.id,
                'bookings-2-status': 'OPEN',
                'bookings-2-block': block1.id
            }
        )
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )
        errors = resp.context_data['userbookingformset'].errors
        self.assertIn(
            {
                'block': ['{} ({} type "{}") cannot be ' \
                            'block-booked'.format(
                    event2, 'class', event2.event_type
                )]
            },
            errors)
        bookings = Booking.objects.filter(event=event2)
        self.assertEqual(len(bookings), 0)
        self.assertEqual(Booking.objects.count(), 10)

    def test_cannot_add_booking_to_full_event(self):
        event = mommy.make_recipe('booking.future_EV', max_participants=2)
        mommy.make_recipe('booking.booking', event=event, _quantity=2)
        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-2-event': event.id,
                'bookings-2-status': 'OPEN'
            }
        )
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )
        # redirects and doesn't make booking
        self.assertEqual(resp.status_code, 302)
        # new booking has not been made
        bookings = Booking.objects.filter(event=event)
        self.assertEqual(len(bookings), 2)

    def test_formset_unchanged(self):
        """
        test formset submitted unchanged redirects back to user bookings list
        """
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=self.formset_data(
                {'formset_submitted': 'Submit'}
            )
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url,
            reverse(
                'studioadmin:user_bookings_list',
                kwargs={'user_id': self.user.id, 'booking_status': 'future'}
            )
        )

    def test_create_new_booking_as_free_class(self):
        event1 = mommy.make_recipe(
            'booking.future_PC',
            event_type__subtype='Pole level class'
        )
        block1 = mommy.make_recipe(
            'booking.block', block_type__event_type=event1.event_type,
            user=self.user
        )

        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-2-event': event1.id,
                'bookings-2-status': 'OPEN',
                'bookings-2-free_class': True
            }
        )
        self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )
        booking = Booking.objects.get(event=event1)
        self.assertTrue(booking.free_class)
        self.assertTrue(booking.paid)
        self.assertTrue(booking.payment_confirmed)

    def test_cannot_assign_free_class_to_block(self):
        event1 = mommy.make_recipe(
            'booking.future_PC',
            event_type__subtype='Pole level class'
        )
        block1 = mommy.make_recipe(
            'booking.block', block_type__event_type=event1.event_type,
            user=self.user
        )
        form_data = self.formset_data(
            {
                'bookings-TOTAL_FORMS': 3,
                'bookings-2-event': event1.id,
                'bookings-2-status': 'OPEN',
                'bookings-2-block': block1.id,
                'bookings-2-free_class': True
            }
        )
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )
        errors = resp.context_data['userbookingformset'].errors
        self.assertIn(
            {
                'free_class': ['"Free class" cannot be assigned to a block.']
            },
            errors)
        bookings = Booking.objects.filter(event=event1)
        self.assertEqual(len(bookings), 0)

    def test_confirmation_email_sent_if_data_changed(self):
        form_data = self.formset_data(
            {
                'bookings-0-status': 'CANCELLED',
                'bookings-0-send_confirmation': 'on',
            }
        )
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_confirmation_email_not_sent_if_data_unchanged(self):
        form_data=self.formset_data(
            {'formset_submitted': 'Submit',
            'bookings-0-send_confirmation': 'on'}
        )
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=form_data
            )
        self.assertEqual(len(mail.outbox), 0)


class UserBlocksViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(UserBlocksViewTests, self).setUp()
        self.block = mommy.make_recipe('booking.block', user=self.user)

    def _get_response(self, user, user_id):
        url = reverse(
            'studioadmin:user_blocks_list',
            kwargs={'user_id': user_id}
        )
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return user_blocks_view(request, user_id)

    def _post_response(self, user, user_id, form_data):
        url = reverse(
            'studioadmin:user_blocks_list',
            kwargs={'user_id': user_id}
        )
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return user_blocks_view(request, user_id)

    def formset_data(self, extra_data={}):

        data = {
            'blocks-TOTAL_FORMS': 1,
            'blocks-INITIAL_FORMS': 1,
            'blocks-0-id': self.block.id,
            'blocks-0-block_type': self.block.block_type.id,
            'blocks-0-start_date': self.block.start_date.strftime('%d/%m/%y')
            }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse(
            'studioadmin:user_blocks_list',
            kwargs={'user_id': self.user.id}
        )
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user, self.user.id)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user, self.user.id)
        self.assertEquals(resp.status_code, 200)

    def test_view_users_blocks(self):
        """
        Test only user's bookings for future events shown by default
        """
        new_user = mommy.make_recipe('booking.user')
        new_blocks = mommy.make_recipe(
            'booking.block', user=new_user, _quantity=2
        )
        self.assertEqual(Block.objects.count(), 3)
        resp = self._get_response(self.staff_user, new_user.id)
        # get all but last form (last form is the empty extra one)
        block_forms = resp.context_data['userblockformset'].forms[:-1]
        self.assertEqual(len(block_forms), 2)
        self.assertEqual(
            [block.instance for block in block_forms],
            new_blocks
        )

    def test_can_update_block(self):
        self.assertFalse(self.block.paid)
        resp = self._post_response(
            self.staff_user, self.user.id,
            self.formset_data({'blocks-0-paid': True})
        )
        block = Block.objects.get(id=self.block.id)
        self.assertTrue(block.paid)

    def test_can_create_block(self):
        block_type = mommy.make_recipe('booking.blocktype')
        self.assertEqual(Block.objects.count(), 1)
        resp = self._post_response(
            self.staff_user, self.user.id,
            self.formset_data(
                {
                    'blocks-TOTAL_FORMS': 2,
                    'blocks-1-block_type': block_type.id
                }
            )
        )
        self.assertEqual(Block.objects.count(), 2)

    def test_formset_unchanged(self):
        """
        test formset submitted unchanged redirects back to user block list
        """
        resp = self._post_response(
            self.staff_user, self.user.id, form_data=self.formset_data()
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url,
            reverse(
                'studioadmin:user_blocks_list',
                kwargs={'user_id': self.user.id}
            )
        )


class ActivityLogListViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(ActivityLogListViewTests, self).setUp()
        # 9 logs
        # 2 logs when self.user and self.staff_user are created in setUp
        # 2 for empty cron jobs
        # 3 with log messages to test search text
        # 2 with fixed dates to test search date
        mommy.make(
            ActivityLog,
            log='email_warnings job run; no unpaid booking warnings to send'
        )
        mommy.make(
            ActivityLog,
            log='cancel_unpaid_bookings job run; no bookings to cancel'
        )
        mommy.make(ActivityLog, log='Test log message')
        mommy.make(ActivityLog, log='Test log message1')
        mommy.make(ActivityLog, log='Test log message2')
        mommy.make(
            ActivityLog,
            timestamp=datetime(2015, 1, 1, 16, 0, tzinfo=timezone.utc),
            log='Log with test date'
        )
        mommy.make(
            ActivityLog,
            timestamp=datetime(2015, 1, 1, 4, 0, tzinfo=timezone.utc),
            log='Log with test date for search'
        )

    def _get_response(self, user, form_data={}):
        url = reverse('studioadmin:activitylog')
        session = _create_session()
        request = self.factory.get(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        view = ActivityLogListView.as_view()
        return view(request)

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse('studioadmin:activitylog')
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user)
        self.assertEquals(resp.status_code, 200)

    def test_empty_cron_job_logs_filtered_by_default(self):
        resp = self._get_response(self.staff_user)
        self.assertEqual(len(resp.context_data['logs']), 7)

    def test_filter_out_empty_cron_job_logs(self):
        resp = self._get_response(
            self.staff_user, {'hide_empty_cronjobs': True}
        )
        self.assertEqual(len(resp.context_data['logs']), 7)

    def test_search_text(self):
        resp = self._get_response(self.staff_user, {
            'search_submitted': 'Search',
            'search': 'message1'})
        self.assertEqual(len(resp.context_data['logs']), 1)

        resp = self._get_response(self.staff_user, {
            'search_submitted': 'Search',
            'search': 'message'})
        self.assertEqual(len(resp.context_data['logs']), 3)

    def test_search_date(self):
        resp = self._get_response(
            self.staff_user, {
                'search_submitted': 'Search',
                'search_date': '01-Jan-2015'
            }
        )
        self.assertEqual(len(resp.context_data['logs']), 2)

    def test_invalid_search_date_format(self):
        """
        invalid search date returns all results and a message
        """
        resp = self._get_response(
            self.staff_user, {
                'search_submitted': 'Search',
                'search_date': '01-34-2015'}
        )
        self.assertEqual(len(resp.context_data['logs']), 9)

    def test_search_date_and_text(self):
        resp = self._get_response(
            self.staff_user, {
                'search_submitted': 'Search',
                'search_date': '01-Jan-2015',
                'search': 'test date for search'}
        )
        self.assertEqual(len(resp.context_data['logs']), 1)

    def test_reset(self):
        """
        Test that reset button resets the search text and date and excludes
        empty cron job messages
        """
        resp = self._get_response(
            self.staff_user, {
                'search_submitted': 'Search',
                'search_date': '01-Jan-2015',
                'search': 'test date for search'
            }
        )
        self.assertEqual(len(resp.context_data['logs']), 1)

        resp = self._get_response(
            self.staff_user, {
                'search_date': '01-Jan-2015',
                'search': 'test date for search',
                'reset': 'Reset'
            }
        )
        self.assertEqual(len(resp.context_data['logs']), 7)


class WaitingListViewStudioAdminTests(TestPermissionMixin, TestCase):

    def _get_response(self, user, event):
        url = reverse(
            'studioadmin:event_waiting_list', kwargs={"event_id": event.id}
        )
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return event_waiting_list_view(request, event_id=event.id)

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        event = mommy.make_recipe('booking.future_PC')
        url = reverse(
            'studioadmin:event_waiting_list', kwargs={'event_id':event.id}
        )
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        event = mommy.make_recipe('booking.future_PC')
        resp = self._get_response(self.user, event)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        event = mommy.make_recipe('booking.future_PC')
        resp = self._get_response(self.staff_user, event)
        self.assertEquals(resp.status_code, 200)

    def test_waiting_list_users_shown(self):
        """
        Only show users on the waiting list for the relevant event
        """
        event = mommy.make_recipe('booking.future_PC')
        event1 = mommy.make_recipe('booking.future_PC')

        event_wl = mommy.make_recipe(
            'booking.waiting_list_user', event=event, _quantity=3
        )
        mommy.make_recipe(
            'booking.waiting_list_user', event=event1, _quantity=3
        )
        resp = self._get_response(self.staff_user, event)

        waiting_list_users = resp.context_data['waiting_list_users']
        self.assertEqual(set(waiting_list_users), set(event_wl))
