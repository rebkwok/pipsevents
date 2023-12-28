# -*- coding: utf-8 -*-

from collections.abc import Iterable
import logging
import pytz
import shortuuid

from decimal import Decimal

from django.db import models
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from django_extensions.db.fields import AutoSlugField

from datetime import timedelta
from dateutil.relativedelta import relativedelta

from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


class BlockTypeError(Exception):
    pass


class TicketBookingError(Exception):
    pass


class AllowedGroup(models.Model):
    group = models.OneToOneField(Group, on_delete=models.CASCADE)
    description = models.CharField(
        max_length=255, null=True, blank=True, 
        help_text='Optional description of permitted group, e.g. "only available to regular students"'
    )

    class Meta:
        ordering = ("group__name",)

    def __str__(self):
        if self.group.name.startswith("_"):
            return self.group.name[1:].title()
        return self.group.name.title()

    def has_permission(self, user):
        if self.group == self.open_to_all_group():
            return True
        return self.group in user.groups.all()

    def add_user(self, user):
        if self.group not in user.groups.all():
            user.groups.add(self.group)

    def remove_user(self, user):
        if self.group in user.groups.all():
            user.groups.remove(self.group)

    @classmethod
    def open_to_all_group(cls):
        group, _ = Group.objects.get_or_create(name="_open to all")
        return group

    @classmethod
    def default_group(cls):
        allowed_group, _ = cls.objects.get_or_create(group=cls.open_to_all_group(), defaults={"description": "default group; open to all"})
        return allowed_group

    @classmethod
    def create_with_group(cls, group_name, description=None):
        group = Group.objects.create(name=group_name.lower())
        return cls.objects.create(group=group, description=description)


class EventType(models.Model):
    TYPE_CHOICE = (
        ('CL', 'Class'),
        ('EV', 'Event'),
        ('OT', "Online tutorial"),
        ('RH', 'Room hire')
    )
    TYPE_VERBOSE_NAME = dict(TYPE_CHOICE)
    event_type = models.CharField(max_length=2, choices=TYPE_CHOICE,
                                  help_text="This determines whether events "
                                            "of this type are listed on the "
                                            "'Classes', 'Workshops', 'Tutorials', 'Room "
                                            "Hire' pages")
    subtype = models.CharField(max_length=255,
                               help_text="Type of class/event. Use this to "
                                         "categorise events/classes.  If an "
                                         "event can be block booked, this "
                                         "should match the event type used in "
                                         "the Block Type.")
    allowed_group = models.ForeignKey(
        AllowedGroup, null=True, blank=True, related_name="event_types",
        help_text="Group allowed to book this type of event", on_delete=models.SET_NULL
    )

    def __str__(self):
        return f'{self.TYPE_VERBOSE_NAME.get(self.event_type, "Unknown")} - {self.subtype}'

    @property
    def readable_name(self):
        return self.TYPE_VERBOSE_NAME[self.event_type]

    def has_permission_to_book(self, user):
        return self.allowed_group.has_permission(user)

    def add_permission_to_book(self, user):

        return self.allowed_group.add_user(user)

    @property
    def allowed_group_description(self):
        return self.allowed_group.description

    def save(self, *args, **kwargs):
        if not self.allowed_group:
            self.allowed_group = AllowedGroup.default_group()
        return super().save(*args, **kwargs)

    class Meta:
        unique_together = ('event_type', 'subtype')


class FilterCategory(models.Model):
    category = models.CharField(max_length=255)
    
    def __str__(self):
        return self.category

    class Meta:
        constraints = [
            models.UniqueConstraint(models.functions.Lower('category'), name='unique_lower_category')
        ]
        verbose_name_plural = "Filter categories"


