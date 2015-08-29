import logging
import pytz

from django.db import models
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.utils import timezone

from django_extensions.db.fields import AutoSlugField

from datetime import timedelta
from dateutil.relativedelta import relativedelta

from activitylog.models import ActivityLog

logger = logging.getLogger(__name__)

class BookingError(Exception):
    pass

class EventType(models.Model):
    TYPE_CHOICE = (
        ('CL', 'Class'),
        ('EV', 'Event')
    )
    event_type = models.CharField(max_length=2, choices=TYPE_CHOICE,
                                  help_text="This determines whether events "
                                            "of this type are listed on the "
                                            "'Classes' or 'Events' page")
    subtype = models.CharField(max_length=255,
                               help_text="Type of class/event. Use this to "
                                         "categorise events/classes.  If an "
                                         "event can be block booked, this "
                                         "should match the event type used in "
                                         "the Block Type.")

    def __str__(self):
        if self.event_type == 'CL':
            event_type = "Class"
        else:
            event_type = "Event"
        return '{} - {}'.format(event_type, self.subtype)

    class Meta:
        unique_together = ('event_type', 'subtype')


class Event(models.Model):
    name = models.CharField(max_length=255)
    event_type = models.ForeignKey(EventType)
    description = models.TextField(blank=True, default="")
    date = models.DateTimeField()
    location = models.CharField(max_length=255, default="Watermelon Studio")
    max_participants = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Leave blank if no max number of participants"
    )
    contact_person = models.CharField(max_length=255, default="Gwen Burns")
    contact_email = models.EmailField(
        default="thewatermelonstudio@hotmail.com"
        )
    cost = models.DecimalField(default=0, max_digits=8, decimal_places=2)
    advance_payment_required = models.BooleanField(default=True)
    booking_open = models.BooleanField(default=True)
    payment_open = models.BooleanField(default=True)
    payment_info = models.TextField(blank=True)
    payment_due_date = models.DateTimeField(
        null=True, blank=True,
        help_text='If this date is set, make sure that it is earlier '
                  'than the cancellation period.  Booking that are not paid '
                  'will be automatically cancelled (a warning email will be '
                  'sent to users first).')
    cancellation_period = models.PositiveIntegerField(
        default=24
    )
    external_instructor = models.BooleanField(
        default=False,
        help_text='Run by external instructor; booking and payment to be made '
                  'with instructor directly')
    email_studio_when_booked = models.BooleanField(default=False)
    slug = AutoSlugField(populate_from='name', max_length=40, unique=True)

    class Meta:
        ordering = ['-date']

    def spaces_left(self):
        if self.max_participants:
            booked_number = Booking.objects.filter(
                event__id=self.id, status='OPEN').count()
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

    def can_cancel(self):
        time_until_event = self.date - timezone.now()
        time_until_event = time_until_event.total_seconds() / 3600
        return time_until_event > self.cancellation_period

    def get_absolute_url(self):
        return reverse("booking:event_detail", kwargs={'slug': self.slug})

    def __str__(self):
        return '{} - {}'.format(
            str(self.name),
            self.date.astimezone(
                pytz.timezone('Europe/London')
            ).strftime('%d %b %Y, %H:%M')
        )

    def save(self, *args, **kwargs):
        if not self.cost:
            self.advance_payment_required = False
            self.payment_open = False
            self.payment_due_date = None
        if self.payment_due_date:
            # replace time with very end of day
            # move forwards 1 day and set hrs/min/sec/microsec to 0, then move
            # back 1 sec
            next_day = (self.payment_due_date + timedelta(
                days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            self.payment_due_date = next_day - timedelta(seconds=1)
            # if a payment due date is set, make sure advance_payment_required is
            # set to True
            self.advance_payment_required = True
        if self.external_instructor:
            # if external_instructor, make sure payment_open and booking_open
            # are False
            self.payment_open = False
            self.booking_open = False
        super(Event, self).save(*args, **kwargs)


class BlockType(models.Model):
    """
    Block type; currently blocks are 5 or 10 classes
    5 classes = GBP 32, 10 classes = GBP 62
    5 classes expires in 2 months, 10 classes expires in 4 months
    """
    size = models.PositiveIntegerField(help_text="Number of classes in block")
    event_type = models.ForeignKey(EventType)
    cost = models.DecimalField(max_digits=8, decimal_places=2)
    duration = models.PositiveIntegerField(
        help_text="Number of months until block expires")

    def __str__(self):
        return '{} - quantity {}'.format(self.event_type.subtype, self.size)


class Block(models.Model):
    """
    Block booking
    """

    user = models.ForeignKey(User, related_name='blocks')
    block_type = models.ForeignKey(BlockType)
    start_date = models.DateTimeField(default=timezone.now)
    paid = models.BooleanField(
        verbose_name='Paid',
        default=False,
        help_text='Payment has been made by user'
    )

    class Meta:
        ordering = ['user__username']

    def __str__(self):
        return "{} -- {} -- size {} -- start {}".format(
            self.user.username,
            self.block_type.event_type.subtype,
            self.block_type.size,
            self.start_date.strftime('%d %b %Y')
        )

    @property
    def expiry_date(self):
        # replace block expiry date with very end of day
        # move forwards 1 day and set hrs/min/sec/microsec to 0, then move
        # back 1 sec
        expiry_datetime = self.start_date + relativedelta(
            months=self.block_type.duration)
        next_day = (expiry_datetime + timedelta(
            days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return next_day - timedelta(seconds=1)

    @property
    def expired(self):
        return self.expiry_date < timezone.now()

    @property
    def full(self):
        return Booking.objects.filter(
            block__id=self.id).count() >= self.block_type.size

    def active_block(self):
        """
        A block is active if its expiry date has not passed
        AND
        the number of bookings on it is < size
        AND
        payment is confirmed
        """
        return not self.expired and not self.full and self.paid
    active_block.boolean = True

    def bookings_made(self):
        """
        Number of bookings made against block
        """
        return Booking.objects.filter(block__id=self.id).count()

    def get_absolute_url(self):
        return reverse("booking:block_list")

    def delete(self, *args, **kwargs):
        bookings = Booking.objects.filter(block=self.id)
        for booking in bookings:
            if booking.event.cost > 0:
                booking.paid = False
                booking.payment_confirmed = False
                booking.block = None
                booking.save()
            ActivityLog.objects.create(
                log='Booking id {} booked with deleted block {} has been reset to '
                'unpaid'.format(booking.id, self.id)
            )
        super(Block, self).delete(*args, **kwargs)


class Booking(models.Model):
    STATUS_CHOICES = (
        ('OPEN', 'Open'),
        ('CANCELLED', 'Cancelled')
    )

    user = models.ForeignKey(User, related_name='bookings')
    event = models.ForeignKey(Event, related_name='bookings')
    paid = models.BooleanField(
        default=False,
        help_text='Payment has been made by user'
    )
    date_booked = models.DateTimeField(default=timezone.now)
    payment_confirmed = models.BooleanField(
        default=False,
        help_text='Payment confirmed by admin/organiser'
    )
    date_payment_confirmed = models.DateTimeField(null=True, blank=True)
    block = models.ForeignKey(
        Block, related_name='bookings', null=True, blank=True,
        on_delete=models.SET_NULL
        )
    status = models.CharField(
        max_length=255, choices=STATUS_CHOICES, default='OPEN'
    )
    attended = models.BooleanField(
        default=False, help_text='Student has attended this event')
    # Flags for email reminders and warnings
    reminder_sent = models.BooleanField(default=False)
    warning_sent = models.BooleanField(default=False)
    free_class = models.BooleanField(default=False)

    class Meta:
        unique_together = ('user', 'event')
        permissions = (
            ("can_book_free_pole_practice", "Can book free pole practice"),
            ("is_regular_student", "Is regular student")
        )

    def __str__(self):
        return "{} - {}".format(str(self.event.name), str(self.user.username))

    def confirm_space(self):
        if self.event.cost:
            self.paid = True
            self.payment_confirmed = True
            self.save()
            ActivityLog.objects.create(
                log='Space confirmed manually for Booking {} ({})'.format(
                    self.id, self.event)
            )

    def space_confirmed(self):
        # False if cancelled
        # True if open and advance payment not required or cost = 0 or
        # payment confirmed
        if self.status == 'CANCELLED':
            return False
        return not self.event.advance_payment_required \
            or self.event.cost == 0 \
            or self.payment_confirmed
    space_confirmed.boolean = True

    def save(self, *args, **kwargs):
        if self.pk is not None:
            orig = Booking.objects.get(pk=self.pk)
            if orig.status == 'CANCELLED' and \
            self.status == 'OPEN' and \
            self.event.spaces_left() == 0:
                raise BookingError(
                    'Attempting to reopen booking for full '
                    'event %s' % self.event.id
                )
        else:
            if self.status != "CANCELLED" and \
            self.event.spaces_left() == 0:
                raise BookingError(
                    'Attempting to create booking for full '
                    'event %s' % self.event.id
                )

        if self.payment_confirmed and not self.date_payment_confirmed:
            self.date_payment_confirmed = timezone.now()
        if self.free_class:
            self.paid = True
            self.payment_confirmed = True
            self.block = None
        super(Booking, self).save(*args, **kwargs)


class WaitingListUser(models.Model):
    """
    A model to represent a single user on a waiting list for an event
    """
    user = models.ForeignKey(User, related_name='waitinglists')
    event = models.ForeignKey(Event, related_name='waitinglistusers')
    # date user joined the waiting list
    date_joined = models.DateTimeField(default=timezone.now)
