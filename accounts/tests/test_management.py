import csv
import os

from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch
from model_mommy import mommy

from django.conf import settings
from django.core import management, mail
from django.test import TestCase, override_settings
from django.contrib.auth.models import User, Group
from django.utils import timezone

from accounts.management.commands.import_disclaimer_data import logger as \
    import_disclaimer_data_logger
from accounts.management.commands.export_encrypted_disclaimers import EmailMessage
from accounts.models import PrintDisclaimer, OnlineDisclaimer

from booking.models import Booking
from common.tests.helpers import TestSetupMixin, PatchRequestMixin


class DeleteExpiredDisclaimersTests(PatchRequestMixin, TestCase):

    def setUp(self):
        super(DeleteExpiredDisclaimersTests, self).setUp()
        self.user_online_only = mommy.make_recipe(
            'booking.user', first_name='Test', last_name='User')
        mommy.make(
            OnlineDisclaimer, user=self.user_online_only,
            date=timezone.now()-timedelta(370)
        )
        self.user_print_only = mommy.make_recipe(
            'booking.user', first_name='Test', last_name='User1'
        )
        mommy.make(
            PrintDisclaimer, user=self.user_print_only,
            date=timezone.now()-timedelta(370)
        )
        self.user_both = mommy.make_recipe(
            'booking.user', first_name='Test', last_name='User2'
        )
        mommy.make(
            OnlineDisclaimer, user=self.user_both,
            date=timezone.now()-timedelta(370)
        )
        mommy.make(
            PrintDisclaimer, user=self.user_both,
            date=timezone.now()-timedelta(370)
        )

    def test_disclaimers_deleted_if_no_bookings_in_past_year(self):
        self.assertEqual(OnlineDisclaimer.objects.count(), 2)
        self.assertEqual(PrintDisclaimer.objects.count(), 2)

        management.call_command('delete_expired_disclaimers')
        self.assertEqual(OnlineDisclaimer.objects.count(), 0)
        self.assertEqual(PrintDisclaimer.objects.count(), 0)

    def test_disclaimers_deleted_if_no_paid_booking_in_past_year(self):
        self.assertEqual(OnlineDisclaimer.objects.count(), 2)
        self.assertEqual(PrintDisclaimer.objects.count(), 2)

        # make one paid booking for self.user_online_only in past 365 days; this
        # user's disclaimer should not be deleted
        mommy.make_recipe(
            'booking.booking',
            user=self.user_online_only,
            event__date=timezone.now()-timedelta(360),
            paid=True
        )
        management.call_command('delete_expired_disclaimers')
        self.assertEqual(OnlineDisclaimer.objects.count(), 1)
        self.assertEqual(PrintDisclaimer.objects.count(), 0)
        self.assertEqual(
            OnlineDisclaimer.objects.first().user, self.user_online_only
        )

    def test_disclaimers_deleted_if_only_unpaid_booking_in_past_year(self):
        self.assertEqual(OnlineDisclaimer.objects.count(), 2)
        self.assertEqual(PrintDisclaimer.objects.count(), 2)

        # make one unpaid booking for self.user_online_only in past 365 days; this
        # user's disclaimer should still be deleted because unpaid
        mommy.make_recipe(
            'booking.booking',
            user=self.user_online_only,
            event__date=timezone.now()-timedelta(360),
            paid=False
        )
        management.call_command('delete_expired_disclaimers')
        self.assertEqual(OnlineDisclaimer.objects.count(), 0)
        self.assertEqual(PrintDisclaimer.objects.count(), 0)

    def test_both_print_and_online_disclaimers_deleted(self):
        self.assertEqual(OnlineDisclaimer.objects.count(), 2)
        self.assertEqual(PrintDisclaimer.objects.count(), 2)

        # make one paid booking for self.user_both in past 365 days; both other
        # disclaimers should be deleted because unpaid
        mommy.make_recipe(
            'booking.booking',
            user=self.user_both,
            event__date=timezone.now()-timedelta(360),
            paid=True
        )
        management.call_command('delete_expired_disclaimers')
        self.assertEqual(OnlineDisclaimer.objects.count(), 1)
        self.assertEqual(PrintDisclaimer.objects.count(), 1)

    def test_disclaimers_not_deleted_if_created_in_past_year(self):
        # make a user with a disclaimer created today
        user = mommy.make_recipe('booking.user')
        mommy.make(OnlineDisclaimer, user=user)

        self.assertEqual(OnlineDisclaimer.objects.count(), 3)
        self.assertEqual(PrintDisclaimer.objects.count(), 2)

        # user has no bookings in past 365 days, but disclaimer should not be
        # deleted because it was created < 365 days ago.  All others will be.
        management.call_command('delete_expired_disclaimers')
        self.assertEqual(OnlineDisclaimer.objects.count(), 1)
        self.assertEqual(PrintDisclaimer.objects.count(), 0)

    def test_disclaimers_not_deleted_if_updated_in_past_year(self):
        # make a user with a disclaimer created > yr ago but updated in past yr
        user = mommy.make_recipe('booking.user')
        mommy.make(
            OnlineDisclaimer, user=user, date=timezone.now() - timedelta(370),
            date_updated=timezone.now() - timedelta(360),
        )
        self.assertEqual(OnlineDisclaimer.objects.count(), 3)
        self.assertEqual(PrintDisclaimer.objects.count(), 2)

        # user has no bookings in past 365 days, but disclaimer should not be
        # deleted because it was created < 365 days ago.  The other 3 will be
        # deleted

        management.call_command('delete_expired_disclaimers')
        self.assertEqual(OnlineDisclaimer.objects.count(), 1)
        self.assertEqual(PrintDisclaimer.objects.count(), 0)

    def test_disclaimer_with_multiple_bookings(self):
        self.assertEqual(OnlineDisclaimer.objects.count(), 2)
        self.assertEqual(PrintDisclaimer.objects.count(), 2)

        # make paid and unpaid bookings for self.user_online_only in past 365
        # days and earlier; disclaimer not deleted
        mommy.make_recipe(
            'booking.booking',
            user=self.user_online_only,
            event__date=timezone.now()-timedelta(360),
            paid=True
        )
        mommy.make_recipe(
            'booking.booking',
            user=self.user_online_only,
            event__date=timezone.now()-timedelta(200),
            paid=False
        )
        mommy.make_recipe(
            'booking.booking',
            user=self.user_online_only,
            event__date=timezone.now()-timedelta(400),
            paid=True
        )
        mommy.make_recipe(
            'booking.booking',
            user=self.user_online_only,
            event__date=timezone.now()-timedelta(400),
            paid=False
        )

        management.call_command('delete_expired_disclaimers')
        # only disclaimer for self.user_online_only is not deleted
        self.assertEqual(OnlineDisclaimer.objects.count(), 1)
        self.assertEqual(PrintDisclaimer.objects.count(), 0)
        self.assertEqual(
            OnlineDisclaimer.objects.first().user, self.user_online_only
        )

    @patch('accounts.management.commands.delete_expired_disclaimers.send_mail')
    @patch('booking.email_helpers.send_mail')
    def test_email_errors(self, mock_send_mail, mock_send_mail1):
        mock_send_mail.side_effect = Exception('Error sending mail')
        mock_send_mail1.side_effect = Exception('Error sending mail')
        self.assertEqual(OnlineDisclaimer.objects.count(), 2)
        self.assertEqual(PrintDisclaimer.objects.count(), 2)

        management.call_command('delete_expired_disclaimers')
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(OnlineDisclaimer.objects.count(), 0)
        self.assertEqual(PrintDisclaimer.objects.count(), 0)

    def test_email_not_sent_to_studio_if_nothing_deleted(self):
        self.assertEqual(OnlineDisclaimer.objects.count(), 2)
        self.assertEqual(PrintDisclaimer.objects.count(), 2)

        for user in User.objects.all():
            mommy.make_recipe(
            'booking.booking',
            user=user,
            event__date=timezone.now()-timedelta(10),
            paid=True
        )

        management.call_command('delete_expired_disclaimers')
        self.assertEqual(OnlineDisclaimer.objects.count(), 2)
        self.assertEqual(PrintDisclaimer.objects.count(), 2)
        self.assertEqual(len(mail.outbox), 0)