class Event(models.Model):
    LOCATION_CHOICES = (
        ("Beaverbank Place", "The Watermelon Studio - Beaverbank Place"),
        ("Online", "Online"),
        ("Davidson's Mains", "The Watermelon Studio - Davidson's Mains"),
    )
    LOCATION_INDEX_MAP = {
        "Beaverbank Place": 1,
        "Online": 2,
        "Davidson's Mains": 3,
    }
    name = models.CharField(max_length=255)
    event_type = models.ForeignKey(EventType, on_delete=models.CASCADE)
    description = models.TextField(blank=True, default="")
    date = models.DateTimeField()
    location = models.CharField(
        max_length=255, choices=LOCATION_CHOICES, default="Beaverbank Place"
    )
    location_index = models.PositiveIntegerField(default=1)
    max_participants = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Leave blank if no max number of participants"
    )
    contact_person = models.CharField(max_length=255, default="Gwen Holbrey")
    contact_email = models.EmailField(default=settings.DEFAULT_STUDIO_EMAIL)
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
    payment_time_allowed = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Number of hours allowed for payment after booking (after "
                  "this bookings will be cancelled.)"
    )
    cancellation_period = models.PositiveIntegerField(
        default=24
    )
    external_instructor = models.BooleanField(
        default=False,
        help_text='Run by external instructor; booking and payment to be made '
                  'with instructor directly')
    email_studio_when_booked = models.BooleanField(default=False)
    slug = AutoSlugField(
        populate_from=['name', 'date'], max_length=40, unique=True
    )
    cancelled = models.BooleanField(default=False)
    allow_booking_cancellation = models.BooleanField(default=True)
    paypal_email = models.EmailField(
        default="thewatermelonstudio@hotmail.com",
        help_text='Email for the paypal account to be used for payment.  '
                  'Check this carefully!'
    )
    video_link = models.URLField(null=True, blank=True, help_text="Zoom/Video URL (for online classes only)")
    video_link_available_after_class = models.BooleanField(
        default=False,
        help_text="Zoom/Video URL available after class is past (for online classes only)"
    )
    visible_on_site = models.BooleanField(default=True)
    categories = models.ManyToManyField(FilterCategory)

    allowed_group = models.ForeignKey(
        AllowedGroup, null=True, blank=True, related_name="events", on_delete=models.SET_NULL,
        help_text="Override group allowed to book this event (defaults to same group as the event type)"
    )

    class Meta:
        ordering = ['-date']
        indexes = [
            models.Index(fields=['event_type', 'date', 'cancelled']),
            models.Index(fields=['event_type', 'name', 'date', 'cancelled']),
        ]

    @property
    def spaces_left(self):
        if self.max_participants:
            booked_number = Booking.objects.filter(
                event__id=self.id, status='OPEN', no_show=False).count()
            return self.max_participants - booked_number
        else:
            return 100

    @property
    def bookable(self):
        return self.booking_open and self.spaces_left > 0

    @property
    def can_cancel(self):
        now = timezone.now()
        time_until_event = self.date - timezone.now()
        time_until_event = time_until_event.total_seconds() / 3600
        # adjust cancellation period if now and event date are in different DST states
        # in spring, if it's currently before DST and the class is after DST, we need to decrease the
        # cancellation period by 1 hour i.e.
        # - currently it is 9.30am and NOT DST
        # - class is tomorrow at 10am and IS DST
        # Only 23.5 actual hrs between now and class time, but user would expect to be able to cancel
        # if cancellation period is 24 hrs
        
        # Only bother checking if it's currently March or October; DST only has an impact on cancellations
        # made within a day or two (depending on cancellation time) of event date 
        cancellation_period = self.cancellation_period
        if now.month in [3, 10]:
            local_tz = pytz.timezone("Europe/London")
            now_local = now.astimezone(local_tz)
            event_date_local = self.date.astimezone(local_tz)
            # find the difference in DST offset between now and the event date (in hours)
            dst_diff_in_hrs = (now_local.dst().seconds - event_date_local.dst().seconds) / (60 * 60)
            # add this to the cancellation period
            # For spring, this means now (0 offset) minus event date (1 hr offset) == -1 hour
            # We subtract 1 hour from the cancellation period, so for a 24 hr cancellation users can 
            # cancel in the 23 hrs before
            # For Autumn we add 1 hour, so the cancellation period is 1 hr more
            cancellation_period += dst_diff_in_hrs

        return time_until_event > cancellation_period

    @property
    def show_video_link(self):
        return (self.is_online and (timezone.now() > self.date - timedelta(minutes=20)) or self.event_type.event_type == "OT")

    def has_permission_to_book(self, user):
        return self.allowed_group.has_permission(user)
    
    @property
    def allowed_group_description(self):
        return self.allowed_group.description

    def allowed_group_for_event(self):
        if self.allowed_group == AllowedGroup.default_group():
            return "-"
        return self.allowed_group or self.event_type.allowed_group
        
    def get_absolute_url(self):
        return reverse("booking:event_detail", kwargs={'slug': self.slug})

    @property
    def is_past(self):
        return self.date < timezone.now()

    @property
    def is_online(self):
        return "online" in self.event_type.subtype.lower()

    def __str__(self):
        return f'{self.str_no_location()} ({self.location})'
    
    def str_no_location(self):
        formatted_date = self.date.astimezone(pytz.timezone('Europe/London')).strftime('%d %b %Y, %H:%M')
        return f"{self.name} - {formatted_date}"

    def save(self, *args, **kwargs):
        self.location_index = self.LOCATION_INDEX_MAP[self.location]
        if not self.cost:
            self.advance_payment_required = False
            self.payment_open = False
            self.payment_due_date = None
            self.payment_time_allowed = None
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
        if self.payment_time_allowed:
            self.advance_payment_required = True
        if self.external_instructor:
            # if external_instructor, make sure payment_open and booking_open
            # are False
            self.payment_open = False
            self.booking_open = False

        if not self.allowed_group:
            self.allowed_group = self.event_type.allowed_group

        super(Event, self).save(*args, **kwargs)


