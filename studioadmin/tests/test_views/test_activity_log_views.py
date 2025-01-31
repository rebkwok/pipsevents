from datetime import datetime
from datetime import timezone as dt_timezone

from model_bakery import baker

from django.urls import reverse
from django.test import TestCase

from activitylog.models import ActivityLog

from studioadmin.tests.test_views.helpers import TestPermissionMixin


class ActivityLogListViewTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.url = reverse('studioadmin:activitylog')
        
    def setUp(self):
        super(ActivityLogListViewTests, self).setUp()
        # 17 logs
        # 1 for DP creation
        # 6 logs when self.user, self.instructor_user and self.staff_user
        # are created in setUp (create user and sign DP agreement)
        # 1 for disclaimer content creation
        # 1 for online disclaimer creation for self.user
        
        # 2 for empty cron jobs
        # 3 with log messages to test search text
        # 2 with fixed dates to test search date
        baker.make(
            ActivityLog,
            log='email_warnings job run; no unpaid booking warnings to send'
        )
        baker.make(
            ActivityLog,
            log='cancel_unpaid_bookings job run; no bookings to cancel'
        )
        baker.make(ActivityLog, log='Test log message')
        baker.make(ActivityLog, log='Test log message1 One')
        baker.make(ActivityLog, log='Test log message2 Two')
        baker.make(
            ActivityLog,
            timestamp=datetime(2015, 1, 1, 16, 0, tzinfo=dt_timezone.utc),
            log='Log with test date'
        )
        baker.make(
            ActivityLog,
            timestamp=datetime(2015, 1, 1, 4, 0, tzinfo=dt_timezone.utc),
            log='Log with test date for search'
        )

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
       
        resp = self.client.get(self.url)
        redirected_url = reverse('account_login') + "?next={}".format(self.url)
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
        self.client.force_login(self.staff_user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_empty_cron_job_logs_filtered_by_default(self):
        self.client.force_login(self.staff_user)
        resp = self.client.get(self.url)
        self.assertEqual(len(resp.context_data['logs']), 15)

    def test_filter_out_empty_cron_job_logs(self):
        self.client.force_login(self.staff_user)
        resp = self.client.get(self.url + "?hide_empty_cronjobs=True")
        self.assertEqual(len(resp.context_data['logs']), 15)

    def test_search_text(self):
        self.client.force_login(self.staff_user)
        resp = self.client.get(self.url + "?search_submitted=Search&search=message1")
        self.assertEqual(len(resp.context_data['logs']), 1)

        self.client.force_login(self.staff_user)
        resp = self.client.get(self.url + "?search_submitted=Search&search=message")
        self.assertEqual(len(resp.context_data['logs']), 3)

    def test_search_is_case_insensitive(self):
        self.client.force_login(self.staff_user)
        resp = self.client.get(self.url + "?search_submitted=Search&search=Message")
        self.assertEqual(len(resp.context_data['logs']), 3)

    def test_search_date(self):
        self.client.force_login(self.staff_user)
        resp = self.client.get(self.url + "?search_submitted=Search&search_date=01-Jan-2015")
        self.assertEqual(len(resp.context_data['logs']), 2)

    def test_invalid_search_date_format(self):
        """
        invalid search date returns all results and a message
        """
        self.client.force_login(self.staff_user)
        resp = self.client.get(self.url + "?search_submitted=Search&search_date=01-34-2015")
        self.assertEqual(len(resp.context_data['logs']), 17)

    def test_search_date_and_text(self):
        self.client.force_login(self.staff_user)
        resp = self.client.get(self.url + "?search_submitted=Search&search_date=01-Jan-2015&search=test date for search")
        self.assertEqual(len(resp.context_data['logs']), 1)
    
    def test_search_date_and_text_with_pagination(self):
        baker.make(
            ActivityLog,
            timestamp=datetime(2015, 1, 1, 15, 10, tzinfo=dt_timezone.utc),
            _quantity=25
        )
        self.client.force_login(self.staff_user)
        url = reverse('studioadmin:activitylog') + f"?search_submitted=Search&search_date='01-Jan-2015"
        resp = self.client.get(url)
        assert len(resp.context_data['logs']) == 20

        resp = self.client.get(url + "&page=2")
        assert len(resp.context_data['logs']) == 20

        resp = self.client.get(url + "&page=3")
        assert len(resp.context_data['logs']) == ActivityLog.objects.count() - 40

    def test_search_multiple_terms(self):
        """
        Search with multiple terms returns only logs that contain all terms
        """
        self.client.force_login(self.staff_user)
        resp = self.client.get(self.url + "?search_submitted=Search&search=Message")
        self.assertEqual(len(resp.context_data['logs']), 3)

        resp = self.client.get(self.url + "?search_submitted=Search&search=Message One")
        self.assertEqual(len(resp.context_data['logs']), 1)

        resp = self.client.get(self.url + "?search_submitted=Search&search=test one")
        self.assertEqual(len(resp.context_data['logs']), 1)

    def test_reset(self):
        """
        Test that reset button resets the search text and date and excludes
        empty cron job messages
        """
        self.client.force_login(self.staff_user)
        resp = self.client.get(self.url + "?search_submitted=Search&search_date=01-Jan-2015&search=test date for search")
        self.assertEqual(len(resp.context_data['logs']), 1)
        resp = self.client.get(self.url + "?search_date=01-Jan-2015&search=test date for search&reset=Reset")
        self.assertEqual(len(resp.context_data['logs']), 15)
