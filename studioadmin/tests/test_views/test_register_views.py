from datetime import datetime

from model_mommy import mommy

from django.core.urlresolvers import reverse
from django.test import TestCase
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone

from booking.models import Event, Booking, Block, BlockType
from booking.tests.helpers import _create_session
from studioadmin.views import (
    EventRegisterListView,
    register_view,
    register_print_day,
)
from studioadmin.tests.test_views.helpers import TestPermissionMixin


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

        resp = self._get_response(self.user, 'lessons')
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user, 'events')
        self.assertEquals(resp.status_code, 200)

    def test_can_access_class_registers_if_instructor(self):
        """
        test that the page can be accessed by a non staff user if in the
        instructors group and event type is not events
        """
        resp = self._get_response(self.instructor_user, 'events')
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

        resp = self._get_response(self.instructor_user, 'lessons')
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

    def test_class_register_list_excludes_events(self):
        mommy.make_recipe('booking.future_EV', _quantity=4)
        mommy.make_recipe('booking.future_PC', _quantity=5)
        url = reverse('studioadmin:class_register_list')
        resp = self._get_response(self.staff_user, 'lessons', url=url)
        self.assertEquals(len(resp.context_data['events']), 5)

    def test_class_register_list_shows_room_hire_with_classes(self):
        mommy.make_recipe('booking.future_EV', _quantity=4)
        mommy.make_recipe('booking.future_PC', _quantity=5)
        mommy.make_recipe('booking.future_RH', _quantity=5)

        url = reverse('studioadmin:class_register_list')
        resp = self._get_response(self.staff_user, 'lessons', url=url)
        self.assertEquals(len(resp.context_data['events']), 10)


class EventRegisterViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(EventRegisterViewTests, self).setUp()
        self.event = mommy.make_recipe(
            'booking.future_EV', max_participants=16
        )
        self.booking1 = mommy.make_recipe('booking.booking', event=self.event)
        self.booking2 = mommy.make_recipe('booking.booking', event=self.event)

    def _get_response(
            self, user, event_slug,
            status_choice='OPEN', print_view=False, ev_type='event'
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
            print_view=print_view)

    def _post_response(
            self, user, event_slug, form_data,
            status_choice='OPEN', print_view=False, ev_type='event'
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
            print_view=print_view)

    def formset_data(self, extra_data={}, status_choice='OPEN'):

        data = {
            'bookings-TOTAL_FORMS': 2,
            'bookings-INITIAL_FORMS': 2,
            'bookings-0-id': self.booking1.id,
            'bookings-0-user': self.booking1.user.id,
            'bookings-0-paid': self.booking1.paid,
            'bookings-0-deposit_paid': self.booking1.paid,
            'bookings-0-attended': self.booking1.attended,
            'bookings-1-id': self.booking2.id,
            'bookings-1-user': self.booking2.user.id,
            'bookings-1-deposit_paid': self.booking2.paid,
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

    def test_can_access_if_instructor(self):
        """
        test that the page can be accessed by a non staff user if in the
        instructors group
        """
        resp = self._get_response(self.instructor_user, self.event.slug)
        self.assertEquals(resp.status_code, 200)

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
        # bookings: open - 5 plus 2 created in setup, cancelled = 5 (12)
        # also shows forms for available spaces (16 max, 9 spaces)
        self.assertEquals(len(resp.context_data['formset'].forms), 21)

        resp = self._get_response(
            self.staff_user, self.event.slug, status_choice='OPEN'
        )
        # 5 open plus 2 created in setup, plus empty forms for available
        # spaces to max participants 16
        forms = resp.context_data['formset'].forms
        self.assertEquals(len(forms), 16)
        self.assertEquals(
            set([form.instance.status for form in forms]), {'OPEN'}
            )

        resp = self._get_response(
            self.staff_user, self.event.slug, status_choice='CANCELLED'
        )
        forms = resp.context_data['formset'].forms
        # 5 cancelled plus empty forms for 9 available spaces
        self.assertEquals(len(forms), 14)

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

    def test_can_update_booking_deposit_paid(self):
        self.assertFalse(self.booking1.paid)
        self.assertFalse(self.booking1.deposit_paid)

        formset_data = self.formset_data({
            'bookings-0-deposit_paid': True,
            'formset_submitted': 'Save changes'
        })

        self._post_response(
            self.staff_user, self.event.slug,
            formset_data, status_choice='OPEN'
        )

        self.booking1.refresh_from_db()
        self.assertTrue(self.booking1.deposit_paid)
        self.assertFalse(self.booking1.paid)

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

    def test_selecting_block_makes_booking_paid(self):
        self.booking1.paid = False
        self.booking1.save()
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
        self.assertTrue(booking.paid)

    def test_unselecting_block_makes_booking_paid(self):
        block_type = mommy.make(
            BlockType, event_type=self.event.event_type
        )
        block = mommy.make_recipe(
            'booking.block', block_type=block_type, user=self.user, paid=True
        )
        self.booking1.block = block
        self.booking1.paid = True
        self.booking1.save()
        self.assertTrue(block.active_block())

        formset_data = self.formset_data({
            'bookings-0-block': '',
            'formset_submitted': 'Save changes'
        })
        self._post_response(
            self.staff_user, self.event.slug,
            formset_data, status_choice='OPEN'
        )
        booking = Booking.objects.get(id=self.booking1.id)
        self.assertIsNone(booking.block)
        self.assertFalse(booking.paid)

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
            self.staff_user, self.event.slug, print_view=False,
            status_choice='OPEN'
        )
        resp.render()
        self.assertIn(
            '<select id="id_status_choice" name="status_choice">',
            str(resp.content),
        )
        resp = self._get_response(
            self.staff_user, self.event.slug, print_view=True,
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
            print_view=False,
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
            print_view=False,
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
            print_view=False,
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


class RegisterByDateTests(TestPermissionMixin, TestCase):

    def _get_response(self, user):
        url = reverse('studioadmin:register-day')
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return register_print_day(request)

    def _post_response(self, user,form_data):
        url = reverse('studioadmin:register-day')
        session = _create_session()
        request = self.factory.post(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return register_print_day(request)

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse('studioadmin:register-day')
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

    def test_show_events_by_selected_date(self):

        events = mommy.make_recipe(
            'booking.future_EV',
            date=datetime(
                year=2015, month=9, day=7,
                hour=18, minute=0, tzinfo=timezone.utc
            ),
            _quantity=3
        )
        mommy.make_recipe(
            'booking.future_EV',
            date=datetime(
                year=2015, month=9, day=6,
                hour=18, minute=0, tzinfo=timezone.utc
            ),
            _quantity=3
        )

        resp = self._post_response(
            self.staff_user, {
                'register_date': 'Mon 07 Sep 2015',
                'exclude_ext_instructor': True,
                'register_format': 'full',
                'show': 'show'}
        )
        self.assertEqual(Event.objects.count(), 6)

        form = resp.context_data['form']
        self.assertIn('select_events', form.fields)
        selected_events = form.fields['select_events'].choices

        self.assertEqual(
            [ev[0] for ev in selected_events],
            [event.id for event in events]
        )

    def test_print_selected_events(self):
        events = mommy.make_recipe(
            'booking.future_EV',
            date=datetime(
                year=2015, month=9, day=7,
                hour=18, minute=0, tzinfo=timezone.utc
            ),
            _quantity=3
        )

        resp = self._post_response(
            self.staff_user, {
                'register_date': 'Mon 07 Sep 2015',
                'exclude_ext_instructor': True,
                'register_format': 'full',
                'print': 'print',
                'select_events': [events[0].id, events[1].id]}
        )
        self.assertEqual(len(resp.context_data['events']), 2)

        for event in resp.context_data['events']:
            self.assertTrue(event['event'] in [events[0], events[1]])

    def test_print_unselected_events(self):
        """
        If no events selected (i.e. print button pressed without using the
        "show classes" button first), all events for that date are printed,
         with exception of ext instructor classes which are based on the
         checkbox value
        """
        events = mommy.make_recipe(
            'booking.future_EV',
            date=datetime(
                year=2015, month=9, day=7,
                hour=18, minute=0, tzinfo=timezone.utc
            ),
            _quantity=3
        )

        resp = self._post_response(
            self.staff_user, {
                'register_date': 'Mon 07 Sep 2015',
                'exclude_ext_instructor': True,
                'register_format': 'full',
                'print': 'print',
                'select_events': [event.id for event in events]
            }
        )
        self.assertEqual(len(resp.context_data['events']), 3)

        for event in resp.context_data['events']:
            self.assertTrue(event['event'] in events)

    def test_print_open_bookings_for_events(self):
        event1 = mommy.make_recipe(
            'booking.future_EV',
            name="event1",
            date=datetime(
                year=2015, month=9, day=7,
                hour=18, minute=0, tzinfo=timezone.utc
            ),
        )
        event2 = mommy.make_recipe(
            'booking.future_EV',
            name='event2',
            date=datetime(
                year=2015, month=9, day=7,
                hour=19, minute=0, tzinfo=timezone.utc
            ),
        )

        ev1_bookings = mommy.make_recipe(
            'booking.booking',
            event=event1,
            _quantity=2
        )
        ev1_cancelled_booking = mommy.make_recipe(
            'booking.booking',
            event=event2,
            status='CANCELLED'
        )
        ev2_bookings = mommy.make_recipe(
            'booking.booking',
            event=event1,
            _quantity=2
        )

        resp = self._post_response(
            self.staff_user, {
                'register_date': 'Mon 07 Sep 2015',
                'exclude_ext_instructor': True,
                'register_format': 'full',
                'print': 'print',
                'select_events': [event1.id, event2.id]
            }
        )

        self.assertEqual(len(resp.context_data['events']), 2)

        for event in resp.context_data['events']:
            self.assertTrue(event['event'] in [event1, event2])
            for booking in event['bookings']:
                self.assertTrue(booking['booking'] in event['event'].bookings.all())

    def test_print_format_no_available_blocktype(self):
        event = mommy.make_recipe(
            'booking.future_EV',
            name="event1",
            date=datetime(
                year=2015, month=9, day=7,
                hour=18, minute=0, tzinfo=timezone.utc
            ),
        )

        resp = self._post_response(
            self.staff_user, {
                'register_date': 'Mon 07 Sep 2015',
                'exclude_ext_instructor': True,
                'register_format': 'full',
                'print': 'print',
                'select_events': [event.id]
            }
        )

        self.assertEqual(len(resp.context_data['events']), 1)
        # check correct headings are present
        self.assertIn('>Attended<', resp.rendered_content)
        self.assertIn('>Status<', resp.rendered_content)
        self.assertIn('>User<', resp.rendered_content)
        self.assertIn('>Deposit Paid<', resp.rendered_content)
        self.assertIn('>Fully Paid<', resp.rendered_content)

        resp = self._post_response(
            self.staff_user, {
                'register_date': 'Mon 07 Sep 2015',
                'exclude_ext_instructor': True,
                'register_format': 'namesonly',
                'print': 'print',
                'select_events': [event.id]
            }
        )

        self.assertEqual(len(resp.context_data['events']), 1)
        # check correct headings are present
        self.assertIn('>Attended<', resp.rendered_content)
        self.assertIn('>User<', resp.rendered_content)
        self.assertNotIn('>Status<', resp.rendered_content)
        self.assertNotIn('>Deposit Paid<', resp.rendered_content)
        self.assertNotIn('>Fully Paid<', resp.rendered_content)

    def test_print_format_with_available_blocktype(self):
        event = mommy.make_recipe(
            'booking.future_EV',
            name="event1",
            date=datetime(
                year=2015, month=9, day=7,
                hour=18, minute=0, tzinfo=timezone.utc
            ),
        )

        mommy.make_recipe(
            'booking.blocktype',
            event_type=event.event_type
        )

        resp = self._post_response(
            self.staff_user, {
                'register_date': 'Mon 07 Sep 2015',
                'exclude_ext_instructor': True,
                'register_format': 'full',
                'print': 'print',
                'select_events': [event.id]
            }
        )

        self.assertEqual(len(resp.context_data['events']), 1)
        # check correct headings are present
        self.assertIn('>Attended<', resp.rendered_content)
        self.assertIn('>Status<', resp.rendered_content)
        self.assertIn('>User<', resp.rendered_content)
        self.assertIn('>Deposit Paid<', resp.rendered_content)
        self.assertIn('>Fully Paid<', resp.rendered_content)
        self.assertIn('>Booked with<br/>block<', resp.rendered_content)
        self.assertIn('>User\'s block</br>expiry date<', resp.rendered_content)
        self.assertIn('>Block size<', resp.rendered_content)
        self.assertIn('>Block bookings</br>used<', resp.rendered_content)

        resp = self._post_response(
            self.staff_user, {
                'register_date': 'Mon 07 Sep 2015',
                'exclude_ext_instructor': True,
                'register_format': 'namesonly',
                'print': 'print',
                'select_events': [event.id]
            }
        )

        self.assertEqual(len(resp.context_data['events']), 1)
        # check correct headings are present
        self.assertIn('>Attended<', resp.rendered_content)
        self.assertIn('>User<', resp.rendered_content)
        self.assertNotIn('>Status<', resp.rendered_content)
        self.assertNotIn('>Deposit Paid<', resp.rendered_content)
        self.assertNotIn('>Fully Paid<', resp.rendered_content)
        self.assertNotIn('>Book with<br/>available block<', resp.rendered_content)
        self.assertNotIn('>User\'s block</br>expiry date<', resp.rendered_content)
        self.assertNotIn('>Block size<', resp.rendered_content)
        self.assertNotIn('>Bookings used<', resp.rendered_content)
