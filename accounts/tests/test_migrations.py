import pytest 

from datetime import datetime, date
from datetime import timezone as dt_timezone

from decimal import Decimal

from django_migration_testcase import MigrationTest


DISCLAIMER_TERMS = """I recognise that I may be asked to participate in some strenuous
exercise during the course and that such participation may present a heightened risk of
injury or ill health. All risks will be fully explained and I do NOT hold The Watermelon
Studio and any of their staff responsible for any harm that may come to me should I decide
to participate in such tasks. I knowingly assume all risks associated with participation,
even if arising from negligence of the participants or others and assume full responsibility
for my participation. I certify that I am in good physical condition can participate in the
courses offered by The Watermelon Studio. I will not participate if pregnant or if I have
given birth within the previous 6 weeks or C-section within the previous 12 weeks and I
will update my teacher on any new medical condition/injury throughout my time at
The Watermelon Studio.  I will not participate under the influence of drugs or alcohol.
Other teachers/instructors may use the information submitted in this form to help keep the
chances of any injury to a minimum. I also hereby agree to follow all rules set out by The
Watermelon Studio. I understand that photographs taken at the studio may be used on the studio's
website and social media pages.  I have read and agree to the terms and conditions on the website."""

DISCLAIMER_TERMS_AT_2020_05_01 = DISCLAIMER_TERMS.replace("\n", " ")

MEDICAL_TREATMENT_TERMS_AT_2020_05_01 = "I give permission for myself to receive medical treatment in the event of an accident"

OVER_18_STATEMENT_AT_2020_05_01 = "I confirm that I am aged 18 or over"


@pytest.mark.skip(reason="Old migration tests")
class DisclaimerVersioningMingrationTests(MigrationTest):

    before = [
        ('accounts', '0012_add_indexes'),
        ('auth', '0011_update_proxy_permissions')
    ]
    after = [
        ('accounts', '0016_remove_disclaimer_content_fields_from_signed_disclaimers'),
        ('auth', '0011_update_proxy_permissions')
    ]
    
    default_disclaimer_data = {
        "dob": date(1990, 1, 1),
        "address":'foo',
        "postcode":  'foo',
        "home_phone":  '1',
        "mobile_phone":  '1',
        "emergency_contact1_name":  'foo',
        "emergency_contact1_relationship":  'foo',
        "emergency_contact1_phone":  'foo',
        "emergency_contact2_name":  'foo',
        "emergency_contact2_relationship":  'foo',
        "emergency_contact2_phone":  'foo',
        "medical_conditions":  False,
        "joint_problems":  False,
        "allergies":  False,
        "medical_treatment_permission":  True,
        "terms_accepted":  True,
        "age_over_18_confirmed":  True,
    }

    def test_migration_versions(self):
        # get pre-migration models
        User = self.get_model_before('auth.User')
        OnlineDisclaimer = self.get_model_before('accounts.OnlineDisclaimer')
        NonRegisteredDisclaimer = self.get_model_before('accounts.NonRegisteredDisclaimer')

        # set up pre-migration data
        user1 = User.objects.create(username='user1', password='user1', email='user1@test.com')
        user2 = User.objects.create(username='user2', password='user2', email='user2@test.com')
        user3 = User.objects.create(username='user3', password='user3', email='user3@test.com')

        date_signed = datetime(2020, 2, 1, tzinfo=dt_timezone.utc)
        # disclaimer with current terms
        OnlineDisclaimer.objects.create(
            user=user1,
            date=date_signed,
            disclaimer_terms=DISCLAIMER_TERMS_AT_2020_05_01,
            medical_treatment_terms=MEDICAL_TREATMENT_TERMS_AT_2020_05_01,
            over_18_statement=OVER_18_STATEMENT_AT_2020_05_01,
            **self.default_disclaimer_data,
        )

        # non-reg disclaimer with older terms
        NonRegisteredDisclaimer.objects.create(
            first_name="test",
            last_name="user",
            email="test@test.com",
            event_date=date(2020, 3, 4),
            date=datetime(2019, 12, 1, tzinfo=dt_timezone.utc),
            disclaimer_terms="foo",
            medical_treatment_terms="foo",
            over_18_statement="foo",
            **self.default_disclaimer_data,
        )

        # 2 disclaimers, one with with the same older terms
        OnlineDisclaimer.objects.create(
            user=user2,
            date=datetime(2019, 12, 28, tzinfo=dt_timezone.utc),
            disclaimer_terms="bar",
            medical_treatment_terms="bar",
            over_18_statement="bar",
            **self.default_disclaimer_data,
        )
        OnlineDisclaimer.objects.create(
            user=user3,
            date=datetime(2019, 12, 15, tzinfo=dt_timezone.utc),
            disclaimer_terms="foo",
            medical_treatment_terms="foo",
            over_18_statement="foo",
            **self.default_disclaimer_data,
        )

        self.run_migration()

        # get post-migration models
        User = self.get_model_after('auth.User')
        OnlineDisclaimer = self.get_model_after('accounts.OnlineDisclaimer')
        NonRegisteredDisclaimer = self.get_model_after('accounts.NonRegisteredDisclaimer')
        DisclaimerContent = self.get_model_after('accounts.DisclaimerContent')

        user1_afer = User.objects.get(id=user1.id)
        user2_afer = User.objects.get(id=user2.id)
        user3_afer = User.objects.get(id=user3.id)

        assert OnlineDisclaimer.objects.count() == 3
        assert NonRegisteredDisclaimer.objects.count() == 1
        disclaimer = OnlineDisclaimer.objects.get(user=user1_afer)
        assert disclaimer.version == 1.0
        assert disclaimer.date == date_signed
        content = DisclaimerContent.objects.get(version=Decimal("1.0"))
        assert content.disclaimer_terms == DISCLAIMER_TERMS_AT_2020_05_01
        assert content.medical_treatment_terms == MEDICAL_TREATMENT_TERMS_AT_2020_05_01
        assert content.over_18_statement == OVER_18_STATEMENT_AT_2020_05_01

        assert DisclaimerContent.objects.count() == 3
        # old versions are created by latest signed date, versioned from 0.1
        content_v0_1 = DisclaimerContent.objects.get(version=Decimal("0.1"))
        assert content_v0_1.disclaimer_terms == "bar"

        # old versions are created by latest signed date, versioned from 0.1
        content_v0_2 = DisclaimerContent.objects.get(version=Decimal("0.2"))
        assert content_v0_2.disclaimer_terms == "foo"

        assert OnlineDisclaimer.objects.get(user=user2_afer).version == Decimal("0.1")
        assert OnlineDisclaimer.objects.get(user=user3_afer).version == Decimal("0.2")
        assert NonRegisteredDisclaimer.objects.first().version == Decimal("0.2")
