# -*- coding: utf-8 -*-

import logging
import pytz

from datetime import timedelta

from django.db import models
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.utils import timezone

from accounts.utils import active_disclaimer_cache_key, \
    expired_disclaimer_cache_key
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
                   "the previous 12 weeks and I will update my teacher on " \
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
class OnlineDisclaimer(models.Model):

    read_only_fields = (
        'disclaimer_terms', 'medical_treatment_terms', 'over_18_statement',
        'date'
    )

    user = models.ForeignKey(User, related_name='online_disclaimer')
    date = models.DateTimeField(default=timezone.now)
    date_updated = models.DateTimeField(null=True, blank=True)

    name = models.CharField(max_length=255, verbose_name="full name")
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
                active_disclaimer_cache_key(self.user), True, timeout=6000
            )
        else:
            cache.set(
                expired_disclaimer_cache_key(self.user), True, timeout=6000
            )

    def delete(self, using=None, keep_parents=False):
        # clear active cache if there is any
        cache.delete(active_disclaimer_cache_key(self.user))
        super(OnlineDisclaimer, self).delete(using, keep_parents)


class PrintDisclaimer(models.Model):
    user = models.OneToOneField(User, related_name='print_disclaimer')
    date = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return '{} - {}'.format(self.user.username, self.date.astimezone(
                pytz.timezone('Europe/London')
            ).strftime('%d %b %Y, %H:%M'))

