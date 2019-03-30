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
from accounts.models import ArchivedDisclaimer, NonRegisteredDisclaimer, PrintDisclaimer, OnlineDisclaimer
from activitylog.models import ActivityLog
from booking.models import Booking
from common.tests.helpers import TestSetupMixin, PatchRequestMixin


class DeleteExpiredDisclaimersTests(PatchRequestMixin, TestCase):

    def setUp(self):
        super(DeleteExpiredDisclaimersTests, self).setUp()
        self.user_online_only = mommy.make_recipe(
            'booking.user', first_name='Test', last_name='User')
        mommy.make(
            OnlineDisclaimer, user=self.user_online_only,
            date=timezone.now()-timedelta(2200)  # > 6 yrs
        )
        self.user_print_only = mommy.make_recipe(
            'booking.user', first_name='Test', last_name='User1'
        )
        mommy.make(
            PrintDisclaimer, user=self.user_print_only,
            date=timezone.now()-timedelta(2200)  # > 6 yrs
        )
        self.user_both = mommy.make_recipe(
            'booking.user', first_name='Test', last_name='User2'
        )
        mommy.make(
            OnlineDisclaimer, user=self.user_both,
            date=timezone.now()-timedelta(2200)  # > 6 yrs
        )
        mommy.make(
            PrintDisclaimer, user=self.user_both,
            date=timezone.now()-timedelta(2200)  # > 6 yrs
        )

        mommy.make(
            NonRegisteredDisclaimer, first_name='Test', last_name='Nonreg',
            date=timezone.now()-timedelta(2200)  # > 6 yrs
        )
        mommy.make(
            ArchivedDisclaimer, name='Test Archived',
            date=timezone.now()-timedelta(2200)  # > 6 yrs
        )

    def test_disclaimers_deleted_if_more_than_6_years_old(self):
        self.assertEqual(OnlineDisclaimer.objects.count(), 2)
        self.assertEqual(PrintDisclaimer.objects.count(), 2)

        management.call_command('delete_expired_disclaimers')
        self.assertEqual(OnlineDisclaimer.objects.count(), 0)
        self.assertEqual(PrintDisclaimer.objects.count(), 0)

        activitylogs = ActivityLog.objects.values_list('log', flat=True)
        print_users = [
            '{} {}'.format(user.first_name, user.last_name)
            for user in [self.user_print_only, self.user_both]
        ]

        self.assertIn(
            'Print disclaimers more than 6 yrs old deleted for users: {}'.format(
                ', '.join(print_users)
            ),
            activitylogs
        )

        online_users = [
            '{} {}'.format(user.first_name, user.last_name)
            for user in [self.user_online_only, self.user_both]
        ]

        self.assertIn(
            'Online disclaimers more than 6 yrs old deleted for users: {}'.format(
                ', '.join(online_users)
            ),
            activitylogs
        )

        self.assertIn(
            'Non-registered disclaimers more than 6 yrs old deleted for users: Test Nonreg',
            activitylogs
        )

        self.assertIn(
            'Archived disclaimers more than 6 yrs old deleted for users: Test Archived',
            activitylogs
        )

    def test_disclaimers_not_deleted_if_created_in_past_6_years(self):
        # make a user with a disclaimer created today
        user = mommy.make_recipe('booking.user')
        mommy.make(OnlineDisclaimer, user=user)
        mommy.make(NonRegisteredDisclaimer)
        mommy.make(ArchivedDisclaimer)

        self.assertEqual(OnlineDisclaimer.objects.count(), 3)
        self.assertEqual(NonRegisteredDisclaimer.objects.count(), 2)
        self.assertEqual(ArchivedDisclaimer.objects.count(), 2)
        self.assertEqual(PrintDisclaimer.objects.count(), 2)

        # disclaimer should not be deleted because it was created < 3 yrs ago.
        # All others will be.
        management.call_command('delete_expired_disclaimers')
        self.assertEqual(OnlineDisclaimer.objects.count(), 1)
        self.assertEqual(PrintDisclaimer.objects.count(), 0)

    def test_disclaimers_not_deleted_if_updated_in_past_6_years(self):
        # make a user with a disclaimer created > yr ago but updated in past yr
        user = mommy.make_recipe('booking.user')
        mommy.make(
            OnlineDisclaimer, user=user, date=timezone.now() - timedelta(2200),
            date_updated=timezone.now() - timedelta(2000),
        )
        self.assertEqual(OnlineDisclaimer.objects.count(), 3)
        self.assertEqual(PrintDisclaimer.objects.count(), 2)

        management.call_command('delete_expired_disclaimers')
        self.assertEqual(OnlineDisclaimer.objects.count(), 1)
        self.assertEqual(PrintDisclaimer.objects.count(), 0)

    def test_no_disclaimers_to_delete(self):
        for disclaimer_list in [
            OnlineDisclaimer.objects.all(), PrintDisclaimer.objects.all(),
            ArchivedDisclaimer.objects.all(), NonRegisteredDisclaimer.objects.all()
        ]:
            for disclaimer in disclaimer_list:
                if hasattr(disclaimer, 'date_updated'):
                    disclaimer.date_updated = timezone.now() - timedelta(600)
                    disclaimer.save()
                else:
                    disclaimer.delete()

        management.call_command('delete_expired_disclaimers')
        self.assertEqual(OnlineDisclaimer.objects.count(), 2)
        self.assertEqual(PrintDisclaimer.objects.count(), 0)
        self.assertEqual(ArchivedDisclaimer.objects.count(), 1)
        self.assertEqual(NonRegisteredDisclaimer.objects.count(), 0)


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

    @patch('mailchimp3.entities.listmembers.ListMembers.all')
    def test_group_created(self, mock_listmembers):

        self.assertFalse(Group.objects.filter(name='subscribed').exists())
        self.assertFalse(Booking.objects.exists())
        self.assertTrue(User.objects.count(), 3)

        management.call_command('create_mailing_list')
        groups = Group.objects.filter(name='subscribed')
        self.assertEqual(groups.count(), 1)

        # no users on mailing list from mailchimp, so none added to group
        self.assertFalse(groups[0].user_set.exists())

    @patch('mailchimp3.entities.listmembers.ListMembers.all')
    def test_group_and_mailing_list_created(self, mock_listmembers):
        """
        Add users to mailing list only if they are on mailchimp
        """
        mock_listmembers.return_value = {
            'members': [
                {'status': 'subscribed', 'email_address': 'mailchimptest@test.com'}
            ]
        }

        mommy.make_recipe('booking.user', email='mailchimptest@test.com')
        mommy.make_recipe('booking.user', email='test1@test.com')

        management.call_command('create_mailing_list')
        group = Group.objects.get(name='subscribed')
        self.assertEqual(group.user_set.count(), 1)

    @patch('mailchimp3.entities.listmembers.ListMembers.all')
    def test_mailing_list_not_created_if_group_exists(self, mock_listmembers):
        mock_listmembers.return_value = {
            'members': [
                {'status': 'subscribed',
                 'email_address': 'mailchimptest@test.com'}
            ]
        }
        user = mommy.make_recipe('booking.user', email='mailchimptest@test.com')
        user1 = mommy.make_recipe('booking.user', email='test1@test.com')

        self.assertFalse(Group.objects.filter(name='subscribed').exists())
        group = Group.objects.create(name='subscribed')
        group.user_set.add(user1)

        management.call_command('create_mailing_list')
        group.refresh_from_db()

        self.assertEqual(group.user_set.count(), 1)
        susbscribed = group.user_set.all()
        self.assertNotIn(user, susbscribed)
        self.assertIn(user1, susbscribed)

    @patch('mailchimp3.entities.listmembers.ListMembers.all')
    def test_force_recreate_mailing_list(self, mock_listmembers):
        mock_listmembers.return_value = {
            'members': [
                {'status': 'subscribed', 'email_address': 'mailchimptest@test.com'},
                {'status': 'unsubscribed', 'email_address': 'mailchimptest1@test.com'},
                {'status': 'subscribed', 'email_address': 'mailchimptest2@test.com'},
                {'status': 'subscribed', 'email_address': 'doesnotexist@test.com'}
            ]
        }

        self.assertFalse(Group.objects.filter(name='subscribed').exists())
        group = Group.objects.create(name='subscribed')
        group_id = group.id
        # subscribed on both
        user1 = mommy.make_recipe('booking.user', email='mailchimptest@test.com')
        group.user_set.add(user1)
        # subscribed on site, unsubscribed on mailchimp
        user2 = mommy.make_recipe('booking.user', email='mailchimptest1@test.com')
        group.user_set.add(user2)
        # subscribed on mailchimp, unsubscribed on site
        user3 = mommy.make_recipe('booking.user', email='mailchimptest2@test.com')

        management.call_command('create_mailing_list', recreate=True)
        group_after = Group.objects.get(name='subscribed')

        # group was recreated
        self.assertNotEqual(group_id, group_after.id)
        self.assertEqual(group_after.user_set.count(), 2)

        susbscribed = group_after.user_set.all()
        self.assertIn(user1, susbscribed)
        self.assertNotIn(user2, susbscribed)
        self.assertIn(user3, susbscribed)
