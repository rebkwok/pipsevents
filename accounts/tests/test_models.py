import pytz

from datetime import date, datetime, timedelta
from decimal import Decimal
from model_bakery import baker

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import CookiePolicy, DataPrivacyPolicy, SignedDataPrivacy, \
    PrintDisclaimer, OnlineDisclaimer, NonRegisteredDisclaimer, ArchivedDisclaimer, \
    DISCLAIMER_TERMS, MEDICAL_TREATMENT_TERMS, OVER_18_TERMS
from accounts.utils import has_active_data_privacy_agreement, \
    active_data_privacy_cache_key
from common.tests.helpers import make_data_privacy_agreement


class DisclaimerModelTests(TestCase):

    def test_online_disclaimer_str(self,):
        user = baker.make_recipe('booking.user', username='testuser')
        disclaimer = baker.make(OnlineDisclaimer, user=user)
        self.assertEqual(str(disclaimer), 'testuser - {}'.format(
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
        disclaimer = baker.make(
            NonRegisteredDisclaimer, first_name='Test', last_name='User',
            event_date=datetime(2019, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(str(disclaimer), 'Test User - {}'.format(
            disclaimer.date.astimezone(
                pytz.timezone('Europe/London')
            ).strftime('%d %b %Y, %H:%M')
        ))

    def test_archived_disclaimer_str(self):
        disclaimer = baker.make(
            ArchivedDisclaimer, name='Test User',
            date=datetime(2019, 1, 1, tzinfo=timezone.utc),
            date_archived=datetime(2019, 1, 20, tzinfo=timezone.utc)
        )
        self.assertEqual(str(disclaimer), 'Test User - {} (archived {})'.format(
            disclaimer.date.astimezone(pytz.timezone('Europe/London')).strftime('%d %b %Y, %H:%M'),
            disclaimer.date_archived.astimezone(pytz.timezone('Europe/London')).strftime('%d %b %Y, %H:%M')
        ))

    def test_default_terms_set_on_new_online_disclaimer(self):
        disclaimer = baker.make(
            OnlineDisclaimer, disclaimer_terms="foo", over_18_statement="bar",
            medical_treatment_terms="foobar"
        )
        self.assertEqual(disclaimer.disclaimer_terms, DISCLAIMER_TERMS)
        self.assertEqual(disclaimer.medical_treatment_terms, MEDICAL_TREATMENT_TERMS)
        self.assertEqual(disclaimer.over_18_statement, OVER_18_TERMS)

    def test_cannot_update_terms_after_first_save(self):
        disclaimer = baker.make(OnlineDisclaimer)
        self.assertEqual(disclaimer.disclaimer_terms, DISCLAIMER_TERMS)
        self.assertEqual(disclaimer.medical_treatment_terms, MEDICAL_TREATMENT_TERMS)
        self.assertEqual(disclaimer.over_18_statement, OVER_18_TERMS)

        with self.assertRaises(ValueError):
            disclaimer.disclaimer_terms = 'foo'
            disclaimer.save()

        with self.assertRaises(ValueError):
            disclaimer.medical_treatment_terms = 'foo'
            disclaimer.save()

        with self.assertRaises(ValueError):
            disclaimer.over_18_statement = 'foo'
            disclaimer.save()

    def test_cannot_create_new_active_disclaimer(self):
        user = baker.make_recipe('booking.user', username='testuser')
        disclaimer = baker.make(
            OnlineDisclaimer, user=user,
            date=datetime(2015, 2, 10, 19, 0, tzinfo=timezone.utc)
        )

        self.assertFalse(disclaimer.is_active)
        # can make a new disclaimer
        baker.make(OnlineDisclaimer, user=user)
        # can't make new disclaimer when one is already active
        with self.assertRaises(ValidationError):
            baker.make(OnlineDisclaimer, user=user)

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
        disclaimer = baker.make(NonRegisteredDisclaimer, first_name='Test', last_name='User')
        self.assertTrue(disclaimer.is_active)

        old_disclaimer = baker.make(
            NonRegisteredDisclaimer, first_name='Test', last_name='User',
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

    def test_cached_on_save(self):
        make_data_privacy_agreement(self.user)
        self.assertTrue(cache.get(active_data_privacy_cache_key(self.user)))

        DataPrivacyPolicy.objects.create(content='New Foo')
        self.assertFalse(has_active_data_privacy_agreement(self.user))

    def test_delete(self):
        make_data_privacy_agreement(self.user)
        self.assertTrue(cache.get(active_data_privacy_cache_key(self.user)))

        SignedDataPrivacy.objects.get(user=self.user).delete()
        self.assertIsNone(cache.get(active_data_privacy_cache_key(self.user)))
