# -*- coding: utf-8 -*-
import logging
import pytz
import uuid

from datetime import timedelta

from math import floor

from dateutil.relativedelta import relativedelta

from django.db import models
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.utils import timezone

from accounts.utils import active_disclaimer_cache_key, \
    active_print_disclaimer_cache_key, active_online_disclaimer_cache_key, \
    active_data_privacy_cache_key, expired_disclaimer_cache_key
from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


# Decorator for django models that contain readonly fields.
def has_readonly_fields(original_class):
    def store_read_only_fields(sender, instance, **kwargs):
        if not instance.id:
            return
        for field_name in sender.read_only_fields:
            val = getattr(instance, field_name)
            setattr(instance, field_name + "_oldval", val)

    def check_read_only_fields(sender, instance, **kwargs):
        if not instance.id:
            return
        for field_name in sender.read_only_fields:
            old_value = getattr(instance, field_name + "_oldval")
            new_value = getattr(instance, field_name)
            if old_value != new_value:
                raise ValueError("Field %s is read only." % field_name)

    models.signals.post_init.connect(
        store_read_only_fields, original_class, weak=False) # for load
    models.signals.post_save.connect(
        store_read_only_fields, original_class, weak=False) # for save
    models.signals.pre_save.connect(
        check_read_only_fields, original_class, weak=False)
    return original_class


DISCLAIMER_TERMS = "I recognise that I may be asked to participate in some " \
                   "strenuous exercise during the course and that such " \
                   "participation may present a heightened risk of injury or " \
                   "ill health. All risks will be fully explained and I do " \
                   "NOT hold The Watermelon Studio and any of their staff " \
                   "responsible for any harm that may come to me should I " \
                   "decide to participate in such tasks. I knowingly assume " \
                   "all risks associated with participation, even if arising " \
                   "from negligence of the participants or others and assume " \
                   "full responsibility for my participation. I certify that " \
                   "I am in good physical condition can participate in the " \
                   "courses offered by The Watermelon Studio. I will not " \
                   "participate if pregnant or if I have given birth within " \
                   "the previous 12 weeks 6 weeks or C-section in 12 weeks " \
                   "and I will update my teacher on " \
                   "any new medical condition/injury throughout my time at " \
                   "The Watermelon Studio.  I will not participate under the " \
                   "influence of drugs or alcohol. Other teachers/instructors " \
                   "may use the information submitted in this form to help " \
                   "keep the chances of any injury to a minimum. I also " \
                   "hereby agree to follow all rules set out by The " \
                   "Watermelon Studio. I understand that photographs taken " \
                   "at the studio may be used on the studio's website and " \
                   "social media pages.  I have read and agree to the terms " \
                   "and conditions on the website."

OVER_18_TERMS = "I confirm that I am aged 18 or over"

MEDICAL_TREATMENT_TERMS = "I give permission for myself to receive medical " \
                          "treatment in the event of an accident"

BOOL_CHOICES = ((True, 'Yes'), (False, 'No'))


@has_readonly_fields
class CookiePolicy(models.Model):
    read_only_fields = ('content', 'version', 'issue_date')

    content = models.TextField()
    version = models.DecimalField(unique=True, decimal_places=1, max_digits=100)
    issue_date = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name_plural = "Cookie Policies"

    @classmethod
    def current_version(cls):
        current_policy = CookiePolicy.current()
        if current_policy is None:
            return 0
        return current_policy.version

    @classmethod
    def current(cls):
        return CookiePolicy.objects.order_by('version').last()

    def __str__(self):
        return 'Cookie Policy - Version {}'.format(self.version)

    def save(self, **kwargs):
        if not self.id:
            current = CookiePolicy.current()
            if current and current.content == self.content:
                raise ValidationError('No changes made to content; not saved')

        if not self.id and not self.version:
            # if no version specified, go to next major version
            self.version = floor((CookiePolicy.current_version() + 1))
        super(CookiePolicy, self).save(**kwargs)
        ActivityLog.objects.create(
            log='Cookie Policy version {} created'.format(self.version)
        )


@has_readonly_fields
class DataPrivacyPolicy(models.Model):
    read_only_fields = ('content', 'version', 'issue_date')

    content = models.TextField()
    version = models.DecimalField(unique=True, decimal_places=1, max_digits=100)
    issue_date = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name_plural = "Data Privacy Policies"

    @classmethod
    def current_version(cls):
        current_policy = DataPrivacyPolicy.current()
        if current_policy is None:
            return 0
        return current_policy.version

    @classmethod
    def current(cls):
        return DataPrivacyPolicy.objects.order_by('version').last()

    def __str__(self):
        return 'Data Privacy Policy - Version {}'.format(self.version)

    def save(self, **kwargs):

        if not self.id:
            current = DataPrivacyPolicy.current()
            if current and current.content == self.content:
                raise ValidationError('No changes made to content; not saved')

        if not self.id and not self.version:
            # if no version specified, go to next major version
            self.version = floor((DataPrivacyPolicy.current_version() + 1))
        super(DataPrivacyPolicy, self).save(**kwargs)
        ActivityLog.objects.create(
            log='Data Privacy Policy version {} created'.format(self.version)
        )


