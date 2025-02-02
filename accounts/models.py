# -*- coding: utf-8 -*-
import logging
import pytz
import uuid

from datetime import timedelta

from math import floor

from dateutil.relativedelta import relativedelta

from django.db import models
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist, ValidationError

from django.contrib.auth.models import User
from django.utils import timezone


from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


# Decorator for django models that contain readonly fields.
def has_readonly_fields(original_class):
    def store_read_only_fields(sender, instance, **kwargs):
        if not instance.id:
            return
        fields_to_store = list(sender.read_only_fields)
        if hasattr(instance, "is_draft"):
            fields_to_store.append("is_draft")
        for field_name in fields_to_store:
            val = getattr(instance, field_name)
            setattr(instance, field_name + "_oldval", val)

    def check_read_only_fields(sender, instance, **kwargs):
        if not instance.id:
            return
        elif instance.id and hasattr(instance, "is_draft"):
            if instance.is_draft:
                # we can edit if we're changing a draft
                return
            if instance.is_draft_oldval and not instance.is_draft:
                # we can edit if we're changing a draft to published
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
        super().save(**kwargs)
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
        super().save(**kwargs)
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
        # delete the cache key to force re-cache
        cache.delete(active_data_privacy_cache_key(self.user))
        if not self.id:
            ActivityLog.objects.create(
                log="Signed data privacy policy agreement created: {}".format(self.__str__())
            )
        super().save(**kwargs)

    def delete(self, using=None, keep_parents=False):
        # clear cache if this is the active signed agreement
        if self.is_active:
            cache.delete(active_data_privacy_cache_key(self.user))
        super().delete(using, keep_parents)


@has_readonly_fields
class DisclaimerContent(models.Model):
    read_only_fields = ('disclaimer_terms', 'medical_treatment_terms', 'over_18_statement', 'version', 'issue_date')
    disclaimer_terms = models.TextField()
    medical_treatment_terms = models.TextField()
    over_18_statement = models.TextField()
    version = models.DecimalField(unique=True, decimal_places=1, max_digits=100)
    issue_date = models.DateTimeField(default=timezone.now)
    is_draft = models.BooleanField(default=False)

    @classmethod
    def current_version(cls):
        current_content = DisclaimerContent.current()
        if current_content is None:
            return 0
        return current_content.version

    @classmethod
    def current(cls):
        return DisclaimerContent.objects.filter(is_draft=False).order_by('version').last()

    @property
    def status(self):
        return "draft" if self.is_draft else "published"

    def __str__(self):
        return f'Disclaimer Content - Version {self.version} ({self.status})'

    def save(self, **kwargs):
        if not self.id:
            current = DisclaimerContent.current()
            if (
                current and current.disclaimer_terms == self.disclaimer_terms
                and current.medical_treatment_terms == self.medical_treatment_terms
                and current.over_18_statement == self.over_18_statement
            ):
                raise ValidationError('No changes made to content; not saved')

        if not self.id and not self.version:
            # if no version specified, go to next major version
            self.version = float(floor((DisclaimerContent.current_version() + 1)))

        # Always update issue date on saving drafts or publishing first version
        if self.is_draft or getattr(self, "is_draft_oldval", False):
            self.issue_date = timezone.now()
        super().save(**kwargs)
        ActivityLog.objects.create(
            log='Disclaimer Content version {} created'.format(self.version)
        )

@has_readonly_fields
class BaseOnlineDisclaimer(models.Model):
    read_only_fields = ('date', 'version')
    date = models.DateTimeField(default=timezone.now)
    version = models.DecimalField(decimal_places=1, max_digits=100)

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

    medical_treatment_permission = models.BooleanField()

    terms_accepted = models.BooleanField()

    age_over_18_confirmed = models.BooleanField()

    expired = models.BooleanField(default=False)

    class Meta:
        abstract = True


@has_readonly_fields
class OnlineDisclaimer(BaseOnlineDisclaimer):

    user = models.ForeignKey(
        User, related_name='online_disclaimer', on_delete=models.CASCADE
    )

    date_updated = models.DateTimeField(null=True, blank=True)
    name = models.CharField(max_length=255, verbose_name="full name")

    class Meta:
        indexes = [
            models.Index(fields=["user"]),
        ]

    def __str__(self):
        return '{} - V{} - {}'.format(
            self.user.username,
            self.version,
            self.date.astimezone(pytz.timezone('Europe/London')).strftime('%d %b %Y, %H:%M'))

    def _signed_version_active(self):
        """
        Irrespective of manual expiry, is the signed disclaimer still active?  This controls
        whether manual expiry can be toggled on/off
        """
        date_signed = self.date_updated if self.date_updated else self.date
        return self.version == DisclaimerContent.current_version() and (
            date_signed + timedelta(days=365)
        ) > timezone.now()

    def can_toggle_expiry(self):
        return self._signed_version_active()

    @property
    def is_active(self):
        # Disclaimer is active if it was signed <1 yr ago AND it is the current version
        # AND it has not been manually expired
        if self.expired:
            return False
        return self._signed_version_active()

    def save(self, **kwargs):
        if not self.id:
            # Can't create a new disclaimer if an active one already exists (we can end up here when
            # a user double-clicks the save button)
            if has_active_disclaimer(self.user):
                logger.info(f"{self.user} aleady has active disclaimer, not creating another")
                return
            ActivityLog.objects.create(
                log=f"Online disclaimer created: {self}"
            )
        else:
            ActivityLog.objects.create(
                    log=f"Online disclaimer updated: {self}"
                )
        # delete the cache keys again to force re-cache on next retrieval
        cache.delete(active_disclaimer_cache_key(self.user))
        cache.delete(active_online_disclaimer_cache_key(self.user))
        cache.delete(expired_disclaimer_cache_key(self.user))
        super().save(**kwargs)

    def delete(self, using=None, keep_parents=False):
        # clear cache if there is any
        cache.delete(active_disclaimer_cache_key(self.user))
        cache.delete(active_online_disclaimer_cache_key(self.user))
        cache.delete(expired_disclaimer_cache_key(self.user))
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
        super().delete(using, keep_parents)