@override_settings(LOG_FOLDER=os.path.dirname(__file__))
class ExportDisclaimersTests(TestCase):

    def setUp(self):
        mommy.make(OnlineDisclaimer, _quantity=10)

    def test_export_disclaimers_creates_default_bu_file(self):
        bu_file = os.path.join(settings.LOG_FOLDER, 'disclaimers_bu.csv')
        self.assertFalse(os.path.exists(bu_file))
        management.call_command('export_disclaimers')
        self.assertTrue(os.path.exists(bu_file))
        os.unlink(bu_file)

    def test_export_disclaimers_writes_correct_number_of_rows(self):
        bu_file = os.path.join(settings.LOG_FOLDER, 'disclaimers_bu.csv')
        management.call_command('export_disclaimers')

        with open(bu_file, 'r') as exported:
            reader = csv.reader(exported)
            rows = list(reader)
        self.assertEqual(len(rows), 11)  # 10 records plus header row
        os.unlink(bu_file)

    def test_export_disclaimers_with_filename_argument(self):
        bu_file = os.path.join(settings.LOG_FOLDER, 'test_file.csv')
        self.assertFalse(os.path.exists(bu_file))
        management.call_command('export_disclaimers', file=bu_file)
        self.assertTrue(os.path.exists(bu_file))
        os.unlink(bu_file)


