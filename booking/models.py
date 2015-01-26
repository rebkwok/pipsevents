from django.db import models
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django_extensions.db.fields import AutoSlugField


class Event(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    date = models.DateTimeField()
    location = models.CharField(max_length=255, default="Watermelon Studio")
    max_participants = models.PositiveIntegerField(null=True, blank=True, help_text="Leave blank if no max number of participants")
    contact_person = models.CharField(max_length=255, default="Gwen Burns")
    contact_email = models.EmailField(default="thewatermelonstudio@hotmail.com")
    cost = models.DecimalField(default=0, max_digits=8, decimal_places=2)
    payment_open = models.BooleanField(default=False)
    payment_info = models.TextField(blank=True)
    payment_due_date = models.DateTimeField(null=True, blank=True)
    slug = AutoSlugField(populate_from='name', max_length=40, unique=True)

    def spaces_left(self):
        if self.max_participants:
            booked_number = Booking.objects.filter(event__id=self.id).count()
            return self.max_participants - booked_number
        else:
            return 100

    def get_absolute_url(self):
        return reverse("booking:event_detail", kwargs={'slug': self.slug})

    def __unicode__(self):
        return self.name


class Booking(models.Model):
    user = models.ForeignKey(User, related_name='bookings')
    event = models.ForeignKey(Event, related_name='bookings')
    paid = models.BooleanField(verbose_name='Payment made (as confirmed by particpant', default=False, help_text='Payment has been made by user')
    payment_confirmed = models.BooleanField(default=False, help_text='Payment confirmed by admin/organiser')

    def confirm_space(self):
        self.paid = True
        self.payment_confirmed = True
        self.save()

    def space_confirmed(self):
        return self.event.cost == 0 or self.payment_confirmed
    space_confirmed.boolean = True

    class Meta:
        unique_together = ('user', 'event')

    def get_absolute_url(self):
        return reverse("booking:booking_detail", args=[str(self.id)])

    def __unicode__(self):
        return "{} {}".format(str(self.event.name), str(self.user.username))