class BlockType(models.Model):
    """
    Block type; currently blocks are 5 or 10 classes
    5 classes = GBP 32, 10 classes = GBP 62
    5 classes expires in 2 months, 10 classes expires in 4 months
    """
    identifier = models.CharField(
        max_length=255, null=True, blank=True,
        help_text="Optional identifier for individual or group of block types "
                  "(e.g. sale blocks)"
    )
    size = models.PositiveIntegerField(help_text="Number of classes in block")
    event_type = models.ForeignKey(EventType, on_delete=models.CASCADE)
    cost = models.DecimalField(max_digits=8, decimal_places=2)
    duration = models.PositiveIntegerField(
        help_text="Number of months until block expires", blank=True, null=True)
    duration_weeks = models.PositiveIntegerField(
        help_text="Number of weeks until block expires", blank=True, null=True)    
    active = models.BooleanField(default=False)
    assign_free_class_on_completion = models.BooleanField(default=False)
    paypal_email = models.EmailField(
        default="thewatermelonstudio@hotmail.com",
        help_text='Email for the paypal account to be used for payment.  '
                  'Check this carefully!'
    )

    class Meta:
        ordering = ('event_type__subtype', 'size')

    def __str__(self):
        return '{}{} - quantity {}'.format(
            self.event_type.subtype,
            ' ({})'.format(self.identifier) if self.identifier else '',
            self.size
        )
    
    def save(self, *args, **kwargs) -> None:
        if self.duration and self.duration_weeks:
            raise ValidationError("A block type must have a duration or duration_weeks (not both)") 
        if not (self.duration or self.duration_weeks):
            if settings.TESTING:
                # set a default for tests
                self.duration = 1
            else:
                raise ValidationError("A block type must have a duration or duration_weeks") 
        return super().save(*args, **kwargs)
    
    @property
    def duration_type(self):
        return "weeks" if self.duration_weeks else "months"

    @cached_property
    def description(self):
        return f'{self.event_type.subtype} - {self.size} classes (block)'

    @classmethod
    def get_transfer_block_type(cls, event_type):
        block_type, _ = cls.objects.get_or_create(
            event_type=event_type,
            size=1, cost=0, duration_weeks=2,
            identifier='transferred',
            active=False
        )
        return block_type

@receiver(pre_save)
def check_duplicate_blocktype(sender, instance, **kwargs):
    # makes sure we don't create duplicate
    if sender == BlockType:
        if not instance.id and instance.identifier:
            if instance.identifier == "free class" \
                    or instance.identifier == "transferred":
                if BlockType.objects.filter(
                    event_type=instance.event_type,
                    identifier=instance.identifier,
                    duration=instance.duration,
                    duration_weeks=instance.duration_weeks,
                ).count() == 1:
                    raise BlockTypeError(
                        'Block type with event type "{}" and idenitifer "{}" '
                        'already exists'.format(
                            instance.event_type,
                            instance.identifier
                        )
                    )


