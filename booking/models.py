from django.db import models
from django.contrib.auth.models import User
from django_extensions.db.fields import AutoSlugField


class Location(models.Model):
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=255, blank=True)
    postcode = models.CharField(max_length=255, blank=True)

    def __unicode__(self):
        return self.name


class Event(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    date = models.DateTimeField()
    location = models.ForeignKey(Location, related_name='events')
    max_participants = models.PositiveIntegerField(null=True, blank=True)
    contact_person = models.CharField(max_length=255, default="Gwen Burns")
    contact_email = models.EmailField(default="thewatermelonstudio@hotmail.com")
    cost = models.PositiveIntegerField(default=0)
    payment_info = models.TextField(blank=True)
    payment_due_date = models.DateTimeField(null=True, blank=True)
    slug = AutoSlugField(populate_from='name', max_length=40, unique=True)

    def __unicode__(self):
        return self.name


class Booking(models.Model):
    user = models.ForeignKey(User, related_name='bookings')
    event = models.ForeignKey(Event, related_name='bookings')
    paid = models.BooleanField(default=False)

    def __unicode__(self):
        return "{} {}".format(str(self.event.name), str(self.user.username))
