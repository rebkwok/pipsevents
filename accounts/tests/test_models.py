import pytz
import pytest

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from decimal import Decimal
from model_bakery import baker

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import AccountBan, CookiePolicy, DataPrivacyPolicy, DisclaimerContent, SignedDataPrivacy, \
    PrintDisclaimer, OnlineDisclaimer, NonRegisteredDisclaimer, ArchivedDisclaimer, has_active_data_privacy_agreement, \
    active_data_privacy_cache_key
from common.tests.helpers import make_data_privacy_agreement


class DisclaimerContentModelTests(TestCase):

    def test_disclaimer_content_first_version(self):
        DisclaimerContent.objects.all().delete()
        assert DisclaimerContent.objects.exists() is False
        assert DisclaimerContent.current_version() == 0

        content = baker.make(DisclaimerContent, version=None)
        assert content.version == 1.0

        content1 = baker.make(DisclaimerContent, version=None)
        assert content1.version == 2.0

    def test_can_edit_draft_disclaimer_content(self):
        content = baker.make(DisclaimerContent, disclaimer_terms="first version", version=4, is_draft=True)
        first_issue_date = content.issue_date

        content.disclaimer_terms = "second version"
        content.save()
        assert first_issue_date < content.issue_date

        assert content.disclaimer_terms == "second version"
        content.is_draft = False
        content.save()

        with pytest.raises(ValueError):
            content.disclaimer_terms = "third version"
            content.save()

    def test_can_update_and_make_draft_published(self):
        content = baker.make(DisclaimerContent, disclaimer_terms="first version", version=4, is_draft=True)
        first_issue_date = content.issue_date

        content.disclaimer_terms = "second version"
        content.is_draft = False
        content.save()
        assert first_issue_date < content.issue_date

        with self.assertRaises(ValueError):
            content.disclaimer_terms = "third version"
            content.save()

    def test_cannot_change_existing_published_disclaimer_version(self):
        content = baker.make(DisclaimerContent, disclaimer_terms="first version", version=4, is_draft=True)
        content.version = 3.8
        content.save()

        assert content.version == 3.8
        content.is_draft = False
        content.save()

        with pytest.raises(ValueError):
            content.version = 4
            content.save()

    def test_cannot_update_terms_after_first_save(self):
        disclaimer_content = baker.make(
            DisclaimerContent,
            disclaimer_terms="foo", over_18_statement="bar", medical_treatment_terms="foobar",
            version=None  # ensure version is incremented from any existing ones
        )

        with self.assertRaises(ValueError):
            disclaimer_content.disclaimer_terms = 'foo1'
            disclaimer_content.save()

        with self.assertRaises(ValueError):
            disclaimer_content.medical_treatment_terms = 'foo1'
            disclaimer_content.save()

        with self.assertRaises(ValueError):
            disclaimer_content.over_18_statement = 'foo1'
            disclaimer_content.save()

    def test_status(self):
        disclaimer_content = baker.make(DisclaimerContent, version=None)
        assert disclaimer_content.status == "published"
        disclaimer_content_draft = baker.make(DisclaimerContent, version=None, is_draft=True)
        assert disclaimer_content_draft.status == "draft"

    def test_str(self):
        disclaimer_content = baker.make(DisclaimerContent, version=None)
        assert str(disclaimer_content) == f'Disclaimer Content - Version {disclaimer_content.version} (published)'

    def test_new_version_must_have_new_terms(self):
        baker.make(
            DisclaimerContent,
            disclaimer_terms="foo", over_18_statement="bar", medical_treatment_terms="foobar",
            version=None
        )
        with pytest.raises(ValidationError) as e:
            baker.make(
                DisclaimerContent,
                disclaimer_terms="foo", over_18_statement="bar", medical_treatment_terms="foobar",
                version=None
            )
            assert str(e) == "No changes made to content; not saved"