class Block(models.Model):
    """
    Block booking
    """

    user = models.ForeignKey(User, related_name='blocks', on_delete=models.CASCADE)
    block_type = models.ForeignKey(BlockType, on_delete=models.CASCADE)
    start_date = models.DateTimeField(default=timezone.now)
    paid = models.BooleanField(
        verbose_name='Paid',
        default=False,
        help_text='Payment has been made by user'
    )
    parent = models.ForeignKey(
        'self', blank=True, null=True, related_name='children',
        on_delete=models.CASCADE, help_text="Used for auto-assigned free classes"
    )
    transferred_booking_id = models.PositiveIntegerField(blank=True, null=True)
    extended_expiry_date = models.DateTimeField(blank=True, null=True)
    paypal_pending = models.BooleanField(default=False)
    expiry_date = models.DateTimeField()

    # stripe payments
    invoice = models.ForeignKey("stripe_payments.Invoice", on_delete=models.SET_NULL, null=True, blank=True, related_name="blocks")
    checkout_time = models.DateTimeField(null=True, blank=True)

    # voucher
    # voucher_code; used to keep track of a code being applied; doesn't mean it's
    # actually used (See UsedEventVoucher instead, which are applied only on marking
    # payment complete)
    voucher_code = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        ordering = ['user__username', 'id']
        indexes = [
                models.Index(fields=['user', 'paid']),
                models.Index(fields=['user', 'expiry_date']),
                models.Index(fields=['user', '-start_date']),
            ]

    def __str__(self):

        return "{} -- {}{} -- size {} -- start {}".format(
            self.user.username,
            self.block_type.event_type.subtype,
            ' ({})'.format(self.block_type.identifier)
            if self.block_type.identifier else '',
            self.block_type.size,
            self.start_date.strftime('%d %b %Y')
        )

    def mark_checked(self):
        self.checkout_time = timezone.now()
        self.save()

    @classmethod
    def get_end_of_day(cls, input_datetime):
        next_day = (input_datetime + timedelta(
            days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_of_day_utc = next_day - timedelta(seconds=1)
        uktz = pytz.timezone('Europe/London')
        end_of_day_uk = end_of_day_utc.astimezone(uktz)
        utc_offset = end_of_day_uk.utcoffset()
        return end_of_day_utc - utc_offset

    def get_expiry_date(self):
        # replace block expiry date with very end of day in local time
        # move forwards 1 day and set hrs/min/sec/microsec to 0, then move
        # back 1 sec
        # For a with a parent block with a parent (free class block),
        # override blocktype duration to be same as parent's blocktype
        duration = self.block_type.duration
        duration_weeks = self.block_type.duration_weeks
        if self.parent:
            duration = self.parent.block_type.duration
            duration_weeks = self.block_type.duration_weeks

        if duration_weeks:
            expiry_datetime = self.start_date + timedelta(weeks=duration_weeks)
        else:
            expiry_datetime = self.start_date + relativedelta(months=duration)

        # if a manual extended expiry date has been set, use that instead (it can be earlier than the data calculated from duration)
        # extended_expiry_date is set to end of day on save, so just return it
        if self.extended_expiry_date:
            return self.extended_expiry_date

        return self.get_end_of_day(expiry_datetime)

    @cached_property
    def expired(self):
        return self.expiry_date < timezone.now()

    @property
    def full(self):
        return Booking.objects.select_related('block', 'block__block_type')\
                   .filter(block__id=self.id).count() >= self.block_type.size

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

    @property
    def cost_with_voucher(self):
        original_cost = self.block_type.cost
        if self.voucher_code:
            try:
                voucher = BlockVoucher.objects.get(code=self.voucher_code)
                return (
                    Decimal(original_cost) * Decimal((100 - voucher.discount) / 100)
                ).quantize(Decimal('.01'))
            except BlockVoucher.DoesNotExist:
                self.voucher_code = None
                self.save()
        return original_cost

    def reset_voucher_code(self):
        self.voucher_code = None
        self.save()
    
    def process_voucher(self):
        if self.voucher_code:
            try:
                voucher = BlockVoucher.objects.get(code=self.voucher_code)
                UsedBlockVoucher.objects.get_or_create(voucher=voucher, block_id=self.id, user=self.user)
            except BlockVoucher.DoesNotExist:
                logger.error(
                    f"Tried to process non-existent Block Voucher with code '{self.voucher_code}' "
                    f"for block {self.id}" 
                )

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

    def save(self, *args, **kwargs):
        # for an existing block, if changed to paid, update start date to now
        # (in case a user leaves a block sitting in basket for a while)
        if self.id:
            pre_save_block = Block.objects.get(id=self.id)
            if not pre_save_block.paid and self.paid and not self.parent:
                self.start_date = timezone.now()
            # also update expiry date based on revised start date if changed
            if pre_save_block.start_date != self.start_date:
                self.expiry_date = self.get_expiry_date()

        # if block has parent, make start date same as parent
        if self.parent:
            self.start_date = self.parent.start_date
        if self.block_type.cost == 0:
            self.paid = True

        # make extended expiry date end of day
        if self.extended_expiry_date:
            self.extended_expiry_date = self.get_end_of_day(
                self.extended_expiry_date
            )
            self.expiry_date = self.get_expiry_date()

        if not self.expiry_date or not self.id:
            self.expiry_date = self.get_expiry_date()

        super(Block, self).save(*args, **kwargs)


class Booking(models.Model):
    STATUS_CHOICES = (
        ('OPEN', 'Open'),
        ('CANCELLED', 'Cancelled')
    )

    user = models.ForeignKey(
        User, related_name='bookings', on_delete=models.CASCADE
    )
    event = models.ForeignKey(
        Event, related_name='bookings', on_delete=models.CASCADE
    )
    paid = models.BooleanField(
        default=False,
        help_text='Payment has been made by user'
    )
    deposit_paid = models.BooleanField(
        default=False,
        help_text='Deposit payment has been made by user'
    )
    date_booked = models.DateTimeField(default=timezone.now)
    date_rebooked = models.DateTimeField(null=True, blank=True)
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
    no_show = models.BooleanField(
        default=False, help_text='Student paid but did not attend')

    instructor_confirmed_no_show = models.BooleanField(
        default=False, help_text="Marked as no-show by instructor (confirmed no-show, not late cancellation)"
    )

    # Flags for email reminders and warnings
    reminder_sent = models.BooleanField(default=False)
    warning_sent = models.BooleanField(default=False)
    date_warning_sent = models.DateTimeField(null=True, blank=True)

    free_class_requested = models.BooleanField(default=False)
    free_class = models.BooleanField(default=False)
    # Flag to note if booking was autocancelled due to non-payment - use to
    # disable rebooking
    auto_cancelled = models.BooleanField(default=False)

    paypal_pending = models.BooleanField(default=False)

    # stripe payments
    invoice = models.ForeignKey("stripe_payments.Invoice", on_delete=models.SET_NULL, null=True, blank=True, related_name="bookings")
    checkout_time = models.DateTimeField(null=True, blank=True)

    # voucher
    # voucher_code; used to keep track of a code being applied; doesn't mean it's
    # actually used (See UsedEventVoucher instead, which are applied only on marking
    # payment complete)
    voucher_code = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        unique_together = ('user', 'event')
        permissions = (
            ("can_request_free_class", "Can request free class and pole practice"),
            ("is_regular_student", "Is regular student"),
            ("can_view_registers", "Can view registers"),
        )
        indexes = [
            models.Index(fields=['event', 'user', 'status']),
            models.Index(fields=['block']),
        ]

    def __str__(self):
        return "{} - {} - {}".format(
            str(self.event.name), str(self.user.username),
            self.event.date.strftime('%d%b%Y %H:%M')
        )

    def mark_checked(self):
        self.checkout_time = timezone.now()
        self.save()

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
        if self.status == 'CANCELLED' or self.no_show:
            return False
        return not self.event.advance_payment_required \
            or self.event.cost == 0 \
            or self.payment_confirmed
    space_confirmed.boolean = True

    @property
    def can_cancel(self):
        if not self.event.allow_booking_cancellation:
            return False
        return self.event.can_cancel

    @property
    def has_available_block(self):
        available_blocks = [
            block for block in
            Block.objects.select_related("user", "block_type").filter(
                user=self.user, block_type__event_type=self.event.event_type
            )
            if block.active_block()
        ]
        return bool(available_blocks)

    @cached_property
    def has_unpaid_block(self):
        available_blocks = [
            block for block in
            Block.objects.select_related("user", "block_type").filter(
                user=self.user, block_type__event_type=self.event.event_type
            )
            if not block.full and not block.expired and not block.paid
        ]
        return bool(available_blocks)

    @cached_property
    def payment_method(self):
        if not self.paid:
            return ""
        if self.block:
            return "Block"

        from payments.models import PaypalBookingTransaction
        if PaypalBookingTransaction.objects.filter(
            booking=self, transaction_id__isnull=False).exists():
            return "PayPal"
        from stripe_payments.models import Invoice
        invoice = Invoice.objects.filter(bookings=self, paid=True).first()
        if invoice:
            if invoice.amount > 0:
                return "Stripe"
            else:
                return "Voucher"
        return ""
    
    @property
    def cost_with_voucher(self):
        original_cost = self.event.cost
        if self.voucher_code:
            try:
                voucher = EventVoucher.objects.get(code=self.voucher_code)
                return (
                    Decimal(original_cost) * Decimal((100 - voucher.discount) / 100)
                ).quantize(Decimal('.01'))
            except EventVoucher.DoesNotExist:
                self.voucher_code = None
                self.save()
        return original_cost

    def reset_voucher_code(self):
        self.voucher_code = None
        self.save()

    def process_voucher(self):
        if self.voucher_code:
            try:
                voucher = EventVoucher.objects.get(code=self.voucher_code)
                UsedEventVoucher.objects.get_or_create(voucher=voucher, booking_id=self.id, user=self.user)
            except EventVoucher.DoesNotExist:
                logger.error(
                    f"Tried to process non-existent Event Voucher with code '{self.voucher_code}' "
                    f"for booking {self.id}" 
                )

    def _old_booking(self):
        if self.pk:
            return Booking.objects.get(pk=self.pk)
        return None

    def _is_new_booking(self):
        if not self.pk:
            return True

    def _is_rebooking(self):
        if not self.pk:
            return False
        was_cancelled = self._old_booking().status == 'CANCELLED' \
            and self.status == 'OPEN'
        was_no_show = self._old_booking().no_show and not self.no_show
        return was_cancelled or was_no_show

    def _is_cancellation(self):
        if not self.pk:
            return False
        return self._old_booking().status == 'OPEN' \
            and self.status == 'CANCELLED'

    def clean(self):
        if self._is_rebooking():
            if self.event.spaces_left == 0:
                raise ValidationError(
                    _('Attempting to reopen booking for full '
                      'event %s' % self.event.id)
                )

        if self._is_new_booking() and self.status != "CANCELLED" and \
                self.event.spaces_left == 0:
                    raise ValidationError(
                        _('Attempting to create booking for full '
                          'event %s (id %s)' % (str(self.event), self.event.id))
                    )

        if self.attended and self.no_show:
            raise ValidationError(
                _('Booking cannot be both attended and no-show')
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        rebooking = self._is_rebooking()
        cancellation = self._is_cancellation()
        orig = self._old_booking()

        if rebooking:
            self.date_rebooked = timezone.now()
            # reset auto_cancelled so user can rebook if they manually cancelled
            # later
            if self.auto_cancelled == True:
                ActivityLog.objects.create(
                    log="Auto_cancelled booking {} for {} has been "
                        "reopened".format(
                            self.id, self.user.username,
                        )
                )
                self.auto_cancelled = False

        if (cancellation and orig.block) or \
                (orig and orig.block and not self.block):
            # cancelling a booking from a block or removing booking from block
            # if block has a used free class, move the booking from the
            #  free
            # class to this block, otherwise delete the free class block
            free_class_block = orig.block.children.first()
            if free_class_block:
                if free_class_block.bookings.exists():
                    free_booking = free_class_block.bookings.first()
                    free_booking.block = orig.block
                    free_booking.free_class = False
                    free_booking.save()
                    ActivityLog.objects.create(
                        log="Booking {} cancelled from block {} (user {}); "
                            "free booking {} moved to parent block".format(
                            self.id, orig.block.id, self.user.username,
                            free_booking.id
                        )
                    )
                else:
                    free_class_block.delete()
                    ActivityLog.objects.create(
                        log="Booking {} cancelled from block {} (user {}); unused "
                            "free class block deleted".format(
                            self.id, orig.block.id, self.user.username
                        )
                    )
            self.block = None
            self.paid = False
            self.payment_confirmed = False

        if cancellation:
            # reset reminder and warning flags on cancel
            self.reminder_sent = False
            self.warning_sent = False
            self.date_warning_sent = None

        if self.block and self.block.block_type.identifier == 'free class':
            self.free_class = True

        if self.free_class or self.block:
            self.paid = True
            self.payment_confirmed = True

        if self.payment_confirmed and not self.date_payment_confirmed:
            self.date_payment_confirmed = timezone.now()

        if self.warning_sent and not self.date_warning_sent:
            self.date_warning_sent = timezone.now()

        if self.status == "CANCELLED":
            # can't be both cancelled and no-show
            self.no_show = False

        if not self.no_show:
            # make sure instructor_confirmed_no_show is always False if no_show is False
            self.instructor_confirmed_no_show = False

        # Done with changes to current booking; call super to save the
        # booking so we can check block status
        super(Booking, self).save(*args, **kwargs)


@receiver(post_save, sender=Booking)
def update_free_blocks(sender, instance, **kwargs):
    # saving open booking block booking where block is no longer active (i.e. just
    # used last in block) and block allows creation of free class on completetion,
    if instance.status == 'OPEN' \
        and instance.block \
            and instance.block.block_type.assign_free_class_on_completion \
                and instance.block.paid \
                    and not instance.block.active_block():

        free_blocktype, _ = BlockType.objects.get_or_create(
            identifier='free class', event_type=instance.block.block_type.event_type,
            defaults={
                'size': 1, 'cost': 0, 'duration': 1, 'active': False,
                'assign_free_class_on_completion': False
            }
        )

        # User just used last block in block that credits free classes on completion;
        # check for free class block, add one if doesn't exist already (unless block has already expired)
        if not instance.block.children.exists() and not instance.block.expired:
            free_block = Block.objects.create(
                user=instance.user, parent=instance.block,
                block_type=free_blocktype
            )
            ActivityLog.objects.create(
                log='Free class block created with booking {}. '
                    'Block id {}, parent block id {}, user {}'.format(
                        instance.id,
                        free_block.id, instance.block.id,
                        instance.user.username
                    )
            )


class WaitingListUser(models.Model):
    """
    A model to represent a single user on a waiting list for an event
    """
    user = models.ForeignKey(
        User, related_name='waitinglists', on_delete=models.CASCADE
    )
    event = models.ForeignKey(
        Event, related_name='waitinglistusers', on_delete=models.CASCADE
    )
    # date user joined the waiting list
    date_joined = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'event'])
        ]


