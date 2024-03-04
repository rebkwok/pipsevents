from django.conf import settings
from django.db import models

from booking.models import EventType, Event, FilterCategory


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
    event_type = models.ForeignKey(EventType, null=True, on_delete=models.SET_NULL)
    description = models.TextField(blank=True, default="")
    location = models.CharField(
        max_length=255, choices=Event.LOCATION_CHOICES,
        default="Main Studio"
    )
    max_participants = models.PositiveIntegerField(
        null=True, blank=True, default=10,
        help_text="Leave blank if no max number of participants"
    )
    contact_person = models.CharField(max_length=255, default="Gwen Holbrey")
    contact_email = models.EmailField(default=settings.DEFAULT_STUDIO_EMAIL)
    cost = models.DecimalField(default=8.50, max_digits=8, decimal_places=2)
    booking_open = models.BooleanField(default=True)
    payment_open = models.BooleanField(default=True)
    advance_payment_required = models.BooleanField(default=True)
    payment_info = models.TextField(blank=True)
    payment_time_allowed = models.PositiveIntegerField(
        null=True, blank=True, default=4,
        help_text="Number of hours allowed for payment after booking (after "
                  "this bookings will be cancelled.)"
    )
    cancellation_period = models.PositiveIntegerField(
        default=24
    )
    allow_booking_cancellation = models.BooleanField(default=True)
    external_instructor = models.BooleanField(default=False)
    email_studio_when_booked = models.BooleanField(default=False)
    paypal_email = models.EmailField(
        default="thewatermelonstudio@hotmail.com",
        help_text='Email for the paypal account to be used for payment.  '
                  'Check this carefully!'
    )
    categories = models.ManyToManyField(FilterCategory)

    @property
    def location_index(self):
        return Event.LOCATION_INDEX_MAP[self.location]

    def __str__(self):
        return "{} - {} - {} ({})".format(
            dict(self.DAY_CHOICES)[self.day], self.time.strftime("%H:%M"),
            self.name, self.location
        )
