from datetime import timedelta
from decimal import Decimal
from math import floor

from django.conf import settings
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django import forms
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import get_template

from ckeditor.widgets import CKEditorWidget

from accounts.models import OnlineDisclaimer, PrintDisclaimer, DisclaimerContent, \
    CookiePolicy, DataPrivacyPolicy, SignedDataPrivacy, NonRegisteredDisclaimer, AccountBan


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
                next_default_version = Decimal(floor((DisclaimerContent.current_version() + 1)))
                self.fields['version'].help_text = f'Current version is {current_content.version}.  Leave ' \
                                           f'blank for next major version ({next_default_version:.1f})'
            else:
                self.fields['version'].initial = 1.0

    def clean_version(self):
        version = self.cleaned_data.get('version')
        current_version = DisclaimerContent.current_version()
        if version is None or version > current_version:
            return version
        self.add_error('version', f'New version must increment current version (must be greater than {current_version})')

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
                      'new version must update disclaimer content (terms, medical terms or age confirmation statement)'
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


class CurrentlyBannedListFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = 'currently banned'

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'currently_banned'

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        return (
            ('currently_banned', 'currently banned'),
            ('previously_banned', 'previously banned'),
        )

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        # Compare the requested value
        # to decide how to filter the queryset.
        if self.value() == 'currently_banned':
            return queryset.filter(end_date__gt=timezone.now())
        if self.value() == 'previously_banned':
            return queryset.filter(end_date__lte=timezone.now())
        return queryset


class CurrentlyBannedUserListFilter(CurrentlyBannedListFilter):
    def lookups(self, request, model_admin):
        return (
            ('currently_banned', 'currently banned'),
            ('not_banned', 'not banned'),
        )

    def queryset(self, request, queryset):
        banned = AccountBan.objects.filter(end_date__gt=timezone.now()).values_list("user", flat=True)
        if self.value() == 'currently_banned':
            return queryset.filter(id__in=banned)
        if self.value() == 'not_banned':
            return queryset.exclude(id__in=banned)
        return queryset


class AccountBanAdmin(admin.ModelAdmin):
    list_display = ("user", "start_date", "end_date", "currently_banned")
    list_filter = (CurrentlyBannedListFilter, 'user')

    def currently_banned(self, obj):
        return obj.user.currently_banned()
    currently_banned.boolean = True


class CustomUserAdmin(UserAdmin):
    actions = ['ban_account']
    list_display = UserAdmin.list_display + ("currently_banned",)
    list_filter = UserAdmin.list_filter + (CurrentlyBannedUserListFilter,)

    def currently_banned(self, obj):
        return obj.currently_banned()
    currently_banned.boolean = True

    def ban_account(self, request, queryset):
        for user in queryset:
            if user.currently_banned():
                self.message_user(
                    request, f"Account for {user.username} is already banned, no updates made", "info"
                )
            else:
                ban, new = AccountBan.objects.get_or_create(user=user)
                if not new:
                    ban.start_date = timezone.now()
                    ban.end_date = timezone.now() + timedelta(days=14)
                    ban.save()

                ctx = {"user": user}
                send_mail(
                    f'{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Account locked',
                    get_template('booking/email/account_blocked.txt').render(ctx),
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    html_message=get_template('booking/email/account_blocked.html').render(ctx),
                    fail_silently=False)

                self.message_user(
                    request,
                    f"Account for {user.username} banned until {user.ban.end_date.strftime('%d %b %Y, %H:%M')} UTC",
                    "success"
                )
    ban_account.short_description = "Ban user accounts for 14 days"


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


admin.site.register(AccountBan, AccountBanAdmin)
admin.site.register(OnlineDisclaimer, OnlineDisclaimerAdmin)
admin.site.register(PrintDisclaimer, PrintDisclaimerAdmin)
admin.site.register(DataPrivacyPolicy, DataPrivacyPolicyAdmin)
admin.site.register(CookiePolicy, CookiePolicyAdmin)
admin.site.register(SignedDataPrivacy, SignedDataPrivacyAdmin)
admin.site.register(NonRegisteredDisclaimer, NonRegisteredDisclaimerAdmin)
admin.site.register(DisclaimerContent, DisclaimerContentAdmin)
