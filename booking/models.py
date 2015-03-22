from django.db import models
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils import timezone

from django.template.defaultfilters import slugify
from django_extensions.db.fields import AutoSlugField

from datetime import timedelta
from dateutil.relativedelta import relativedelta


class Event(models.Model):
    POLE_CLASS = 'PC'
    WORKSHOP = 'WS'
    OTHER_CLASS = 'CL'
    OTHER_EVENT = 'EV'
    EVENT_TYPE_CHOICES = (
        (POLE_CLASS, 'Pole level class'),
        (WORKSHOP, 'Workshop'),
        (OTHER_CLASS, 'Other class'),
        (OTHER_EVENT, 'Other event'),
    )

    name = models.CharField(max_length=255)
    type = models.CharField(
        max_length=2, choices=EVENT_TYPE_CHOICES, default=POLE_CLASS
    )
    description = models.TextField(blank=True)
    date = models.DateTimeField()
    location = models.CharField(max_length=255, default="Watermelon Studio")
    max_participants = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Leave blank if no max number of participants"
    )
    contact_person = models.CharField(max_length=255, default="Gwen Burns")
    contact_email = models.EmailField(default="thewatermelonstudio@hotmail.com")
    cost = models.DecimalField(default=0, max_digits=8, decimal_places=2)
    advance_payment_required = models.BooleanField(default=False)
    booking_open = models.BooleanField(default=True)
    payment_open = models.BooleanField(default=False)
    payment_info = models.TextField(blank=True)
    payment_link = models.URLField(blank=True, default="http://www.paypal.co.uk")
    payment_due_date = models.DateTimeField(null=True, blank=True)
    cancellation_period = models.PositiveIntegerField(
        default=24
    )
    slug = AutoSlugField(populate_from='name', max_length=40, unique=True)

    def spaces_left(self):
        if self.max_participants:
            booked_number = Booking.objects.filter(event__id=self.id).count()
            return self.max_participants - booked_number
        else:
            return 100

    def bookable(self):
        if self.payment_due_date:
            return self.booking_open and \
                   self.payment_due_date > timezone.now() \
                   and self.spaces_left() > 0
        else:
            return self.booking_open \
                   and self.spaces_left() > 0

    def get_absolute_url(self):
        return reverse("booking:event_detail", kwargs={'slug': self.slug})

    def __str__(self):
        return '{} - {}'.format(
            str(self.name), self.date.strftime('%d %b %Y, %H:%M')
        )

@receiver(pre_save, sender=Event)
def event_pre_save(sender, instance, *args, **kwargs):
    if not instance.cost:
        instance.advance_payment_required = False
        instance.payment_open = False
        instance.payment_due_date = None
        instance.payment_link = ""


class Block(models.Model):
    """
    Block booking; blocks are 5 or 10 classes
    5 classes = GBP 32, 10 classes = GBP 62
    5 classes expires in 2 months, 10 classes expires in 4 months
    """
    SMALL_BLOCK_SIZE = 'SM'
    LARGE_BLOCK_SIZE = 'LG'
    SIZE_CHOICES = (
        (SMALL_BLOCK_SIZE, '5'),
        (LARGE_BLOCK_SIZE, '10'),
    )

    # [number of classes, cost, expiry in months from start_date]
    BLOCK_DATA = {
        SMALL_BLOCK_SIZE: [5, 32, 2],
        LARGE_BLOCK_SIZE: [10, 62, 4]
    }

    user = models.ForeignKey(User, related_name='blocks')
    block_size = models.CharField(
        verbose_name='Number of classes in block',
        max_length=2,
        choices=SIZE_CHOICES,
        default=SMALL_BLOCK_SIZE,
    )
    start_date = models.DateTimeField(default=timezone.now)
    paid = models.BooleanField(
        verbose_name='Payment made (as confirmed by participant)',
        default=False,
        help_text='Payment has been made by user'
    )
    payment_confirmed = models.BooleanField(
        default=False,
        help_text='Payment confirmed by admin/organiser'
    )

    def __str__(self):
        return "{} -- block size {} -- start {}".format(self.user.username,
                                                      self.block_size,
                                                      self.start_date.strftime(
                                                          '%d %b %Y, %H:%M')
        )

    @property
    def cost(self):
        return self.BLOCK_DATA[self.block_size][1]

    @property
    def expiry_date(self):
        return self.start_date + relativedelta(
            months=self.BLOCK_DATA[self.block_size][2])

    def active_block(self):
        """
        A block is active if its expiry date has not passed
        AND
        the number of bookings on it is < size
        AND
        it is <= one week since start_date OR payment is confirmed
        """
        expired = self.expiry_date < timezone.now()
        full = Booking.objects.filter(
            block__id=self.id).count() >= self.BLOCK_DATA[self.block_size][0]
        start_date_within_one_week = self.start_date >= timezone.now() \
            - timedelta(days=7)

        return (not expired and not full and
                (start_date_within_one_week or self.payment_confirmed))
    active_block.boolean = True

    def bookings_made(self):
        """
        Number of bookings made against block
        """
        return Booking.objects.filter(block__id=self.id).count()


    def get_absolute_url(self):
        return reverse("booking:block_list")


class Booking(models.Model):
    user = models.ForeignKey(User, related_name='bookings')
    event = models.ForeignKey(Event, related_name='bookings')
    paid = models.BooleanField(
        verbose_name='Payment made (as confirmed by participant)',
        default=False,
        help_text='Payment has been made by user'
    )
    date_booked = models.DateTimeField(default=timezone.now)
    payment_confirmed = models.BooleanField(
        default=False,
        help_text='Payment confirmed by admin/organiser'
    )
    date_payment_confirmed = models.DateTimeField(null=True, blank=True)
    block = models.ForeignKey(Block, related_name='bookings', null=True)
    date_space_confirmed = models.DateTimeField(null=True, blank=True)

    def confirm_space(self):
        if self.event.cost:
            self.paid = True
            self.payment_confirmed = True
            self.date_space_confirmed = timezone.now()
            self.save()

    def space_confirmed(self):
        return not self.event.advance_payment_required or \
               self.event.cost == 0 or \
               self.payment_confirmed
    space_confirmed.boolean = True

    class Meta:
        unique_together = ('user', 'event')

    def get_absolute_url(self):
        return reverse("booking:booking_detail", args=[str(self.id)])

    def __str__(self):
        return "{} {}".format(str(self.event.name), str(self.user.username))


@receiver(pre_save, sender=Booking)
def booking_pre_save(sender, instance, *args, **kwargs):
    if instance.payment_confirmed and not instance.date_payment_confirmed:
        instance.date_payment_confirmed = timezone.now()
    if not instance.event.cost and not instance.date_space_confirmed:
        instance.date_space_confirmed = timezone.now()
