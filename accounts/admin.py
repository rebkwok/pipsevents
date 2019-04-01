from django.contrib import admin
from django import forms

from ckeditor.widgets import CKEditorWidget

from accounts.models import OnlineDisclaimer, PrintDisclaimer, \
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
        'medical_treatment_terms', 'medical_treatment_permission',
        'disclaimer_terms', 'terms_accepted', 'over_18_statement',
        'age_over_18_confirmed'
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
        'medical_treatment_terms', 'medical_treatment_permission',
        'disclaimer_terms', 'terms_accepted', 'over_18_statement',
        'age_over_18_confirmed'
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


class CookiePolicyAdmin(admin.ModelAdmin):
    readonly_fields = ('issue_date',)
    form = CookiePolicyAdminForm


class DataPrivacyPolicyAdmin(admin.ModelAdmin):
    readonly_fields = ('issue_date',)
    form = DataPrivacyPolicyAdminForm


class SignedDataPrivacyAdmin(admin.ModelAdmin):
    readonly_fields = ('user', 'date_signed', 'version')


admin.site.register(OnlineDisclaimer, OnlineDisclaimerAdmin)
admin.site.register(PrintDisclaimer, PrintDisclaimerAdmin)
admin.site.register(DataPrivacyPolicy, DataPrivacyPolicyAdmin)
admin.site.register(CookiePolicy, CookiePolicyAdmin)
admin.site.register(SignedDataPrivacy, SignedDataPrivacyAdmin)
admin.site.register(NonRegisteredDisclaimer, NonRegisteredDisclaimerAdmin)