class DisclaimerModelTests(TestCase):

    def test_online_disclaimer_str(self,):
        user = baker.make_recipe('booking.user', username='testuser')
        content = baker.make(DisclaimerContent, version=5.0)
        disclaimer = baker.make(OnlineDisclaimer, user=user, version=content.version)
        self.assertEqual(str(disclaimer), 'testuser - V5.0 - {}'.format(
            disclaimer.date.astimezone(
                pytz.timezone('Europe/London')
            ).strftime('%d %b %Y, %H:%M')
        ))

    def test_print_disclaimer_str(self):
        user = baker.make_recipe('booking.user', username='testuser')
        disclaimer = baker.make(PrintDisclaimer, user=user)
        self.assertEqual(str(disclaimer), 'testuser - {}'.format(
            disclaimer.date.astimezone(
                pytz.timezone('Europe/London')
            ).strftime('%d %b %Y, %H:%M')
        ))

    def test_nonregistered_disclaimer_str(self):
        content = baker.make(DisclaimerContent, version=5.0)
        disclaimer = baker.make(
            NonRegisteredDisclaimer, first_name='Test', last_name='User',
            event_date=datetime(2019, 1, 1, tzinfo=dt_timezone.utc), version=content.version
        )
        self.assertEqual(str(disclaimer), 'Test User - V5.0 - {}'.format(
            disclaimer.date.astimezone(
                pytz.timezone('Europe/London')
            ).strftime('%d %b %Y, %H:%M')
        ))

    def test_archived_disclaimer_str(self):
        content = baker.make(DisclaimerContent, version=5.0)
        disclaimer = baker.make(
            ArchivedDisclaimer, name='Test User',
            date=datetime(2019, 1, 1, tzinfo=dt_timezone.utc),
            date_archived=datetime(2019, 1, 20, tzinfo=dt_timezone.utc),
            version=content.version
        )
        self.assertEqual(str(disclaimer), 'Test User - V5.0 - {} (archived {})'.format(
            disclaimer.date.astimezone(pytz.timezone('Europe/London')).strftime('%d %b %Y, %H:%M'),
            disclaimer.date_archived.astimezone(pytz.timezone('Europe/London')).strftime('%d %b %Y, %H:%M')
        ))

    def test_new_online_disclaimer_with_current_version_is_active(self):
        disclaimer_content = baker.make(
            DisclaimerContent,
            disclaimer_terms="foo", over_18_statement="bar", medical_treatment_terms="foobar",
            version=None  # ensure version is incremented from any existing ones
        )
        disclaimer = baker.make(OnlineDisclaimer, version=disclaimer_content.version)

        assert disclaimer.is_active
        baker.make(
            DisclaimerContent,
            disclaimer_terms="foo1", over_18_statement="bar", medical_treatment_terms="foobar",
            version=None  # ensure version is incremented from any existing ones
        )
        assert disclaimer.is_active is False

    def test_cannot_create_new_active_disclaimer(self):
        user = baker.make_recipe('booking.user', username='testuser')
        disclaimer_content = baker.make(
            DisclaimerContent,
            disclaimer_terms="foo", over_18_statement="bar", medical_treatment_terms="foobar",
            version=None  # ensure version is incremented from any existing ones
        )
        # disclaimer is out of date, so inactive
        disclaimer = baker.make(
            OnlineDisclaimer, user=user,
            date=datetime(2015, 2, 10, 19, 0, tzinfo=dt_timezone.utc), version=disclaimer_content.version
        )

        self.assertFalse(disclaimer.is_active)
        # can make a new disclaimer
        baker.make(OnlineDisclaimer, user=user, version=disclaimer_content.version)
        # can't make new disclaimer when one is already active
        with self.assertRaises(ValidationError):
            baker.make(OnlineDisclaimer, user=user, version=disclaimer_content.version)

    def test_delete_online_disclaimer(self):
        self.assertFalse(ArchivedDisclaimer.objects.exists())
        disclaimer = baker.make(OnlineDisclaimer, name='Test 1')
        disclaimer.delete()

        self.assertTrue(ArchivedDisclaimer.objects.exists())
        archived = ArchivedDisclaimer.objects.first()
        self.assertEqual(archived.name, disclaimer.name)
        self.assertEqual(archived.date, disclaimer.date)

    def test_delete_online_disclaimer_older_than_6_yrs(self):
        self.assertFalse(ArchivedDisclaimer.objects.exists())
        # disclaimer created > 6yrs ago
        disclaimer = baker.make(
            OnlineDisclaimer, name='Test 1', date=timezone.now() - timedelta(2200))
        disclaimer.delete()
        # no archive created
        self.assertFalse(ArchivedDisclaimer.objects.exists())

        # disclaimer created > 6yrs ago, update < 6yrs ago
        disclaimer = baker.make(
            OnlineDisclaimer, name='Test 1',
            date=timezone.now() - timedelta(2200),
            date_updated=timezone.now() - timedelta(1000)
        )
        disclaimer.delete()
        # no archive created
        self.assertTrue(ArchivedDisclaimer.objects.exists())

    def test_nonregistered_disclaimer_is_active(self):
        disclaimer_content = baker.make(
            DisclaimerContent, version=None  # ensure version is incremented from any existing ones
        )
        disclaimer = baker.make(
            NonRegisteredDisclaimer, first_name='Test', last_name='User', version=disclaimer_content.version
        )
        self.assertTrue(disclaimer.is_active)

        old_disclaimer = baker.make(
            NonRegisteredDisclaimer, first_name='Test', last_name='User', version=disclaimer_content.version,
            date=timezone.now() - timedelta(367),
        )
        self.assertFalse(old_disclaimer.is_active)

    def test_delete_nonregistered_disclaimer(self):
        self.assertFalse(ArchivedDisclaimer.objects.exists())
        disclaimer = baker.make(NonRegisteredDisclaimer, first_name='Test', last_name='User')
        disclaimer.delete()

        self.assertTrue(ArchivedDisclaimer.objects.exists())
        archived = ArchivedDisclaimer.objects.first()
        self.assertEqual(archived.name, '{} {}'.format(disclaimer.first_name, disclaimer.last_name))
        self.assertEqual(archived.date, disclaimer.date)

    def test_delete_nonregistered_disclaimer_older_than_6_yrs(self):
        self.assertFalse(ArchivedDisclaimer.objects.exists())
        # disclaimer created > 6yrs ago
        disclaimer = baker.make(
            NonRegisteredDisclaimer, first_name='Test', last_name='User', date=timezone.now() - timedelta(2200))
        disclaimer.delete()
        # no archive created
        self.assertFalse(ArchivedDisclaimer.objects.exists())


