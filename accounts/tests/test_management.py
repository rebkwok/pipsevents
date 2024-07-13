import csv
import os

from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

from unittest.mock import Mock, patch
from pathlib import Path

from model_bakery import baker
import pytest

from django.conf import settings
from django.core import management, mail
from django.test import TestCase, override_settings
from django.contrib.auth.models import User, Group
from django.utils import timezone

from accounts.management.commands.import_disclaimer_data import logger as \
    import_disclaimer_data_logger
from accounts.management.commands.export_encrypted_disclaimers import EmailMessage
from accounts.models import ArchivedDisclaimer, DisclaimerContent, NonRegisteredDisclaimer, PrintDisclaimer, OnlineDisclaimer
from activitylog.models import ActivityLog
from booking.models import Booking
from common.tests.helpers import TestSetupMixin, PatchRequestMixin


class DeleteExpiredDisclaimersTests(PatchRequestMixin, TestCase):

    def setUp(self):
        super(DeleteExpiredDisclaimersTests, self).setUp()
        self.user_online_only = baker.make_recipe(
            'booking.user', first_name='Test', last_name='User')
        baker.make(
            OnlineDisclaimer, user=self.user_online_only,
            date=timezone.now()-timedelta(2200)  # > 6 yrs
        )
        self.user_print_only = baker.make_recipe(
            'booking.user', first_name='Test', last_name='User1'
        )
        baker.make(
            PrintDisclaimer, user=self.user_print_only,
            date=timezone.now()-timedelta(2200)  # > 6 yrs
        )
        self.user_both = baker.make_recipe(
            'booking.user', first_name='Test', last_name='User2'
        )
        baker.make(
            OnlineDisclaimer, user=self.user_both,
            date=timezone.now()-timedelta(2200)  # > 6 yrs
        )
        baker.make(
            PrintDisclaimer, user=self.user_both,
            date=timezone.now()-timedelta(2200)  # > 6 yrs
        )

        baker.make(
            NonRegisteredDisclaimer, first_name='Test', last_name='Nonreg',
            date=timezone.now()-timedelta(2200)  # > 6 yrs
        )
        baker.make(
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
        user = baker.make_recipe('booking.user')
        baker.make(OnlineDisclaimer, user=user)
        baker.make(NonRegisteredDisclaimer)
        baker.make(ArchivedDisclaimer)

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
        user = baker.make_recipe('booking.user')
        baker.make(
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
        content = baker.make(DisclaimerContent, version=None)
        baker.make(OnlineDisclaimer, version=content.version, _quantity=10)
        self.log_path = Path(settings.LOG_FOLDER)
        self.disclaimer_types = ["online", "archived", "non_registered"]

    def test_export_disclaimers_creates_default_bu_file(self):
        bu_files = [
            self.log_path / f"{disclaimer_type}_disclaimers_bu.csv" for disclaimer_type in self.disclaimer_types
        ]
        for bu_file in bu_files:
            assert bu_file.exists() is False
        management.call_command('export_disclaimers')
        for bu_file in bu_files:
            assert bu_file.exists() is True
            bu_file.unlink()

    def test_export_disclaimers_writes_correct_number_of_rows(self):
        bu_files = [
            self.log_path / f"{disclaimer_type}_disclaimers_bu.csv" for disclaimer_type in self.disclaimer_types
        ]
        for bu_file in bu_files:
            assert bu_file.exists() is False
        management.call_command('export_disclaimers')

        with open(bu_files[0], 'r') as exported:  # online disclaimers
            reader = csv.reader(exported)
            rows = list(reader)
        self.assertEqual(len(rows), 11)  # 10 records plus header row

        with open(bu_files[1], 'r') as exported:  # archived disclaimers
            reader = csv.reader(exported)
            rows = list(reader)
        self.assertEqual(len(rows), 1)  # 0 records plus header row

        with open(bu_files[2], 'r') as exported:  # non-reg disclaimers
            reader = csv.reader(exported)
            rows = list(reader)
        self.assertEqual(len(rows), 1)  # 0 records plus header row

        for bu_file in bu_files:
            assert bu_file.exists() is True
            bu_file.unlink()

    def test_export_disclaimers_with_filename_argument(self):
        bu_files = [
            self.log_path / f"{disclaimer_type}_test.csv" for disclaimer_type in self.disclaimer_types
        ]
        input_file = self.log_path / "test.csv"

        for bu_file in bu_files:
            assert bu_file.exists() is False
        management.call_command('export_disclaimers', file=input_file)
        for bu_file in bu_files:
            assert bu_file.exists() is True
            bu_file.unlink()


@pytest.mark.serial
@override_settings(LOG_FOLDER=os.path.dirname(__file__))
class ExportEncryptedDisclaimersTests(TestCase):

    def setUp(self):
        content = baker.make(DisclaimerContent, version=None)
        baker.make(OnlineDisclaimer, version=content.version, _quantity=10)

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


from tempfile import NamedTemporaryFile
class ImportDisclaimersTests(TestCase):

    def call_import_disclaimers(self):
        with NamedTemporaryFile() as tf:
            path = Path(tf.name)
            path.write_text(
                "ID,Disclaimer Version,User,Date,Date Updated,Name (as stated on disclaimer),DOB,Address,Postcode,Home Phone,Mobile Phone,Emergency Contact 1: Name,Emergency Contact 1: Relationship,Emergency Contact 1: Phone,Emergency Contact 2: Name,Emergency Contact 2: Relationship,Emergency Contact 2: Phone,Medical Conditions,Medical Conditions Details,Joint Problems,Joint Problems Details,Allergies,Allergies Details,Medical Treatment Terms,Medical Treatment Accepted,Disclaimer Terms,Disclaimer Terms Accepted,Over 18 Statement,Over 18 Confirmed\n"
                "2,2.0,test_1,2015-12-18 15:32:07:191781 +0000,,Test User1,1991-11-21,11 Test Road,TS6 8JT,12345667,2423223423,Test1 Contact1,Partner,8782347239,Test2 Contact1,Father,71684362378,No,,Yes,knee problems,No,,I give permission for myself to receive medical treatment in the event of an accident,Yes,Test terms,Yes,I confirm that I am aged 18 or over,Yes\n"
                "3,3.0,test_2,2015-01-15 15:43:19:747445 +0000,2016-01-06 15:09:16:920219 +0000,Test User2,1987-12-02,42 2f2 New Rd,EH7 5TS,,7647238927,Test1 Contact2,Friend,7283642323,Test2 Contact2,Friend,8783428372,No,,No,,Yes,nuts,I give permission for myself to receive medical treatment in the event of an accident,Yes,Test terms1,Yes,I confirm that I am aged 18 or over,Yes\n"
                "4,3.0,test_3,2016-02-18 16:09:16:920219 +0000,,Test User3,1991-06-20,74 Test St,TS4 4PD,,7894322143,Test1 Contact3,Mother,874283483,Test2 Contact3,Father,87293874923,No,,No,,No,,I give permission for myself to receive medical treatment in the event of an accident,Yes,Test terms1,Yes,I confirm that I am aged 18 or over,Yes\n"
                )
            management.call_command('import_disclaimer_data', file=tf.name)
     
    def test_import_disclaimers_no_matching_users(self):
        import_disclaimer_data_logger.warning = Mock()
        self.assertFalse(OnlineDisclaimer.objects.exists())
        self.call_import_disclaimers()
        self.assertEqual(OnlineDisclaimer.objects.count(), 0)

        self.assertEqual(import_disclaimer_data_logger.warning.call_count, 3)
        self.assertIn(
            "Unknown user test_1 in backup data; data on row 0 not imported",
            str(import_disclaimer_data_logger.warning.call_args_list[0])
        )
        self.assertIn(
            "Unknown user test_2 in backup data; data on row 1 not imported",
            str(import_disclaimer_data_logger.warning.call_args_list[1])
        )
        self.assertIn(
            "Unknown user test_3 in backup data; data on row 2 not imported",
            str(import_disclaimer_data_logger.warning.call_args_list[2])
        )

    def test_import_disclaimers(self):
        for username in ['test_1', 'test_2', 'test_3']:
            baker.make_recipe('booking.user', username=username)
        self.assertFalse(OnlineDisclaimer.objects.exists())
        self.call_import_disclaimers()
        self.assertEqual(OnlineDisclaimer.objects.count(), 3)

    def test_import_disclaimers_existing_data(self):
        import_disclaimer_data_logger.warning = Mock()
        import_disclaimer_data_logger.info = Mock()

        # One DisclaimerContent is already created during migrations
        assert DisclaimerContent.objects.count() == 1

        # if disclaimer already exists for a user, it isn't imported
        for username in ['test_1', 'test_2']:
            baker.make_recipe('booking.user', username=username)
        test_3 = baker.make_recipe('booking.user', username='test_3')
        baker.make(OnlineDisclaimer, user=test_3, name='Donald Duck', version=3.0)

        self.assertEqual(OnlineDisclaimer.objects.count(), 1)
        self.call_import_disclaimers()
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

        # Missing DisclaimerContents matching the disclaimers terms are imported
        assert DisclaimerContent.objects.count() == 3

    def test_import_disclaimers_existing_data_matching_dates(self):
        import_disclaimer_data_logger.warning = Mock()
        import_disclaimer_data_logger.info = Mock()

        # One DisclaimerContent is already created during migrations
        assert DisclaimerContent.objects.count() == 1

        test_1 = baker.make_recipe('booking.user', username='test_1')
        test_2 = baker.make_recipe('booking.user', username='test_2')
        test_3 = baker.make_recipe('booking.user', username='test_3')
        baker.make(
            OnlineDisclaimer, user=test_2,
            date=datetime(2015, 1, 15, 15, 43, 19, 747445, tzinfo=dt_timezone.utc),
            date_updated=datetime(
                2016, 1, 6, 15, 9, 16, 920219, tzinfo=dt_timezone.utc
            ),
            version=3.0
        ),
        baker.make(
            OnlineDisclaimer, user=test_3,
            date=datetime(2016, 2, 18, 16, 9, 16, 920219, tzinfo=dt_timezone.utc),
            version=3.0
        )

        self.assertEqual(OnlineDisclaimer.objects.count(), 2)
        self.call_import_disclaimers()
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

        assert DisclaimerContent.objects.count() == 2

    def test_imported_data_is_correct(self):
        # One DisclaimerContent is already created during migrations
        assert DisclaimerContent.objects.count() == 1

        test_1 = baker.make_recipe('booking.user', username='test_1')
        self.call_import_disclaimers()
        test_1_disclaimer = OnlineDisclaimer.objects.get(user=test_1)

        self.assertEqual(test_1_disclaimer.name, 'Test User1')
        self.assertEqual(
            test_1_disclaimer.date,
            datetime(2015, 12, 18, 15, 32, 7, 191781, tzinfo=dt_timezone.utc)
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
        self.assertTrue(test_1_disclaimer.medical_treatment_permission)
        self.assertTrue(test_1_disclaimer.terms_accepted)
        self.assertTrue(test_1_disclaimer.age_over_18_confirmed)

        assert DisclaimerContent.objects.count() == 2
        new_content = DisclaimerContent.objects.latest("id")
        assert new_content.disclaimer_terms == "Test terms"
        assert new_content.version == 2.0

    def test_import_disclaimer_bad_data(self):
        import_disclaimer_data_logger.warning = Mock()
        baker.make_recipe('booking.user', username='test_1')
        DisclaimerContent.objects.create(
            version="4.5",
            medical_treatment_terms="foo", 
            disclaimer_terms="foo", 
            over_18_statement="foo"
        )
        with NamedTemporaryFile() as tf:
            path = Path(tf.name)
            path.write_text(
                "ID,Disclaimer Version,User,Date,Date Updated,Name (as stated on disclaimer),DOB,Address,Postcode,Home Phone,Mobile Phone,Emergency Contact 1: Name,Emergency Contact 1: Relationship,Emergency Contact 1: Phone,Emergency Contact 2: Name,Emergency Contact 2: Relationship,Emergency Contact 2: Phone,Medical Conditions,Medical Conditions Details,Joint Problems,Joint Problems Details,Allergies,Allergies Details,Medical Treatment Terms,Medical Treatment Accepted,Disclaimer Terms,Disclaimer Terms Accepted,Over 18 Statement,Over 18 Confirmed\n"
                "2,4.5,test_1,2015-12-18 15:32:07:191781 +0000,,Test User1,1991-11-21,11 Test Road,TS6 8JT,12345667,2423223423,Test1 Contact1,Partner,8782347239,Test2 Contact1,Father,71684362378,No,,Yes,knee problems,No,,I give permission for myself to receive medical treatment in the event of an accident,Yes,Test terms,Yes,I confirm that I am aged 18 or over,Yes\n"
            )
            management.call_command('import_disclaimer_data', file=tf.name)
        
        assert import_disclaimer_data_logger.warning.call_count == 1
        assert "Mismatch content" in str(import_disclaimer_data_logger.warning.call_args_list[0])


class EmailDuplicateUsersTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.users_file = os.path.join(
            os.path.dirname(__file__), 'test_data/test_duplicate_users.csv'
        )

    def call_duplicate_users(self):
        with NamedTemporaryFile() as tf:
            path = Path(tf.name)
            path.write_text(
                "Name,Username1,Email 1,Used?,Verified?,Disclaimer?,FB Account?,username2,Email 2,Used?,Verified?,Disclaimer?,FB Account?,Username3,Email3,Used?,Verified?,Disclaimer?,FB Account?\n"
                "Test User1,one_email_used,user1A@test.com,N,N,N,Y,one_email_used1,user1B@test.com,Y,Y,N,N,,,,,,\n"
                "Test User2,two_emails_used,user2A@test.com,Y,Y,N,N,two_emails_used1,user2B@test.com,Y,Y,N,N,,,,,,\n"
                "TestUser3,three_emails,user3A@test.com,Y,Y,Y,N,three_emails1,user3B@test.com,Y,Y,N,N,three_emails2,user3C@test.com,N,Y,N,Y\n"
                "Test User4,two_emails_not_used,user4A@test.com,N,Y,N,N,two_emails_not_used1,user4B@test.com,N,Y,N,N,,,,,,\n"            
            )
            management.call_command('email_duplicate_users', file=tf.name)

    def test_emails_sent(self):
        """
        test data file has:
        user 1: 2 accounts, only one used for booking
        user 2: 2 accounts, both used for booking
        user 3: 3 accounts, 2 used for booking
        user 4: 2 accounts, neither used
        """
        self.call_duplicate_users()
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

        self.call_duplicate_users()
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

        baker.make_recipe('booking.user', email='mailchimptest@test.com')
        baker.make_recipe('booking.user', email='test1@test.com')

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
        user = baker.make_recipe('booking.user', email='mailchimptest@test.com')
        user1 = baker.make_recipe('booking.user', email='test1@test.com')

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
        user1 = baker.make_recipe('booking.user', email='mailchimptest@test.com')
        group.user_set.add(user1)
        # subscribed on site, unsubscribed on mailchimp
        user2 = baker.make_recipe('booking.user', email='mailchimptest1@test.com')
        group.user_set.add(user2)
        # subscribed on mailchimp, unsubscribed on site
        user3 = baker.make_recipe('booking.user', email='mailchimptest2@test.com')

        management.call_command('create_mailing_list', recreate=True)
        group_after = Group.objects.get(name='subscribed')

        # group was recreated
        self.assertNotEqual(group_id, group_after.id)
        self.assertEqual(group_after.user_set.count(), 2)

        susbscribed = group_after.user_set.all()
        self.assertIn(user1, susbscribed)
        self.assertNotIn(user2, susbscribed)
        self.assertIn(user3, susbscribed)