class TicketedEvent(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    date = models.DateTimeField()
    location = models.CharField(max_length=255, default="Watermelon Studio")
    max_tickets = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Leave blank if no max number"
    )
    contact_person = models.CharField(max_length=255, default="Gwen Holbrey")
    contact_email = models.EmailField(default=settings.DEFAULT_STUDIO_EMAIL)
    ticket_cost = models.DecimalField(default=0, max_digits=8, decimal_places=2)
    advance_payment_required = models.BooleanField(default=True)
    show_on_site = models.BooleanField(
        default=True, help_text="Tick to show on the site and allow ticket bookings")
    payment_open = models.BooleanField(default=True)
    payment_info = models.TextField(blank=True)
    payment_due_date = models.DateTimeField(
        null=True, blank=True,
        help_text='Tickets that are not paid by the payment due date '
                  'will be automatically cancelled (a warning email will be '
                  'sent to users first).')
    payment_time_allowed = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Number of hours allowed for payment after booking (after "
                  "this ticket purchases will be cancelled.  Note that the "
                  "automatic cancel job allows 6 hours after booking, so "
                  "6 hours is the minimum time that will be applied."
    )
    email_studio_when_purchased = models.BooleanField(default=False)
    max_ticket_purchase = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Limit the number of tickets that can be "
                             "purchased at one time"
    )
    extra_ticket_info_label = models.CharField(
        max_length=255, blank=True, default=''
    )
    extra_ticket_info_help = models.CharField(
        max_length=255, blank=True, default='',
        help_text="Description/details/help text to display under the extra "
                  "info field"
    )
    extra_ticket_info_required = models.BooleanField(
        default=False,
        help_text="Tick if this information is mandatory when booking tickets"
    )
    extra_ticket_info1_label = models.CharField(
        max_length=255, blank=True, default=''
    )
    extra_ticket_info1_help = models.CharField(
        max_length=255, blank=True, default='',
        help_text="Description/details/help text to display under the extra "
                  "info field"
    )
    extra_ticket_info1_required = models.BooleanField(
        default=False,
        help_text="Tick if this information is mandatory when booking tickets"
    )
    cancelled = models.BooleanField(default=False)
    slug = AutoSlugField(populate_from='name', max_length=40, unique=True)
    paypal_email = models.EmailField(
        default="thewatermelonstudio@hotmail.com",
        help_text='Email for the paypal account to be used for payment.  '
                  'Check this carefully!'
    )

    class Meta:
        ordering = ['-date']

    def tickets_left(self):
        if self.max_tickets:
            ticket_bookings = TicketBooking.objects.filter(
                ticketed_event__id=self.id, cancelled=False,
                purchase_confirmed=True
            )
            booked_number = Ticket.objects.filter(
                ticket_booking__in=ticket_bookings
            ).count()
            return self.max_tickets - booked_number
        else:
            # if there is no max_tickets, return an unfeasibly high number
            return 10000

    def bookable(self):
        return self.tickets_left() > 0

    def __str__(self):
        return '{} - {}'.format(
            str(self.name),
            self.date.astimezone(
                pytz.timezone('Europe/London')
            ).strftime('%d %b %Y, %H:%M')
        )

    def save(self, *args, **kwargs):
        if not self.ticket_cost:
            self.advance_payment_required = False
            self.payment_open = False
            self.payment_due_date = None
            self.payment_time_allowed = None
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
        if self.payment_time_allowed:
            self.advance_payment_required = True
        super(TicketedEvent, self).save(*args, **kwargs)


