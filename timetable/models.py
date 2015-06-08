from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver

from booking.models import EventType

class Session(models.Model):
    MON = '01MON'
    TUE = '02TUE'
    WED = '03WED'
    THU = '04THU'
    FRI = '05FRI'
    SAT = '06SAT'
    SUN = '07SUN'
    DAY_CHOICES = (
        (MON, 'Monday'),
        (TUE, 'Tuesday'),
        (WED, 'Wednesday'),
        (THU, 'Thursday'),
        (FRI, 'Friday'),
        (SAT, 'Saturday'),
        (SUN, 'Sunday')
    )

    name=models.CharField(max_length=255)
    day = models.CharField(max_length=5, choices=DAY_CHOICES)
    time = models.TimeField()
    event_type = models.ForeignKey(EventType, null=True)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=255, default="Watermelon Studio")
    max_participants = models.PositiveIntegerField(
        null=True, blank=True, default=10,
        help_text="Leave blank if no max number of participants"
    )
    contact_person = models.CharField(max_length=255, default="Gwen Burns")
    contact_email = models.EmailField(default="thewatermelonstudio@hotmail.com")
    cost = models.DecimalField(default=7.00, max_digits=8, decimal_places=2)
    booking_open = models.BooleanField(default=True)
    payment_open = models.BooleanField(default=True)
    payment_info = models.TextField(blank=True)
    cancellation_period = models.PositiveIntegerField(
        default=24
    )
    external_instructor = models.BooleanField(default=False)
    email_studio_when_booked = models.BooleanField(default=False)

    def __str__(self):
        return "{} - {}".format(dict(self.DAY_CHOICES)[self.day], self.name)


@receiver(pre_save, sender=Session)
def session_pre_save(sender, instance, *args, **kwargs):
    if not instance.cost:
        instance.advance_payment_required = False
        instance.payment_open = False
        instance.payment_due_date = None
    if instance.external_instructor:
        # if external_instructor, make sure payment_open and booking_open
        # are False
        instance.payment_open = False
        instance.booking_open = False