class SignedDataPrivacy(models.Model):
    read_only_fields = ('date_signed', 'version')

    user = models.ForeignKey(
        User, related_name='data_privacy_agreement', on_delete=models.CASCADE
    )
    date_signed = models.DateTimeField(default=timezone.now)
    version = models.DecimalField(decimal_places=1, max_digits=100)

    class Meta:
        unique_together = ('user', 'version')
        verbose_name = "Signed Data Privacy Agreement"

    def __str__(self):
        return '{} - V{}'.format(self.user.username, self.version)

    @property
    def is_active(self):
        return self.version == DataPrivacyPolicy.current_version()

    def save(self, **kwargs):
        if not self.id:
            ActivityLog.objects.create(
                log="Signed data privacy policy agreement created: {}".format(self.__str__())
            )
        super(SignedDataPrivacy, self).save()
        # cache agreement
        if self.is_active:
            cache.set(
                active_data_privacy_cache_key(self.user), True, timeout=600
            )

    def delete(self, using=None, keep_parents=False):
        # clear cache if this is the active signed agreement
        if self.is_active:
            cache.delete(active_data_privacy_cache_key(self.user))
        super(SignedDataPrivacy, self).delete(using, keep_parents)


@has_readonly_fields
class BaseOnlineDisclaimer(models.Model):

    read_only_fields = (
        'disclaimer_terms', 'medical_treatment_terms', 'over_18_statement',
        'date'
    )
    date = models.DateTimeField(default=timezone.now)

    dob = models.DateField(verbose_name='date of birth')
    address = models.CharField(max_length=512)
    postcode = models.CharField(max_length=10)
    home_phone = models.CharField(max_length=255, null=True, blank=True)
    mobile_phone = models.CharField(max_length=255)
    emergency_contact1_name = models.CharField(max_length=255, verbose_name='name')
    emergency_contact1_relationship = models.CharField(max_length=255, verbose_name='relationship')
    emergency_contact1_phone = models.CharField(max_length=255, verbose_name='contact number')
    emergency_contact2_name = models.CharField(max_length=255, verbose_name='name')
    emergency_contact2_relationship = models.CharField(max_length=255, verbose_name='relationship')
    emergency_contact2_phone = models.CharField(max_length=255, verbose_name='contact number')

    medical_conditions = models.BooleanField(
        choices=BOOL_CHOICES, default=True,
        verbose_name='Do you have any medical conditions which may require '
                     'treatment or medication?'
    )
    medical_conditions_details = models.CharField(
        max_length=2048, null=True, blank=True
    )
    joint_problems = models.BooleanField(
        choices=BOOL_CHOICES, default=True,
        verbose_name='Do you suffer from problems regarding '
                     'knee/back/shoulder/ankle/hip/neck?'
    )
    joint_problems_details = models.CharField(
        max_length=2048, null=True, blank=True
    )
    allergies = models.BooleanField(
        choices=BOOL_CHOICES, default=True,
        verbose_name='Do you have any allergies?'
    )
    allergies_details = models.CharField(
        max_length=2048, null=True, blank=True
    )

    medical_treatment_terms = models.CharField(
        max_length=2048, default=OVER_18_TERMS
    )
    medical_treatment_permission = models.BooleanField()

    disclaimer_terms = models.CharField(
        max_length=2048, default=DISCLAIMER_TERMS
    )
    terms_accepted = models.BooleanField()

    over_18_statement = models.CharField(
        max_length=2048, default=OVER_18_TERMS
    )
    age_over_18_confirmed = models.BooleanField()

    class Meta:
        abstract = True


