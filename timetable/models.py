from django.db import models


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

    POLE_CLASS = 'PC'
    OTHER_CLASS = 'CL'
    TYPE_CHOICES = (
        (POLE_CLASS, 'Pole level class'),
        (OTHER_CLASS, 'Other class'),
    )
    name=models.CharField(max_length=255)
    day = models.CharField(max_length=5, choices=DAY_CHOICES)
    time = models.TimeField()
    type = models.CharField(
        max_length=2, choices=TYPE_CHOICES, default=POLE_CLASS
    )
    description = models.TextField(blank=True)
    location = models.CharField(max_length=255, default="Watermelon Studio")
    max_participants = models.PositiveIntegerField(
        null=True, blank=True, default=15,
        help_text="Leave blank if no max number of participants"
    )
    contact_person = models.CharField(max_length=255, default="Gwen Burns")
    contact_email = models.EmailField(default="thewatermelonstudio@hotmail.com")
    cost = models.DecimalField(verbose_name='Cost (GBP)', default=7, max_digits=8, decimal_places=2)
    payment_open = models.BooleanField(default=True)

    def __str__(self):
        return "{} - {}".format(dict(self.DAY_CHOICES)[self.day], self.name)
