import pytz

from django.db import models
from django.contrib.auth.models import User, Permission
from django.utils import timezone
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver


DISCLAIMER_TERMS = '''
    I recognise that I may be asked to participate in some strenuous exercise
    during the course and that such participation may present a heightened
    risk of injury or ill health. All risks will be fully explained and I do
    not hold The Watermelon Studio and any of their staff responsible for any
    harm that may come to me should I decide to participate in such tasks. I
    will not participate if pregnant and will update my teacher on any new
    medical condition/injury throughout my time at The Watermelon Studio.
    Other teachers/instructors may use the information submitted in this form
    to help keep the chances of any injury to a minimum. I also hereby agree
    to follow all rules set out by The Watermelon Studio.  I have
    read and agree to the terms and conditions on the website.
'''

BOOL_CHOICES = ((True, 'Yes'), (False, 'No'))

class OnlineDisclaimer(models.Model):
    user = models.OneToOneField(User, related_name='online_disclaimer')
    date = models.DateTimeField(default=timezone.now)

    name = models.CharField(max_length=255)
    dob = models.DateField(verbose_name='date of birth')
    address = models.CharField(max_length=512)
    postcode = models.CharField(max_length=10)
    home_phone = models.CharField(max_length=255)
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

    medical_treatment_permission = models.BooleanField(
        verbose_name='I give permission for myself to receive medical '
                     'treatment in the event of an accident'
    )

    disclaimer_terms = models.CharField(max_length=2048)
    terms_accepted = models.BooleanField()
    age_over_18_confirmed = models.BooleanField(
        verbose_name='I confirm that I am over the age of 18'
    )

    def __str__(self):
        return '{} - {}'.format(self.user.username, self.date.astimezone(
                pytz.timezone('Europe/London')
            ).strftime('%d %b %Y, %H:%M'))

    def save(self):
        if not self.id:
            self.disclaimer_terms = DISCLAIMER_TERMS
        super(OnlineDisclaimer, self).save()


class PrintDisclaimer(models.Model):
    user = models.OneToOneField(User, related_name='print_disclaimer')
    date = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return '{} - {}'.format(self.user.username, self.date.astimezone(
                pytz.timezone('Europe/London')
            ).strftime('%d %b %Y, %H:%M'))

