import pytz

from datetime import date, datetime, timedelta
from model_mommy import mommy

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import DataProtectionPolicy, SignedDataProtection, \
    PrintDisclaimer, OnlineDisclaimer, \
    DISCLAIMER_TERMS, MEDICAL_TREATMENT_TERMS, OVER_18_TERMS
from accounts.utils import has_active_data_protection_agreement, \
    active_data_protection_cache_key
from common.tests.helpers import make_dataprotection_agreement


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


class DataProtectionPolicyModelTests(TestCase):

    def test_no_policy_version(self):
        self.assertEqual(DataProtectionPolicy.current_version(), 0)

    def test_policy_versioning(self):
        self.assertEqual(DataProtectionPolicy.current_version(), 0)
        DataProtectionPolicy.objects.create(content='Foo')

        self.assertEqual(DataProtectionPolicy.current_version(), 1)
        DataProtectionPolicy.objects.create(content='Bar')
        self.assertEqual(DataProtectionPolicy.current_version(), 2)

        self.assertEqual(DataProtectionPolicy.current().version, 2)

    def test_policy_str(self):
        dp = DataProtectionPolicy.objects.create(content='Foo')
        self.assertEqual(
            str(dp), 'Version {}'.format(dp.version)
        )


class SignedDataProtectionModelTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        DataProtectionPolicy.objects.create(content='Foo')

    def setUp(self):
        self.user = mommy.make_recipe('booking.user')

    def test_cached_on_save(self):
        make_dataprotection_agreement(self.user)
        self.assertTrue(cache.get(active_data_protection_cache_key(self.user)))

        cache.clear()
        DataProtectionPolicy.objects.create(content='Bar')
        self.assertFalse(has_active_data_protection_agreement(self.user))

    def test_delete(self):
        make_dataprotection_agreement(self.user)
        self.assertTrue(cache.get(active_data_protection_cache_key(self.user)))

        SignedDataProtection.objects.get(user=self.user).delete()
        self.assertIsNone(cache.get(active_data_protection_cache_key(self.user)))


