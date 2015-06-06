from datetime import datetime, timedelta
from mock import Mock, patch
from model_mommy import mommy

from django.core.urlresolvers import reverse
from django.test import TestCase, RequestFactory
from django.test.client import Client
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone

from booking.models import Event, Booking, Block
from booking.tests.helpers import set_up_fb, _create_session, setup_view

from studioadmin.views import ConfirmPaymentView


class ConfirmPaymentViewTests(TestCase):

    def setUp(self):
        set_up_fb()
        self.client = Client()
        self.factory = RequestFactory()
        self.user = mommy.make_recipe('booking.user')
        self.staff_user = mommy.make_recipe('booking.user')
        self.staff_user.is_staff = True
        self.staff_user.save()
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

    # def test_with_unpaid_booking(self):
    #     """
    #     Change an unpaid booking to paid and confirmed
    #     """
    #     self.assertFalse(self.booking.paid)
    #     self.assertFalse(self.booking.payment_confirmed)
    #
    #     form_data = {
    #         'user': self.booking.user.id,
    #         'event': self.booking.event.id,
    #         'status': self.booking.status,
    #         'date_booked': self.booking.date_booked.strftime('%y %m %d %H:%M'),
    #         'paid': 'on',
    #         'payment_confirmed': 'on'
    #     }
    #     resp = self._post_response(self.staff_user, self.booking, form_data)
    #     import ipdb; ipdb.set_trace()
    #     self.assertTrue(self.booking.paid)
    #     self.assertTrue(self.booking.payment_confirmed)


class ConfirmRefundViewTests(TestCase):

    pass


class EventRegisterListViewTests(TestCase):

    pass


class EventRegisterViewTests(TestCase):

    pass


class EventAdminListTests(TestCase):

    pass


class EventAdminUpdateViewTests(TestCase):

    pass


class EventAdminCreateViewTests(TestCase):

    pass


class TimetableAdminListView(TestCase):

    pass


class TimetableSessionUpdateView(TestCase):

    pass


class TimetableSessionCreateView(TestCase):

    pass


class UploadTimetableTests(TestCase):

    pass


class UserListViewTests(TestCase):

    pass


class BlockListViewTests(TestCase):

    pass


class EmailUsersTests(TestCase):

    pass


class UserBookingsViewTests(TestCase):

    pass
    # try to rebook cancelled
    # trying to overbook block
    # cannot block book event with no available blocktype
    # trying to block book with wrong block type

class UserBlocksViewTests(TestCase):

    pass
