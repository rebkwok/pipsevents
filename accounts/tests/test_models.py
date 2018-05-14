import pytz

from datetime import date, datetime, timedelta
from decimal import Decimal
from model_mommy import mommy

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import CookiePolicy, DataPrivacyPolicy, SignedDataPrivacy, \
    PrintDisclaimer, OnlineDisclaimer, \
    DISCLAIMER_TERMS, MEDICAL_TREATMENT_TERMS, OVER_18_TERMS
from accounts.utils import has_active_data_privacy_agreement, \
    active_data_privacy_cache_key
from common.tests.helpers import make_data_privacy_agreement


class DisclaimerModelTests(TestCase):

    def test_online_disclaimer_str(self,):
        user = mommy.make_recipe('booking.user', username='testuser')
        disclaimer = mommy.make(OnlineDisclaimer, user=user)
        self.assertEqual(str(disclaimer), 'testuser - {}'.format(
            disclaimer.date.astimezone(
                pytz.timezone('Europe/London')
            ).strftime('%d %b %Y, %H:%M')
        ))

    def test_print_disclaimer_str(self):
        user = mommy.make_recipe('booking.user', username='testuser')
        disclaimer = mommy.make(PrintDisclaimer, user=user)
        self.assertEqual(str(disclaimer), 'testuser - {}'.format(
            disclaimer.date.astimezone(
                pytz.timezone('Europe/London')
            ).strftime('%d %b %Y, %H:%M')
        ))

    def test_default_terms_set_on_new_online_disclaimer(self):
        disclaimer = mommy.make(
            OnlineDisclaimer, disclaimer_terms="foo", over_18_statement="bar",
            medical_treatment_terms="foobar"
        )
        self.assertEqual(disclaimer.disclaimer_terms, DISCLAIMER_TERMS)
        self.assertEqual(disclaimer.medical_treatment_terms, MEDICAL_TREATMENT_TERMS)
        self.assertEqual(disclaimer.over_18_statement, OVER_18_TERMS)

    def test_cannot_update_terms_after_first_save(self):
        disclaimer = mommy.make(OnlineDisclaimer)
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
        user = mommy.make_recipe('booking.user', username='testuser')
        disclaimer = mommy.make(
            OnlineDisclaimer, user=user,
            date=datetime(2015, 2, 10, 19, 0, tzinfo=timezone.utc)
        )

        self.assertFalse(disclaimer.is_active)
        # can make a new disclaimer
        mommy.make(OnlineDisclaimer, user=user)
        # can't make new disclaimer when one is already active
        with self.assertRaises(ValidationError):
            mommy.make(OnlineDisclaimer, user=user)


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
        self.user = mommy.make_recipe('booking.user')

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