class TicketedEventWaitingListUser(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ticketed_event_waiting_lists")
    ticketed_event = models.ForeignKey(
        TicketedEvent, related_name="waiting_list_users", on_delete=models.CASCADE
    )
    date_joined = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.user.username} - {self.ticketed_event}"


class TicketBooking(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ticket_bookings")
    ticketed_event = models.ForeignKey(
        TicketedEvent, related_name="ticket_bookings", on_delete=models.CASCADE
    )
    date_booked = models.DateTimeField(default=timezone.now)
    paid = models.BooleanField(default=False)

    # cancelled flag so we can cancel unpaid ticket purchases
    # do not allow reopening of cancelled ticket bookings
    cancelled = models.BooleanField(default=False)

    # Flags for email reminders and warnings
    reminder_sent = models.BooleanField(default=False)
    warning_sent = models.BooleanField(default=False)
    date_warning_sent = models.DateTimeField(null=True, blank=True)

    booking_reference = models.CharField(max_length=255)
    purchase_confirmed = models.BooleanField(default=False)

    # stripe payments
    invoice = models.ForeignKey("stripe_payments.Invoice", on_delete=models.SET_NULL, null=True, blank=True, related_name="ticket_bookings")
    checkout_time = models.DateTimeField(null=True, blank=True)

    def set_booking_reference(self):
        self.booking_reference = shortuuid.ShortUUID().random(length=22)

    def mark_checked(self):
        self.checkout_time = timezone.now()
        self.save()

    @property
    def cost(self):
        return Decimal(
            self.ticketed_event.ticket_cost * self.tickets.count()
        ).quantize(Decimal(".01"))

    def __str__(self):
        return 'Booking ref {} - {} - {}'.format(
            self.booking_reference, self.ticketed_event.name, self.user.username
        )

    def save(self, *args, **kwargs):
        if self.pk is None:
            if self.ticketed_event.tickets_left() <= 0:
                raise TicketBookingError(
                    'No tickets left for {}'.format(self.ticketed_event)
                )
            self.set_booking_reference()
        if self.warning_sent and not self.date_warning_sent:
            self.date_warning_sent = timezone.now()
        super(TicketBooking, self).save(*args, **kwargs)


class Ticket(models.Model):
    extra_ticket_info = models.TextField(blank=True, default='')
    extra_ticket_info1 = models.TextField(blank=True, default='')
    ticket_booking = models.ForeignKey(
        TicketBooking, related_name="tickets", on_delete=models.CASCADE
    )

    def save(self, *args, **kwargs):
        # raise error for each ticket creation also if we try to book for a
        #  full event
        if self.pk is None:
            if self.ticket_booking.ticketed_event.tickets_left() <= 0:
                raise TicketBookingError(
                    'No tickets left for {}'.format(
                        self.ticket_booking.ticketed_event
                    )
                )
        super(Ticket, self).save(*args, **kwargs)


class BaseVoucher(models.Model):
    discount = models.PositiveIntegerField(
        help_text="Enter a number between 1 and 100"
    )
    start_date = models.DateTimeField(default=timezone.now)
    expiry_date = models.DateTimeField(null=True, blank=True)
    max_vouchers = models.PositiveIntegerField(
        null=True, blank=True, verbose_name='Maximum available vouchers',
        help_text="Maximum uses across all users")
    max_per_user = models.PositiveIntegerField(
        null=True, blank=True, default=1,
        verbose_name="Maximum uses per user",
        help_text="Maximum times this voucher can be used by a single user"
    )
    # for gift vouchers
    is_gift_voucher = models.BooleanField(default=False)
    activated = models.BooleanField(default=True)
    name = models.CharField(null=True, blank=True, max_length=255, help_text="Name of recipient")
    message = models.TextField(null=True, blank=True, max_length=500, help_text="Message (max 500 characters)")
    purchaser_email = models.EmailField(null=True, blank=True)

    # stripe payments
    checkout_time = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.code

    def mark_checked(self):
        self.checkout_time = timezone.now()
        self.save()

    @cached_property
    def has_expired(self):
        if self.expiry_date and self.expiry_date < timezone.now():
            return True
        return False

    @cached_property
    def has_started(self):
        return bool(self.start_date < timezone.now() and self.activated)

    def save(self, *args, **kwargs):
        # replace start time with very start of day
        self.start_date = self.start_date.replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        if self.expiry_date:
            # replace time with very end of day
            # move forwards 1 day and set hrs/min/sec/microsec to 0, then move
            # back 1 sec
            next_day = (self.expiry_date + timedelta(
                days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            self.expiry_date = next_day - timedelta(seconds=1)
        super(BaseVoucher, self).save(*args, **kwargs)


class EventVoucher(BaseVoucher):
    code = models.CharField(max_length=255, unique=True)
    event_types = models.ManyToManyField(EventType)

    # stripe payments
    invoice = models.ForeignKey(
        "stripe_payments.Invoice", on_delete=models.SET_NULL, null=True, blank=True, 
        related_name="event_gift_vouchers"
    )

    def check_event_type(self, ev_type):
        return bool(ev_type in self.event_types.all())
    
    def valid_for(self):
        return self.event_types.all()
    
    @property
    def gift_voucher_type(self):
        if self.is_gift_voucher:
            if not self.event_types.exists():
                raise ValueError("Event gift voucher must define at least one applicable event type")
            gvts = GiftVoucherType.objects.filter(event_type=self.event_types.first())
            if not gvts.exists():
                # In case this was a manually created gift voucher, make sure we can return 
                # a valid gift voucher type, but don't make an active one
                gvt = GiftVoucherType.objects.create(event_type=self.event_types.first(), active=False)
            else:
                gvt = gvts.first()
            return gvt


class BlockVoucher(BaseVoucher):
    code = models.CharField(max_length=255, unique=True)
    block_types = models.ManyToManyField(BlockType)
    
    # stripe payments
    invoice = models.ForeignKey(
        "stripe_payments.Invoice", on_delete=models.SET_NULL, null=True, blank=True, 
        related_name="block_gift_vouchers"
    )

    def check_block_type(self, block_type):
        return bool(block_type in self.block_types.all())

    @property
    def gift_voucher_type(self):
        if self.is_gift_voucher:
            if not self.block_types.exists():
                raise ValueError("Block gift voucher must define at least one applicable block type")
            gvts = GiftVoucherType.objects.filter(block_type=self.block_types.first())
            if not gvts.exists():
                gvt = GiftVoucherType.objects.create(block_type=self.block_types.first(), active=False)
            else:
                gvt = gvts.first()
            return gvt


class UsedEventVoucher(models.Model):
    voucher = models.ForeignKey(EventVoucher, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    booking_id = models.CharField(max_length=20, null=True, blank=True)


class UsedBlockVoucher(models.Model):
    voucher = models.ForeignKey(BlockVoucher, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    block_id = models.CharField(max_length=20, null=True, blank=True)


class GiftVoucherType(models.Model):
    block_type = models.ForeignKey(
        BlockType, null=True, blank=True, on_delete=models.SET_NULL, related_name="block_gift_vouchers"
    )
    event_type = models.ForeignKey(
        EventType, null=True, blank=True, on_delete=models.SET_NULL, related_name="event_gift_vouchers"
    )
    active = models.BooleanField(default=True, help_text="Display on site; set to False instead of deleting unused voucher types")

    @cached_property
    def cost(self):
        if self.block_type:
            return self.block_type.cost
        else:
            last_event = Event.objects.filter(event_type=self.event_type).latest("id")
            return last_event.cost

    def clean(self):
        if not self.block_type and not self.event_type:
            raise ValidationError({'block_type': _('One of Block Type or Event Type is required.')})
        elif self.block_type and self.event_type:
            raise ValidationError({'event_type': _('Only one of Block Type or Event Type can be set.')})

    def __str__(self):
        return f"{self.name} - £{self.cost}"

    @property
    def name(self):
        if self.block_type:
            return f"Gift voucher: {self.block_type.event_type.subtype} - {self.block_type.size} classes"
        else:
            return f"Gift voucher: {self.event_type}"


class Banner(models.Model):
    banner_type = models.CharField(
        max_length=10, 
        choices=(("banner_all", "all users banner"), ("banner_new", "new users banner")),
        default="banner_all"
    )
    content = models.TextField()
    start_datetime = models.DateTimeField(default=timezone.now)
    end_datetime = models.DateTimeField(null=True, blank=True)
    colour = models.CharField(
        max_length=10, 
        choices=(
            ("info", "light blue"),
            ("primary", "blue"), 
            ("success", "green"), 
            ("warning", "yellow"), 
            ("danger", "red"),
            ("secondary", "light grey"),
            ("dark", "dark grey")
        ),
        default="info"
    )

    def __str__(self) -> str:
        return f"{self.banner_type}"