@has_readonly_fields
class OnlineDisclaimer(BaseOnlineDisclaimer):

    user = models.ForeignKey(
        User, related_name='online_disclaimer', on_delete=models.CASCADE
    )

    date_updated = models.DateTimeField(null=True, blank=True)
    name = models.CharField(max_length=255, verbose_name="full name")

    def __str__(self):
        return '{} - {}'.format(self.user.username, self.date.astimezone(
                pytz.timezone('Europe/London')
            ).strftime('%d %b %Y, %H:%M'))

    @property
    def is_active(self):
        # Disclaimer is active if it was signed <1 yr ago
        date_signed = self.date_updated if self.date_updated else self.date
        return (date_signed + timedelta(days=365)) > timezone.now()

    def save(self, **kwargs):
        if not self.id:
            self.disclaimer_terms = DISCLAIMER_TERMS
            self.over_18_statement = OVER_18_TERMS
            self.medical_treatment_terms = MEDICAL_TREATMENT_TERMS

            existing_disclaimers = OnlineDisclaimer.objects.filter(
                user=self.user
            )
            if existing_disclaimers and [
                True for disc in existing_disclaimers if disc.is_active
            ]:
                raise ValidationError('Active disclaimer already exists')

            ActivityLog.objects.create(
                log="Online disclaimer created: {}".format(self.__str__())
            )
        super(OnlineDisclaimer, self).save()
        # cache disclaimer
        if self.is_active:
            cache.set(
                active_online_disclaimer_cache_key(self.user), True, timeout=600
            )
            cache.set(
                active_disclaimer_cache_key(self.user), True, timeout=600
            )
        else:
            cache.set(
                expired_disclaimer_cache_key(self.user), True, timeout=600
            )

    def delete(self, using=None, keep_parents=False):
        # clear active cache if there is any
        cache.delete(active_disclaimer_cache_key(self.user))
        cache.delete(active_online_disclaimer_cache_key(self.user))
        # TODO: if disclaimer is < 6 yrs old (date signed or updated), it is being
        # delete by user request; copy data to ArchivedDisclaimer model
        expiry = timezone.now() - relativedelta(years=6)
        if self.date > expiry or (self.date_updated and self.date_updated > expiry):
            ignore_fields = ['id', 'user_id', '_state']
            fields = {key: value for key, value in self.__dict__.items() if key not in ignore_fields and not key.endswith('_oldval')}
            ArchivedDisclaimer.objects.create(**fields)
            ActivityLog.objects.create(
                log="Online disclaimer deleted; archive created for user {} {}".format(
                    self.user.first_name, self.user.last_name
                )
            )
        super(OnlineDisclaimer, self).delete(using, keep_parents)


class PrintDisclaimer(models.Model):
    user = models.OneToOneField(
        User, related_name='print_disclaimer', on_delete=models.CASCADE
    )
    date = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return '{} - {}'.format(self.user.username, self.date.astimezone(
                pytz.timezone('Europe/London')
            ).strftime('%d %b %Y, %H:%M'))

    @property
    def is_active(self):
        # Disclaimer is active if it was created <1 yr ago
        return (self.date + timedelta(days=365)) > timezone.now()

    def delete(self, using=None, keep_parents=False):
        # clear active cache if there is any
        cache.delete(active_disclaimer_cache_key(self.user))
        cache.delete(active_print_disclaimer_cache_key(self.user))
        super(PrintDisclaimer, self).delete(using, keep_parents)


@has_readonly_fields
class NonRegisteredDisclaimer(BaseOnlineDisclaimer):
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    email = models.EmailField()
    event_date = models.DateField()
    user_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    class Meta:
        verbose_name = 'Event disclaimer'

    @property
    def is_active(self):
        # Disclaimer is active if it was created <1 yr ago
        return (self.date + timedelta(days=365)) > timezone.now()

    def __str__(self):
        return '{} {} - {}'.format(self.first_name, self.last_name, self.date.astimezone(
                pytz.timezone('Europe/London')
            ).strftime('%d %b %Y, %H:%M'))

    def delete(self, using=None, keep_parents=False):
        expiry = timezone.now() - relativedelta(years=6)
        if self.date > expiry:
            ignore_fields = ['id', '_state', 'first_name', 'last_name', 'email', 'user_uuid']
            fields = {key: value for key, value in self.__dict__.items() if key not in ignore_fields and not key.endswith('_oldval')}

            ArchivedDisclaimer.objects.create(name='{} {}'.format(self.first_name, self.last_name), **fields)
            ActivityLog.objects.create(
                log="Event disclaimer < 6years old deleted; archive created for user {} {}".format(
                    self.first_name, self.last_name
                )
            )
        super().delete(using=using, keep_parents=keep_parents)


class ArchivedDisclaimer(BaseOnlineDisclaimer):

    name = models.CharField(max_length=255)
    date_updated = models.DateTimeField(null=True, blank=True)
    date_archived = models.DateTimeField(default=timezone.now)
    event_date = models.DateField(blank=True, null=True)

    def __str__(self):
        return '{} - {} (archived {})'.format(
            self.name,
            self.date.astimezone(pytz.timezone('Europe/London')).strftime('%d %b %Y, %H:%M'),
            self.date_archived.astimezone(pytz.timezone('Europe/London')).strftime('%d %b %Y, %H:%M')
        )