class DataPrivacyPolicyModelTests(TestCase):

    def test_no_policy_version(self):
        self.assertEqual(DataPrivacyPolicy.current_version(), 0)

    def test_policy_versioning(self):
        self.assertEqual(DataPrivacyPolicy.current_version(), 0)

        DataPrivacyPolicy.objects.create(content='Foo')
        self.assertEqual(DataPrivacyPolicy.current_version(), Decimal('1.0'))

        DataPrivacyPolicy.objects.create(content='Foo1')
        self.assertEqual(DataPrivacyPolicy.current_version(), Decimal('2.0'))

        DataPrivacyPolicy.objects.create(content='Foo2', version=Decimal('2.6'))
        self.assertEqual(DataPrivacyPolicy.current_version(), Decimal('2.6'))

        DataPrivacyPolicy.objects.create(content='Foo3')
        self.assertEqual(DataPrivacyPolicy.current_version(), Decimal('3.0'))

    def test_cannot_make_new_version_with_same_content(self):
        DataPrivacyPolicy.objects.create(content='Foo')
        self.assertEqual(DataPrivacyPolicy.current_version(), Decimal('1.0'))
        with self.assertRaises(ValidationError):
            DataPrivacyPolicy.objects.create(content='Foo')

    def test_policy_str(self):
        dp = DataPrivacyPolicy.objects.create(content='Foo')
        self.assertEqual(
            str(dp), 'Data Privacy Policy - Version {}'.format(dp.version)
        )


class CookiePolicyModelTests(TestCase):

    def test_policy_versioning(self):
        CookiePolicy.objects.create(content='Foo')
        self.assertEqual(CookiePolicy.current().version, Decimal('1.0'))

        CookiePolicy.objects.create(content='Foo1')
        self.assertEqual(CookiePolicy.current().version, Decimal('2.0'))

        CookiePolicy.objects.create(content='Foo2', version=Decimal('2.6'))
        self.assertEqual(CookiePolicy.current().version, Decimal('2.6'))

        CookiePolicy.objects.create(content='Foo3')
        self.assertEqual(CookiePolicy.current().version, Decimal('3.0'))

    def test_cannot_make_new_version_with_same_content(self):
        CookiePolicy.objects.create(content='Foo')
        self.assertEqual(CookiePolicy.current().version, Decimal('1.0'))
        with self.assertRaises(ValidationError):
            CookiePolicy.objects.create(content='Foo')

    def test_policy_str(self):
        dp = CookiePolicy.objects.create(content='Foo')
        self.assertEqual(
            str(dp), 'Cookie Policy - Version {}'.format(dp.version)
        )


class SignedDataPrivacyModelTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        DataPrivacyPolicy.objects.create(content='Foo')

    def setUp(self):
        self.user = baker.make_recipe('booking.user')

    @pytest.mark.skip("expected fail due to cache")
    def test_cache_deleted_on_save(self):
        make_data_privacy_agreement(self.user)
        assert cache.get(active_data_privacy_cache_key(self.user)) is None
        # re-cache
        assert has_active_data_privacy_agreement(self.user)
        assert cache.get(active_data_privacy_cache_key(self.user)) is True

        DataPrivacyPolicy.objects.create(content='New Foo')
        assert not has_active_data_privacy_agreement(self.user)

    def test_delete(self):
        make_data_privacy_agreement(self.user)
        assert cache.get(active_data_privacy_cache_key(self.user)) is None

        SignedDataPrivacy.objects.get(user=self.user).delete()
        self.assertIsNone(cache.get(active_data_privacy_cache_key(self.user)))


class AccountBanModelTests(TestCase):

    def test_account_ban_default_expiry(self,):
        user = baker.make_recipe('booking.user', username='testuser')
        ban = AccountBan.objects.create(user=user)
        assert ban.end_date.date() == (timezone.now() + timedelta(14)).date()

    def test_account_ban_str(self):
        user = baker.make_recipe('booking.user', username='testuser')
        ban = baker.make(AccountBan, user=user, end_date=datetime(2021, 7, 1, 10,0))
        assert str(ban) == f"testuser - 01 Jul 2021, 10:00"

    def test_currently_banned(self):
        user = baker.make_recipe('booking.user', username='testuser')
        ban = AccountBan.objects.create(user=user)
        user.refresh_from_db()
        assert user.currently_banned() is True

        ban.end_date = timezone.now() - timedelta(1)
        ban.save()
        user.refresh_from_db()
        assert user.currently_banned() is False


@pytest.mark.django_db
def test_userprofile_str():
    user = baker.make_recipe('booking.user', username='testuser')
    # userprofile created for new user
    assert str(user.userprofile) == "testuser"
