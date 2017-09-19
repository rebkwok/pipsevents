import pytz

from datetime import date, datetime, timedelta
from model_mommy import mommy

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import PrintDisclaimer, OnlineDisclaimer, \
    DISCLAIMER_TERMS, MEDICAL_TREATMENT_TERMS, OVER_18_TERMS


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
