from django.contrib import admin
from django import forms

from ckeditor.widgets import CKEditorWidget

from accounts.models import OnlineDisclaimer, PrintDisclaimer, DisclaimerContent, \
    CookiePolicy, DataPrivacyPolicy, SignedDataPrivacy, NonRegisteredDisclaimer


class OnlineDisclaimerAdmin(admin.ModelAdmin):

    readonly_fields = (
        'user', 'date', 'date_updated', 'name', 'dob', 'address', 'postcode', 'home_phone',
        'mobile_phone', 'emergency_contact1_name',
        'emergency_contact1_relationship', 'emergency_contact1_phone',
        'emergency_contact2_name', 'emergency_contact2_relationship',
        'emergency_contact2_phone', 'medical_conditions',
        'medical_conditions_details', 'joint_problems',
        'joint_problems_details', 'allergies', 'allergies_details',
        'medical_treatment_permission',
        'terms_accepted',
        'age_over_18_confirmed',
        'version'
    )


class PrintDisclaimerAdmin(admin.ModelAdmin):

    readonly_fields = ('user', 'date')


class NonRegisteredDisclaimerAdmin(admin.ModelAdmin):

    readonly_fields = (
        'first_name', 'last_name', 'email', 'date', 'dob', 'address', 'postcode', 'home_phone',
        'mobile_phone', 'emergency_contact1_name',
        'emergency_contact1_relationship', 'emergency_contact1_phone',
        'emergency_contact2_name', 'emergency_contact2_relationship',
        'emergency_contact2_phone', 'medical_conditions',
        'medical_conditions_details', 'joint_problems',
        'joint_problems_details', 'allergies', 'allergies_details',
        'medical_treatment_permission',
        'terms_accepted',
        'age_over_18_confirmed',
        'version'
    )


class PolicyAdminFormMixin(object):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.PolicyModel = self._meta.model
        self.fields['content'].widget = CKEditorWidget()
        self.fields['version'].required = False
        if not self.instance.id:
            current_policy = self.PolicyModel.current()
            if current_policy:
                self.fields['content'].initial = current_policy.content
                self.fields[
                    'version'].help_text = 'Current version is {}.  Leave ' \
                                           'blank for next major ' \
                                           'version'.format(current_policy.version)
            else:
                self.fields['version'].initial = 1.0

    def clean(self):
        new_content = self.cleaned_data.get('content')

        # check content has changed
        current_policy = self.PolicyModel.current()
        if current_policy and current_policy.content == new_content:
            self.add_error(
                None, 'No changes made from previous version; '
                      'new version must update policy content'
            )


class CookiePolicyAdminForm(PolicyAdminFormMixin, forms.ModelForm):

    class Meta:
        model = CookiePolicy
        fields = '__all__'


class DataPrivacyPolicyAdminForm(PolicyAdminFormMixin, forms.ModelForm):

    class Meta:
        model = DataPrivacyPolicy
        fields = '__all__'


class DisclaimerContentAdminForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['version'].required = False
        if not self.instance.id:
            current_content = DisclaimerContent.current()
            if current_content:
                self.fields['disclaimer_terms'].initial = current_content.disclaimer_terms
                self.fields['medical_treatment_terms'].initial = current_content.medical_treatment_terms
                self.fields['over_18_statement'].initial = current_content.over_18_statement
                self.fields['version'].help_text = 'Current version is {}.  Leave ' \
                                           'blank for next major ' \
                                           'version'.format(current_content.version)
            else:
                self.fields['version'].initial = 1.0

    def clean(self):
        new_disclaimer_terms = self.cleaned_data.get('disclaimer_terms')
        new_medical_treatment_terms = self.cleaned_data.get('medical_treatment_terms')
        new_over_18_statement = self.cleaned_data.get('over_18_statement')

        # check content has changed
        current_content = DisclaimerContent.current()
        if (
            current_content and
            current_content.disclaimer_terms == new_disclaimer_terms and
            current_content.medical_treatment_terms == new_medical_treatment_terms and
            current_content.over_18_statement == new_over_18_statement
        ):
            self.add_error(
                None, 'No changes made from previous version; '
                      'new version must update disclaimer content'
            )

    class Meta:
        model = DisclaimerContent
        fields = '__all__'


class CookiePolicyAdmin(admin.ModelAdmin):
    readonly_fields = ('issue_date',)
    form = CookiePolicyAdminForm


class DataPrivacyPolicyAdmin(admin.ModelAdmin):
    readonly_fields = ('issue_date',)
    form = DataPrivacyPolicyAdminForm


class SignedDataPrivacyAdmin(admin.ModelAdmin):
    readonly_fields = ('user', 'date_signed', 'version')


class DisclaimerContentAdmin(admin.ModelAdmin):
    readonly_fields = ('issue_date',)
    form = DisclaimerContentAdminForm


admin.site.register(OnlineDisclaimer, OnlineDisclaimerAdmin)
admin.site.register(PrintDisclaimer, PrintDisclaimerAdmin)
admin.site.register(DataPrivacyPolicy, DataPrivacyPolicyAdmin)
admin.site.register(CookiePolicy, CookiePolicyAdmin)
admin.site.register(SignedDataPrivacy, SignedDataPrivacyAdmin)
admin.site.register(NonRegisteredDisclaimer, NonRegisteredDisclaimerAdmin)
admin.site.register(DisclaimerContent, DisclaimerContentAdmin)
