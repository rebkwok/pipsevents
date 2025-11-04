
from datetime import datetime
from dateutil.relativedelta import relativedelta
import logging
import re

from django.core.validators import RegexValidator
from django.db import models
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from django.utils import timezone

from activitylog.models import ActivityLog
from booking.models import EventType
from stripe_payments.utils import StripeConnector, get_first_of_next_month_from_timestamp

logger = logging.getLogger(__name__)



class MembershipManager(models.Manager):
    def purchasable(self):
        return self.get_queryset().filter(visible=True, active=True, membership_items__id__isnull=False).distinct()
    

class Membership(models.Model):
    """
    Represents a Stripe Product for a monthly Membership plan.
    Holds info about number of eligible classes and their types per month (via MembershipItems)

    Price represents the current active price for the membership, denoted on Stripe by the
    stripe_price_id.
    Price can be changed; if it is, then we make a new stripe Price, set it to the default for this
    product, update the stripe_price_id
    """ 
    name = models.TextField()
    stripe_product_id = models.SlugField()
    description = models.TextField(null=True, blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    stripe_price_id = models.TextField(null=True)
    visible = models.BooleanField(
        default=True,
        help_text="Visible and available for purchase on site"
    )
    active = models.BooleanField(
        default=True, 
        help_text="Active on Stripe"
    )

    objects = MembershipManager()

    class Meta:
        ordering = ("id",)

    def __str__(self) -> str:
        return f"{self.name} - £{self.price}"
    
    def generate_stripe_product_id(self):
        slug = slugify(self.name)
        counter = 1
        while Membership.objects.filter(stripe_product_id=slug).exists():
            slug_without_counter = re.sub(r"(_\d+$)", "", slug)
            slug = f"{slug_without_counter}_{counter}"
            counter += 1
        return slug

    def active_user_memberships(self):
        not_cancelled_yet = self.user_memberships.filter(
            models.Q(subscription_status__in=["active", "past_due", "setup_pending"])
         & (models.Q(end_date__isnull=True) | models.Q(end_date__gt=timezone.now()))
        )
        results = {
            "all": [], "ongoing": [], "cancelling": []
        }
        for user_membership in not_cancelled_yet:
            if user_membership.is_active():
                if user_membership.end_date is None:
                    results["ongoing"].append(user_membership)
                else:
                    results["cancelling"].append(user_membership)
                results["all"].append(user_membership)
        return results

    def save(self, *args, **kwargs):
        stripe_client = StripeConnector()
        price_changed = False

        if not self.active:
            # Inactive stripe memberships cannot be visible/purchasable
            self.visible = False

        if not self.id:
            self.stripe_product_id = self.generate_stripe_product_id()
            # create stripe product with price
            product = stripe_client.create_stripe_product(
                product_id=self.stripe_product_id,
                name=self.name,
                description=self.description,
                price=self.price,
            )
            self.stripe_price_id = product.default_price
        else:
            # pre-save object
            presaved = Membership.objects.get(id=self.id)
            changed = False
            if self.price != presaved.price:
                # if price has changed, create new Price and update stripe price ID
                price_id = stripe_client.get_or_create_stripe_price(self.stripe_product_id, self.price)
                self.stripe_price_id = price_id
                changed = True
                price_changed = True
            if self.name != presaved.name or self.description != presaved.description or self.active != presaved.active:
                changed = True 
            if changed:
                stripe_client.update_stripe_product(
                    product_id=self.stripe_product_id,
                    name=self.name,
                    description=self.description,
                    active=self.active,
                    price_id=self.stripe_price_id,
                )
                if price_changed:
                    ActivityLog.objects.create(
                        log=f"Stripe price updated on membership {self.id} ({self.stripe_product_id}): from £{presaved.price} to £{self.price}"
                    )
                    # Archive the old price
                    stripe_client.archive_stripe_price(presaved.stripe_price_id)
        super().save(*args, **kwargs)

        if price_changed:
            # update user memberships from this month (with stripe_client.update_subscription_price())
            for user_membership in self.user_memberships.filter(end_date__isnull=True):
                if user_membership.is_active():
                    stripe_client.update_subscription_price(
                        subscription_id=user_membership.subscription_id, new_price_id=self.stripe_price_id
                    )
                    ActivityLog.objects.create(log=f"User membership for user {user_membership.user} updated for price change on membership {self.id}")

    
    def delete(self, *args, **kwargs):
        assert not self.user_memberships.exists(), f"Attempted to delete membership (id {self.id}) with purchased user memberships"
        stripe_client = StripeConnector()
        stripe_client.archive_stripe_product(self.stripe_product_id, self.stripe_price_id)
        super().delete(*args, **kwargs)


class MembershipItem(models.Model):
    """
    Number of eligible classes of a specific event_type per month for a membership_type
    """
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="membership_items")
    event_type = models.ForeignKey(EventType, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(null=True, help_text="Number allowed per month")

    class Meta:
        unique_together = ("membership", "event_type")

    def __str__(self) -> str:
        return f"{self.event_type.subtype} x {self.quantity}"
    

class UserMembership(models.Model):
    """
    Holds info about user memberships

    Created in the stripe webhook when a customer.subscription.create event is received

    Subscription ID, Membership and User should never change after initial creation
    (MembershipPrice could change on a Membership)
    A change of membership plan sets the end date on the current one and creates a new
    UserMembership with the start of the next one.

    Start date and end date refer to the MEMBERSHIP (not to the stripe subscription) and
    are used to determine whether a UserMembership with an active stripe subscription is
    valid for use for a class on a particular date.  (Membership is used to verify that
    it is valid for the class event_type.) They will always be the 1st of a month.

    A user can have at most 1 active UserMemberships for any one period
    start date now or 1st of next month; pricing charges on 25th
    A user can have more than one UserMembership, but only one that is current at any one time
    There should only be one UserMembershp
                    
    subscription_id should be unique on UserMembership. If plan (membership) changes (on user request), the current
    subscription is cancelled and a new subscription is created. Changes to the price of a membership will
    result in a subscription update webhook event, but don't change anything on the UserMembership.

    status refers to current status on Stripe of subscription
    To verify if this membership is valid, check start/end dates as well as subscription status

    eg. 1) User buys membership A on 12th April; to start this month
    Create UserMembership with start date 1st April
    end date = None
    status = incomplete; once paid, updates to active
     
    e.g. 2) User buys membership A on 12th April; to start next month
    Create UserMembership with start date 1st May
    end date = None
    status = incomplete; once setup intent succeeds, updates to active

    e.g. 3) User upgrades to Membership B
    Cancel this subscription from end of current period, set end date to 1st of next month (checks on class date will check it is < end date (exclusive))
    Create new UserMembership and a new stripe subscription (using the payment method from the previous one), for Membership B, start 1st next month
    Move all bookings for next month from previous UserMembership to new one. 
    Check for unpaid bookings for next month and apply new UserMembership
    
    e.g. 4) User downgrades to Membership C
    Cancel this subscription from end of current period, set end date to 1st of next month (checks on class date will check it is < end date (exclusive))
    Create new UserMembership and a new stripe subscription (using the payment method from the previous one), for Membership C, start 1st next month
    Move all bookings for next both from previous UserMembership to new one where possible. Mark any that
    can't be applied (due to reduced usage) to unpaid (ordered by event date).
    
    e.g. 5) User cancels membership
    Cancel subscription from end of period. 
    Set end date of this UserMembership to to 1st of next month
    (webhook will set status when it actually changes)
    """
    membership = models.ForeignKey(Membership, related_name="user_memberships", on_delete=models.CASCADE)
    user = models.ForeignKey("auth.User", related_name="memberships", on_delete=models.CASCADE)

    # Membership dates (always the 1st). End date is None for ongoing memberships.
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(null=True, blank=True)

    # stripe data
    # https://docs.stripe.com/api/subscriptions/object
    subscription_id = models.TextField(null=True)
    subscription_status = models.TextField(null=True)  
    # FROM STRIPE (initial subscriptions):
    # - incomplete: backdated subscription, invoice not yet paid
    # - incomplete_expired: backdated subscription, invoice not paid within 23 hrs
    # - active: backdated subscription paid, OR starts in future, OR ongoing and paid
    # - past_due: offline invoice payment attempt failed
    # - unpaid?
    # - cancelled
    # PLUS:
    # setup_pending: non-backdated subscription, setup intent not yet succeded (stripe status = active)

    # This are the start/end dates of the Stripe subscription end date (usually 25th)
    # start date may be < 25th if a subscription was set up to start in the future
    # in this case the billing_cycle_anchor is the start date for payment purposes
    subscription_start_date = models.DateTimeField()
    subscription_end_date = models.DateTimeField(null=True, blank=True)
    subscription_billing_cycle_anchor = models.DateTimeField()

    # Allow manual overrides of local start date/subscription; this will prevent the local subscription
    # being updated to stripes version of events
    # E.g. user accidentally starts in Feb instead of March; we apply a discount for the full amount to
    # March to compensate, and manually update the start date so they can't book Feb classes
    # OR manually set status to paused; apply X months full vouchers to allow membership to be free while
    # paused
    override_start_date = models.DateTimeField(
        null=True, blank=True,
        help_text=(
            "Set a manual start date; must be the 1st of a month. Actual start date from Stripe will be ignored. "
            "Note that this affects users' ability to book classes ONLY, not payments. "
            "Changing this date will not update any bookings that have already been made."
        )
    )
    override_subscription_status = models.TextField(
        null=True, blank=True,
        help_text=(
            "Set a manual subscription status; usually this will be used only to manually make a subscription"
            "paused. Note that this affects users' ability to book classes ONLY, not payments. To also pause"
            "payment, you need to add a 100% discount to the subscription for the relevant number of months."
        )
    )

    # Use to store setup intent for subscriptions set to start in the future so we can retrieve
    # them in the stripe webhook and move the subscription to active
    pending_setup_intent = models.TextField(null=True, blank=True)

    # stripe status to user-friendly format
    HR_STATUS = {
        "incomplete": "Incomplete",
        "incomplete_expired": "Expired",
        "active": "Active",
        "past_due": "Overdue",
        "canceled": "Cancelled",
        "unpaid": "Unpaid",
        "setup_pending": "Incomplete",
        "paused": "Paused",
    }

    class Meta:
        ordering = ("subscription_status", "-start_date",)

    def __str__(self) -> str:
        return f"{self.user} - {self.membership.name}"

    def clean(self):
        if self.override_subscription_status and self.override_subscription_status not in self.HR_STATUS:
            raise ValidationError(f"Invalid status '{self.override_subscription_status}'")
        return super().clean()

    @classmethod
    def active_memberships(cls):
        return cls.objects.filter(
            # active/past due statuses are active (past due is auto-cancelled on 28th, so we can assume all past dues are valid)
            models.Q(subscription_status__in=["active", "past_due"]) | 
            # cancelled can be valid, if the start date is before now, and end date is after now
            models.Q(
                subscription_status="canceled",
                end_date__gt=timezone.now(),
                start_date__lt=timezone.now()
            )
        )

    @classmethod
    def active_member_ids(cls):
        """
        Return a list of IDs for users who have an active membership
        """
        valid_subscriptions = cls.active_memberships()
        return set(valid_subscriptions.values_list("user_id", flat=True))

    def is_active(self):
        # Note active doesn't mean valid for a particular class and date
        # A subscription that hasn't started yet is considered active
        if self.subscription_status == "active":
            return True
        if self.subscription_status == "past_due":
            # past_due is allowed until the 28th of the month (after which past due subscriptions get cancelled)
            return datetime.now().day <= 28
        # Subscription can be in cancelled state but still active until the end of the month
        # They can also be created to start in the future and then cancelled before they billed - in this case
        # start and end date are the same and it's not active
        if self.subscription_status == "canceled":
            now = timezone.now()
            return self.end_date is not None and self.start_date < now < self.end_date
        return False
    
    def valid_for_event(self, event):
        if not self.is_active():
            return False
        
        membership_item = self.membership.membership_items.filter(event_type=event.event_type).first()
        if not membership_item:
            return False
        
        if event.date < self.start_date:
            return False
        
        if self.end_date and self.end_date < event.date:
            return False
    
        # check quantities of classes already booked with this membership for this event type in the same month
        allowed_numbers = membership_item.quantity
        open_booking_count = self.bookings.filter(
            event__event_type=event.event_type, event__date__month=event.date.month, event__date__year=event.date.year, 
            status="OPEN"
        ).count()
        return open_booking_count < allowed_numbers

    def hr_status(self):
        return self.HR_STATUS.get(self.subscription_status, self.subscription_status.title())

    def bookings_this_month(self):
        return self.bookings.filter(status="OPEN", event__date__month=datetime.now().month, event__date__year=datetime.now().year)
    
    def bookings_next_month(self):
        next_month = ((datetime.now().month - 12) % 12) + 1
        year = datetime.now().year + 1 if next_month == 1 else datetime.now().year
        return self.bookings.filter(status="OPEN", event__date__month=next_month, event__date__year=year)
    
    def payment_has_started(self):
        if self.subscription_start_date.day < 25:
            first_subscription_payment_date = self.subscription_start_date.replace(day=25)
        else:
            first_subscription_payment_date = self.subscription_start_date
        return first_subscription_payment_date < timezone.now()

    @classmethod
    def calculate_membership_end_date(cls, end_date=None):
        if not end_date:
            return
        return get_first_of_next_month_from_timestamp(end_date.timestamp())

    def _reallocate_existing_booking(self, booking, other_active_memberships):
        # no-show or cancelled bookings are just set to no membership and unpaid
        if booking.no_show or booking.status == "CANCELLED":
            booking.membership = None
            booking.paid = False
            booking.payment_confirmed = False
            booking.save()
            return booking
        # assign to first valid membership
        for membership in other_active_memberships:
            if membership.valid_for_event(booking.event):
                booking.membership = membership
                booking.paid = True
                booking.payment_confirmed = True
                booking.save()
                ActivityLog.objects.create(
                    log=f"Reallocated booking {booking.id} (user {self.user.username}) to membership {membership}"
                )
                return booking
        # assign to first valid block
        active_block = booking.get_next_active_block()
        if active_block is not None:
            booking.membership = None
            booking.block = active_block
            booking.paid = True
            booking.payment_confirmed = True
            booking.save()
            ActivityLog.objects.create(
                log=f"Reallocated booking {booking.id} (user {self.user.username}) to block {active_block.id}"
            )
            return booking
        # no valid membership or block, set to None
        booking.membership = None
        booking.paid = False
        booking.payment_confirmed = False
        booking.save()
        ActivityLog.objects.create(
            log=f"Booking {booking.id} (user {self.user.username}) for cancelled membership set to unpaid"
        )
        return booking

    def reallocate_bookings(self):
        """
        1) Check user's membership for bookings that shouldn't be there and reallocate if possible
            i.e.
            After cancellation ( if status == cancelled or end_date) of a UserMembership, find all booking for events after the
            end_date and:
            - transfer to another available membership
            - transfer other available block(s)
            - mark as unpaid

        2) Check user's bookings for unpaid bookings and allocate to this membership if possible
            i.e. after successful set up of a subscription, allocate any unpaid bookings
            - confirm subscription is in active state first and has no end date (set on payment for backdated, and on
            setup intent confirmation for non-backdated)
        """        
        if self.end_date:
            # check for open bookings for events after the end date and reallocate
            bookings_after_end_date = self.bookings.filter(event__date__gt=self.end_date)
            other_active_memberships = self.user.memberships.filter(subscription_status="active")
            for booking in bookings_after_end_date:
                booking = self._reallocate_existing_booking(booking, other_active_memberships)

        elif self.subscription_status == "active":
            # check for unpaid bookings that this membership is eligible for and assign the membership to it
            unpaid_bookings = self.user.bookings.filter(event__date__gt=self.start_date, paid=False, status="OPEN", no_show=False)
            for booking in unpaid_bookings:
                if self.valid_for_event(booking.event):
                    booking.membership = self
                    booking.paid = True
                    booking.payment_confirmed = True
                    booking.save()
                    ActivityLog.objects.create(
                        log=f"Unpaid booking {booking.id} (user {self.user.username}) allocated to membership"
                    )


class StripeSubscriptionVoucher(models.Model):
    """
    Holds info about a Stripe Coupon and Promotional Code so we don't have to fetch it from
    Stripe every time to show memberships that have codes available. Stripe handles determining whether a
    particular code is valid.
    """
    code = models.CharField(max_length=50, unique=True, validators=[RegexValidator(r"^[a-zA-Z0-9]+$", message="Alphanumeric characters only")])  
    memberships = models.ManyToManyField(Membership)
    promo_code_id = models.CharField(max_length=255)  # from stripe
    amount_off = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    percent_off = models.FloatField(null=True, blank=True)
    duration = models.CharField(max_length=255, choices=(("once", "once"), ("forever", "forever"), ("repeating", "repeating")), default="once")
    duration_in_months = models.PositiveIntegerField(null=True, blank=True)
    max_redemptions = models.PositiveIntegerField(null=True, blank=True)
    redeem_by = models.DateTimeField(
        null=True, blank=True, 
        help_text=(
            "Date after which users can no longer apply the code; note that once applied, it will apply for the voucher duration, "
            "even if that duration extends beyond the redeem by date. i.e. if a voucher applies for 2 months, and is redeemed on the "
            "redeem by date, it will still apply for the next 2 months' membership. If you want to override this behaviour, set an "
            "expiry date as well."
        )
    )
    expiry_date = models.DateTimeField(
        null=True, blank=True,
        help_text=(
            "Date after which the code will be removed from any memberships that have currently applied it."
        )
    )
    active = models.BooleanField(default=True)
    # Apppy to new subscriptions only; this is not a Stripe-handled restriction (Stripe has 'first_time_transaction' restriction on
    # promo codes, but they are customer-based, not product-based)
    new_memberships_only = models.BooleanField(
        default=True, help_text="Valid for new memberships only"
    )

    class Meta:
        ordering = ("-active", "-expiry_date", "-redeem_by")

    def __str__(self) -> str:
        return self.code

    def expired(self):
        if self.redeem_by:
            return self.redeem_by < timezone.now()
        return False

    @property
    def description(self):
        suffix = ""
        if self.expiry_date:
            suffix = f" (expires on {self.expiry_date.strftime('%d-%b-%Y')})"

        if self.amount_off:
            discount = f"£{self.amount_off} off"
        else:
            discount = f"{self.percent_off}% off" 

        match self.duration:
            case "once":
                return f"{discount} one month's membership{suffix}"
            case "forever":
                return f"{discount}{suffix}"
            case "repeating":
                return f"{discount} {self.duration_in_months} months membership{suffix}"

    def save(self, *args, **kwargs):
        presaved = None
        if not self.id:
            self.code = self.code.lower()
        else:
            presaved = StripeSubscriptionVoucher.objects.get(id=self.id)
        if self.expiry_date:
            self.expiry_date.replace(hour=23, minute=59)
        super().save(*args, **kwargs)
        stripe_client = StripeConnector()
        if presaved:
            if presaved.active != self.active:
                stripe_client.update_promo_code(self.promo_code_id, active=self.active)
                change = "unarchived" if self.active else "archived"
                ActivityLog.objects.create(
                log=f"Stripe promo code {self.code} {change}"
            )

    def create_stripe_code(self):
        if self.memberships.exists():
            stripe_client = StripeConnector()
            promo_code = stripe_client.create_promo_code(
                self.code, 
                list(self.memberships.values_list("stripe_product_id", flat=True)),
                amount_off=int(self.amount_off * 100) if self.amount_off else None,
                percent_off=self.percent_off,
                duration=self.duration,
                duration_in_months=self.duration_in_months,
                max_redemptions=self.max_redemptions,
                redeem_by=int(self.redeem_by.timestamp()) if self.redeem_by else None
            )
            ActivityLog.objects.create(
                log=f"Stripe promo code {self.code} created"
            )
            self.promo_code_id = promo_code.id
            self.save()

    def expires_before_next_payment_date(self):
        if not self.expiry_date:
            return False
        now = timezone.now()
        if now.day >= 25:
            next_payment_date = (now + relativedelta(months=1)).replace(day=25)
        else:
            next_payment_date = now.replace(day=25)
        return self.expiry_date < next_payment_date

    @property
    def applied_description(self):
        if self.amount_off:
            return f"£{self.amount_off:.2f}"
        assert self.percent_off
        return f"{self.percent_off:.0f}%"
