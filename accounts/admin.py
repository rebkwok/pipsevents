from django.contrib import admin
from django import forms

from ckeditor.widgets import CKEditorWidget

from accounts.models import OnlineDisclaimer, PrintDisclaimer, \
    DataProtectionPolicy, SignedDataProtection


class OnlineDisclaimerAdmin(admin.ModelAdmin):

    readonly_fields = (
        'user', 'date', 'name', 'dob', 'address', 'postcode', 'home_phone',
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


class DataProtectionPolicyAdminForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(DataProtectionPolicyAdminForm, self).__init__(*args, **kwargs)
        self.fields['content'].widget = forms.Textarea()
        if not self.instance.id:
            current_dp = DataProtectionPolicy.current()
            if current_dp:
                self.fields['content'].initial = current_dp.content

    class Meta:
        model = DataProtectionPolicy
        fields = '__all__'


class DataProtectionPolicyAdmin(admin.ModelAdmin):
    readonly_fields = ('version',)
    form = DataProtectionPolicyAdminForm


class SignedDataProtectionAdmin(admin.ModelAdmin):
    readonly_fields = ('user', 'date_signed', 'content_version')


admin.site.register(OnlineDisclaimer, OnlineDisclaimerAdmin)
admin.site.register(PrintDisclaimer, PrintDisclaimerAdmin)
admin.site.register(DataProtectionPolicy, DataProtectionPolicyAdmin)
admin.site.register(SignedDataProtection, SignedDataProtectionAdmin)