@override_settings(LOG_FOLDER=os.path.dirname(__file__))
class ExportEncryptedDisclaimersTests(TestCase):

    def setUp(self):
        mommy.make(OnlineDisclaimer, _quantity=10)

    def test_export_disclaimers_creates_default_bu_file(self):
        bu_file = os.path.join(settings.LOG_FOLDER, 'disclaimers.bu')
        self.assertFalse(os.path.exists(bu_file))
        management.call_command('export_encrypted_disclaimers')
        self.assertTrue(os.path.exists(bu_file))
        os.unlink(bu_file)

    def test_export_disclaimers_sends_email(self):
        bu_file = os.path.join(settings.LOG_FOLDER, 'disclaimers.bu')
        management.call_command('export_encrypted_disclaimers')

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [settings.SUPPORT_EMAIL])

        os.unlink(bu_file)

    @patch.object(EmailMessage, 'send')
    def test_email_errors(self, mock_send):
        mock_send.side_effect = Exception('Error sending mail')
        bu_file = os.path.join(settings.LOG_FOLDER, 'disclaimers.bu')

        self.assertFalse(os.path.exists(bu_file))
        management.call_command('export_encrypted_disclaimers')
        # mail not sent, but back up still created
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(os.path.exists(bu_file))
        os.unlink(bu_file)

    def test_export_disclaimers_with_filename_argument(self):
        bu_file = os.path.join(settings.LOG_FOLDER, 'test_file.txt')
        self.assertFalse(os.path.exists(bu_file))
        management.call_command('export_encrypted_disclaimers', file=bu_file)
        self.assertTrue(os.path.exists(bu_file))
        os.unlink(bu_file)


class ImportDisclaimersTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.bu_file = os.path.join(
            os.path.dirname(__file__), 'test_data/test_disclaimers_backup.csv'
        )

    def test_import_disclaimers_no_matching_users(self):
        import_disclaimer_data_logger.warning = Mock()
        self.assertFalse(OnlineDisclaimer.objects.exists())
        management.call_command('import_disclaimer_data', file=self.bu_file)
        self.assertEqual(OnlineDisclaimer.objects.count(), 0)

        self.assertEqual(import_disclaimer_data_logger.warning.call_count, 3)
        self.assertIn(
            "Unknown user test_1 in backup data; data on row 1 not imported",
            str(import_disclaimer_data_logger.warning.call_args_list[0])
        )
        self.assertIn(
            "Unknown user test_2 in backup data; data on row 2 not imported",
            str(import_disclaimer_data_logger.warning.call_args_list[1])
        )
        self.assertIn(
            "Unknown user test_3 in backup data; data on row 3 not imported",
            str(import_disclaimer_data_logger.warning.call_args_list[2])
        )

    def test_import_disclaimers(self):
        for username in ['test_1', 'test_2', 'test_3']:
            mommy.make_recipe('booking.user', username=username)
        self.assertFalse(OnlineDisclaimer.objects.exists())
        management.call_command('import_disclaimer_data', file=self.bu_file)
        self.assertEqual(OnlineDisclaimer.objects.count(), 3)

    def test_import_disclaimers_existing_data(self):
        import_disclaimer_data_logger.warning = Mock()
        import_disclaimer_data_logger.info = Mock()

        # if disclaimer already exists for a user, it isn't imported
        for username in ['test_1', 'test_2']:
            mommy.make_recipe('booking.user', username=username)
        test_3 = mommy.make_recipe('booking.user', username='test_3')
        mommy.make(
            OnlineDisclaimer, user=test_3, name='Donald Duck')

        self.assertEqual(OnlineDisclaimer.objects.count(), 1)
        management.call_command('import_disclaimer_data', file=self.bu_file)
        self.assertEqual(OnlineDisclaimer.objects.count(), 3)

        # data has not been overwritten
        disclaimer = OnlineDisclaimer.objects.get(user=test_3)
        self.assertEqual(disclaimer.name, 'Donald Duck')

        self.assertEqual(import_disclaimer_data_logger.warning.call_count, 1)
        self.assertEqual(import_disclaimer_data_logger.info.call_count, 2)

        self.assertIn(
            "Disclaimer for test_1 imported from backup.",
            str(import_disclaimer_data_logger.info.call_args_list[0])
        )
        self.assertIn(
            "Disclaimer for test_2 imported from backup.",
            str(import_disclaimer_data_logger.info.call_args_list[1])
        )
        self.assertIn(
            "Disclaimer for test_3 already exists and has not been "
            "overwritten with backup data. Dates in db and back up DO NOT "
            "match",
            str(import_disclaimer_data_logger.warning.call_args_list[0])
        )

    def test_import_disclaimers_existing_data_matching_dates(self):
        import_disclaimer_data_logger.warning = Mock()
        import_disclaimer_data_logger.info = Mock()

        test_1 = mommy.make_recipe('booking.user', username='test_1')
        test_2 = mommy.make_recipe('booking.user', username='test_2')
        test_3 = mommy.make_recipe('booking.user', username='test_3')
        mommy.make(
            OnlineDisclaimer, user=test_2,
            date=datetime(2015, 1, 15, 15, 43, 19, 747445, tzinfo=timezone.utc),
            date_updated=datetime(
                2016, 1, 6, 15, 9, 16, 920219, tzinfo=timezone.utc
            )
        ),
        mommy.make(
            OnlineDisclaimer, user=test_3,
            date=datetime(2016, 2, 18, 16, 9, 16, 920219, tzinfo=timezone.utc),
        )

        self.assertEqual(OnlineDisclaimer.objects.count(), 2)
        management.call_command('import_disclaimer_data', file=self.bu_file)
        self.assertEqual(OnlineDisclaimer.objects.count(), 3)

        self.assertEqual(import_disclaimer_data_logger.warning.call_count, 2)
        self.assertEqual(import_disclaimer_data_logger.info.call_count, 1)

        self.assertIn(
            "Disclaimer for test_1 imported from backup.",
            str(import_disclaimer_data_logger.info.call_args_list[0])
        )
        self.assertIn(
            "Disclaimer for test_2 already exists and has not been "
            "overwritten with backup data. Dates in db and back up "
            "match",
            str(import_disclaimer_data_logger.warning.call_args_list[0])
        )
        self.assertIn(
            "Disclaimer for test_3 already exists and has not been "
            "overwritten with backup data. Dates in db and back up "
            "match",
            str(import_disclaimer_data_logger.warning.call_args_list[1])
        )

    def test_imported_data_is_correct(self):
        test_1 = mommy.make_recipe('booking.user', username='test_1')
        management.call_command('import_disclaimer_data', file=self.bu_file)
        test_1_disclaimer = OnlineDisclaimer.objects.get(user=test_1)

        self.assertEqual(test_1_disclaimer.name, 'Test User1')
        self.assertEqual(
            test_1_disclaimer.date,
            datetime(2015, 12, 18, 15, 32, 7, 191781, tzinfo=timezone.utc)
        )
        self.assertEqual(test_1_disclaimer.dob, date(1991, 11, 21))
        self.assertEqual(test_1_disclaimer.address, '11 Test Road')
        self.assertEqual(test_1_disclaimer.postcode, 'TS6 8JT')
        self.assertEqual(test_1_disclaimer.home_phone, '12345667')
        self.assertEqual(test_1_disclaimer.mobile_phone, '2423223423')
        self.assertEqual(test_1_disclaimer.emergency_contact1_name, 'Test1 Contact1')
        self.assertEqual(
            test_1_disclaimer.emergency_contact1_relationship, 'Partner'
        )
        self.assertEqual(
            test_1_disclaimer.emergency_contact1_phone, '8782347239'
        )
        self.assertEqual(test_1_disclaimer.emergency_contact2_name, 'Test2 Contact1')
        self.assertEqual(
            test_1_disclaimer.emergency_contact2_relationship, 'Father'
        )
        self.assertEqual(
            test_1_disclaimer.emergency_contact2_phone, '71684362378'
        )
        self.assertFalse(test_1_disclaimer.medical_conditions)
        self.assertEqual(test_1_disclaimer.medical_conditions_details, '')
        self.assertTrue(test_1_disclaimer.joint_problems)
        self.assertEqual(test_1_disclaimer.joint_problems_details, 'knee problems')
        self.assertFalse(test_1_disclaimer.allergies)
        self.assertEqual(test_1_disclaimer.allergies_details, '')
        self.assertIsNotNone(test_1_disclaimer.medical_treatment_terms)
        self.assertTrue(test_1_disclaimer.medical_treatment_permission)
        self.assertIsNotNone(test_1_disclaimer.disclaimer_terms)
        self.assertTrue(test_1_disclaimer.terms_accepted)
        self.assertIsNotNone(test_1_disclaimer.over_18_statement)
        self.assertTrue(test_1_disclaimer.age_over_18_confirmed)


class EmailDuplicateUsersTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.users_file = os.path.join(
            os.path.dirname(__file__), 'test_data/test_duplicate_users.csv'
        )

    def test_emails_sent(self):
        """
        test data file has:
        user 1: 2 accounts, only one used for booking
        user 2: 2 accounts, both used for booking
        user 3: 3 accounts, 2 used for booking
        user 4: 2 accounts, neither used
        """
        management.call_command('email_duplicate_users', file=self.users_file)
        emails = mail.outbox
        # one email sent per account
        self.assertEqual(len(emails), 4)

        user1_email = emails[0]
        self.assertIn(
            'It looks like you have 2 accounts on the Watermelon Studio '
            'booking system.',
            user1_email.body,
        )
        self.assertIn(
            'I will merge your accounts to the one that you have previously '
            'used for booking',
            user1_email.body,
        )

        user2_email = emails[1]
        self.assertIn(
            'It looks like you have 2 accounts on the Watermelon Studio '
            'booking system.',
            user2_email.body,
        )
        self.assertIn(
            'As more than one of these accounts has been used for booking, '
            'please confirm which one you would like to keep.',
            user2_email.body,
        )

        user3_email = emails[2]
        self.assertIn(
            'It looks like you have 3 accounts on the Watermelon Studio '
            'booking system.',
            user3_email.body,
        )
        self.assertIn(
            'As more than one of these accounts has been used for booking, '
            'please confirm which one you would like to keep.',
            user3_email.body,
        )

        user4_email = emails[3]
        self.assertIn(
            'It looks like you have 2 accounts on the Watermelon Studio '
            'booking system.',
            user4_email.body,
        )
        self.assertIn(
            'I will merge your email addresses to one account.  Please let me '
            'know if you have a preference as to which one is primary',
            user4_email.body,
        )

    @patch('accounts.management.commands.email_duplicate_users.EmailMessage.send')
    @patch('booking.email_helpers.send_mail')
    def test_email_errors(self, mock_send_mail, mock_send_mail1):
        mock_send_mail.side_effect = Exception('Error sending mail')
        mock_send_mail1.side_effect = Exception('Error sending mail')

        management.call_command('email_duplicate_users', file=self.users_file)
        self.assertEqual(len(mail.outbox), 0)


class CreateMailingListTests(TestSetupMixin, TestCase):

    def test_group_created(self):
        self.assertFalse(Group.objects.filter(name='subscribed').exists())
        self.assertFalse(Booking.objects.exists())
        self.assertTrue(User.objects.count(), 3)

        management.call_command('create_mailing_list')
        groups = Group.objects.filter(name='subscribed')
        self.assertEqual(groups.count(), 1)

        self.assertFalse(groups[0].user_set.exists())

    def test_group_and_mailing_list_created(self):
        """
        Add users to mailing list only if they have booked a CL event type
        """
        book_cl_users = mommy.make_recipe(
            'booking.booking', event__event_type__event_type='CL', _quantity=3
        )
        mommy.make_recipe(
            'booking.booking', event__event_type__event_type='EV', _quantity=3
        )
        # group was created on model pre-save when bookings created; delete it
        Group.objects.get(name='subscribed').delete()

        management.call_command('create_mailing_list')
        group = Group.objects.get(name='subscribed')
        self.assertEqual(group.user_set.count(), 3)
        self.assertEqual(
            sorted(user.id for user in group.user_set.all()),
            sorted(booking.user.id for booking in book_cl_users)
        )

    def test_mailing_list_not_created_if_group_exists(self):
        self.assertFalse(Group.objects.filter(name='subscribed').exists())
        management.call_command('create_mailing_list')

        book_cl_users = mommy.make_recipe(
            'booking.booking', event__event_type__event_type='CL', _quantity=3
        )
        mommy.make_recipe(
            'booking.booking', event__event_type__event_type='EV', _quantity=3
        )
        # group is created on model pre-save when bookings created
        self.assertTrue(Group.objects.filter(name='subscribed').exists())
        group = Group.objects.get(name='subscribed')
        self.assertEqual(group.user_set.count(), 3)

        # remove users from mailing list
        for booking in book_cl_users:
            group.user_set.remove(booking.user)

        management.call_command('create_mailing_list')
        self.assertFalse(group.user_set.exists())

        group.user_set.add(book_cl_users[0].user)
        management.call_command('create_mailing_list')
        self.assertEqual(group.user_set.count(), 1)
