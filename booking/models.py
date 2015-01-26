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
    cost = models.PositiveIntegerField(default=0)
    payment_open = models.BooleanField(default=False)
    payment_info = models.TextField(blank=True)
    payment_due_date = models.DateTimeField(null=True, blank=True)
    slug = AutoSlugField(populate_from='name', max_length=40, unique=True)

    def spaces_left(self):
        if self.max_participants:
            booked_number = Booking.objects.filter(event__id=self.id).count()
            return self.max_participants - booked_number

    def get_absolute_url(self):
        return reverse("booking:event_detail", kwargs={'slug': self.slug})

    def __unicode__(self):
        return self.name


class Booking(models.Model):
    user = models.ForeignKey(User, related_name='bookings')
    event = models.ForeignKey(Event, related_name='bookings')
    paid = models.BooleanField('Paid', default=False, help_text='Tick to confirm payment has been made')
    payment_confirmed = models.BooleanField('Payment confirmed by organiser', default=False)

    def confirm_place(self):
        self.paid = True
        self.payment_confirmed = True
        self.save()

    def space_confirmed(self):
        if self.event.cost > 0:
            if self.payment_confirmed:
                return True
            return False
        else:
            return True
    space_confirmed.boolean = True

    class Meta:
        unique_together = ('user', 'event')

    def get_absolute_url(self):
        return reverse("booking:booking_detail", args=[str(self.id)])

    def __unicode__(self):
        return "{} {}".format(str(self.event.name), str(self.user.username))
