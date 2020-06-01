# -*- coding: utf-8 -*-
import pytz

from model_bakery import baker

from django.conf import settings
from django.test import TestCase

from accounts.models import DisclaimerContent
from studioadmin.forms import StudioadminDisclaimerContentForm


class DisclaimerContentFormTests(TestCase):

    def form_data(self):
        return {
            'disclaimer_terms': 'test terms',
            'medical_treatment_terms': 'ok',
            'over_18_statement': 'Indeed I am',
            'version': None,
        }

    def test_form_valid(self):
        form = StudioadminDisclaimerContentForm(data=self.form_data())
        assert form.is_valid()

    def test_form_initial(self):
        baker.make(
            DisclaimerContent,
            disclaimer_terms="Foo", medical_treatment_terms="Bar",
            over_18_statement="Yes", version=None
        )
        # initial is autopopulated with current published content
        form = StudioadminDisclaimerContentForm()
        assert form.fields["disclaimer_terms"].initial == "Foo"
        assert form.fields["medical_treatment_terms"].initial == "Bar"
        assert form.fields["over_18_statement"].initial == "Yes"

    def test_form_initial_no_current_content(self):
        DisclaimerContent.objects.all().delete()
        # initial is autopopulated with current published content
        form = StudioadminDisclaimerContentForm()
        assert form.fields["disclaimer_terms"].initial == None
        assert form.fields["medical_treatment_terms"].initial == None
        assert form.fields["over_18_statement"].initial == None
        assert form.fields["version"].initial == 1.0

    def test_version_must_increment(self):
        baker.make(DisclaimerContent, version=5.0)
        data = self.form_data()
        data["version"] = 4.9
        form = StudioadminDisclaimerContentForm(data=data)
        assert form.is_valid() is False

        data["version"] = 5.1
        form = StudioadminDisclaimerContentForm(data=data)
        assert form.is_valid()

    def test_changes_required(self):
        baker.make(
            DisclaimerContent, **self.form_data()
        )
        # initial is autopopulated with current published content
        form = StudioadminDisclaimerContentForm(data=self.form_data())
        assert form.is_valid() is False
        assert form.errors["__all__"] == [
            "No changes made from previous version; new version must update disclaimer content "
            "(terms, medical terms or age confirmation statement)"
        ]
