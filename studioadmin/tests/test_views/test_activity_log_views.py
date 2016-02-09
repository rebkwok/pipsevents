from datetime import datetime
from model_mommy import mommy

from django.core.urlresolvers import reverse
from django.test import TestCase
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone

from activitylog.models import ActivityLog
from booking.tests.helpers import _create_session
from studioadmin.views import ActivityLogListView

from studioadmin.tests.test_views.helpers import TestPermissionMixin


class ActivityLogListViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(ActivityLogListViewTests, self).setUp()
        # 10 logs
        # 3 logs when self.user, self.instructor_user and self.staff_user
        # are created in setUp
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

    def test_instructor_group_cannot_access(self):
        """
        test that the page redirects if user is in the instructor group but is
        not a staff user
        """
        resp = self._get_response(self.instructor_user)
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
        self.assertEqual(len(resp.context_data['logs']), 8)

    def test_filter_out_empty_cron_job_logs(self):
        resp = self._get_response(
            self.staff_user, {'hide_empty_cronjobs': True}
        )
        self.assertEqual(len(resp.context_data['logs']), 8)

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
        self.assertEqual(len(resp.context_data['logs']), 10)

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
        self.assertEqual(len(resp.context_data['logs']), 8)