@has_readonly_fields
class NonRegisteredDisclaimer(BaseOnlineDisclaimer):
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    pronouns = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField()
    event_date = models.DateField()
    user_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    class Meta:
        verbose_name = 'event disclaimer'

    @property
    def is_active(self):
        # Disclaimer is active if it was created <1 yr ago AND it is the current version
        # AND it has not been manually expired
        if self.expired:
            return False
        return self.version == DisclaimerContent.current_version() and (self.date + timedelta(days=365)) > timezone.now()

    def __str__(self):
        return '{} {} - V{} - {}'.format(
            self.first_name,
            self.last_name,
            self.version,
            self.date.astimezone(pytz.timezone('Europe/London')).strftime('%d %b %Y, %H:%M'))

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
    pronouns = models.CharField(max_length=100, null=True, blank=True)
    date_updated = models.DateTimeField(null=True, blank=True)
    date_archived = models.DateTimeField(default=timezone.now)
    event_date = models.DateField(blank=True, null=True)

    def __str__(self):
        return '{} - V{} - {} (archived {})'.format(
            self.name,
            self.version,
            self.date.astimezone(pytz.timezone('Europe/London')).strftime('%d %b %Y, %H:%M'),
            self.date_archived.astimezone(pytz.timezone('Europe/London')).strftime('%d %b %Y, %H:%M')
        )


class AccountBan(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="ban")
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField()

    def save(self, *args, **kwargs):
        if not self.end_date:
            self.end_date = self.start_date + timedelta(days=14)
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user} - {self.end_date.strftime('%d %b %Y, %H:%M')}"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    pronouns = models.CharField(max_length=100, blank=True, null=True)
    stripe_customer_id = models.CharField(max_length=50, blank=True, null=True)
    booking_preference = models.CharField(
        choices=(("membership", "membership"), ("block", "block")), default="membership",
        help_text="Use membership or block first for booking (if you have both available)"    
    )

    def __str__(self):
        return self.user.username


# CACHING

def active_disclaimer_cache_key(user):
    return f'user_{user.id}_active_disclaimer_v{DisclaimerContent.current_version()}'


def active_online_disclaimer_cache_key(user):
    return f'user_{user.id}_active_online_disclaimer_v{DisclaimerContent.current_version()}'


def expired_disclaimer_cache_key(user):
    return 'user_{}_expired_disclaimer'.format(user.id)


def has_active_disclaimer(user):
    key = active_disclaimer_cache_key(user)
    has_disclaimer = cache.get(key)
    if has_disclaimer is None:
        has_disclaimer = has_active_online_disclaimer(user)
        cache.set(key, has_disclaimer, timeout=600)
    else:
        has_disclaimer = bool(cache.get(key))
    return has_disclaimer


def has_active_online_disclaimer(user):
    key = active_online_disclaimer_cache_key(user)
    if cache.get(key) is None:
        has_disclaimer = any(
            od.is_active for od in user.online_disclaimer.all()
        )
        cache.set(key, has_disclaimer, timeout=600)
    else:
        has_disclaimer = bool(cache.get(key))
    return has_disclaimer


def has_expired_disclaimer(user):
    key = expired_disclaimer_cache_key(user)
    has_disclaimer = cache.get(key)
    if has_disclaimer is None:
        if not has_disclaimer:
            has_disclaimer = any(
                (not od.is_active) for od in user.online_disclaimer.all()
            )
            cache.set(key, has_disclaimer, timeout=600)
    else:
        has_disclaimer = bool(cache.get(key))
    return has_disclaimer


def active_data_privacy_cache_key(user):
    current_version = DataPrivacyPolicy.current_version()
    return 'user_{}_active_data_privacy_agreement_version_{}'.format(
        user.id, current_version
    )


def has_active_data_privacy_agreement(user):
    key = active_data_privacy_cache_key(user)
    if cache.get(key) is None:
        has_active_agreement = user.data_privacy_agreement.filter(version=DataPrivacyPolicy.current_version()).exists()
        cache.set(key, has_active_agreement, timeout=600)
    else:
        has_active_agreement = bool(cache.get(key))
    return has_active_agreement
