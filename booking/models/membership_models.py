
from datetime import datetime
import logging
import re

from django.db import models
from django.utils.text import slugify
from django.utils import timezone

from booking.models import EventType
from stripe_payments.utils import StripeConnector

logger = logging.getLogger(__name__)


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
    active = models.BooleanField(default=True, help_text="Visible and available for purchase on site")

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

    def save(self, *args, **kwargs):
        stripe_client = StripeConnector()
        price_changed = False
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
            # TODO: If price has changed, update UserMemberships with active subscriptions
            # beyond this month (with stripe_client.update_subscription_price())
        super().save(*args, **kwargs)

        if price_changed:
            for user_membership in self.user_memberships.filter(end_date__isnull=True):
                if user_membership.is_active():
                    stripe_client.update_subscription_price(
                        subscription_id=user_membership.subscription_id, new_price_id=self.stripe_price_id
                    )



class MembershipItem(models.Model):
    """
    Number of eligible classes of a specific event_type per month for a membership_type
    """
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="membership_items")
    event_type = models.ForeignKey(EventType, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(null=True, help_text="Number allowed per month; leave blank for unlimited")

    class Meta:
        unique_together = ("membership", "event_type")

    def __str__(self) -> str:
        return f"{self.membership.name} - {self.event_type.subtype} - {self.quantity}"
    

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

    # Membership dates. End date is None for ongoing memberships.
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(null=True)

    # stripe data
    subscription_id = models.TextField(null=True)
    subscription_status = models.TextField(null=True)  # active (paid), overdue, cancelled

    # stripe status to user-friendly format
    HR_STATUS = {
        "incomplete": "Incomplete",
        "incomplete_expired": "Expired",
        "active": "Active",
        "past_due": "Overdue",
        "canceled": "Cancelled",
        "unpaid": "Unpaid",
    }

    class Meta:
        ordering = ("-start_date",)

    def __str__(self) -> str:
        return f"{self.user} - {self.membership.name}"

    def is_active(self):
        # Note active doesn't mean valid for a particular class and date
        if self.subscription_status == "active":
            return True
        if self.subscription_status == "past_due":
            # past_due is allowed until the 28th of the month (after which past due subscriptions get cancelled)
            return datetime.now().day <= 28
        # Subscription can be in cancelled state but still active until the end of the month
        if self.subscription_status == "canceled" and self.end_date is not None and timezone.now() < self.end_date:
            return True
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
        
        # check quantities of classes already booked with this membership for this event type
        allowed_numbers = membership_item.quantity
        open_booking_count = self.bookings.filter(event__event_type=event.event_type, status="OPEN").count()
        return open_booking_count < allowed_numbers

    def hr_status(self):
        return self.HR_STATUS.get(self.subscription_status, self.subscription_status.title())

    def bookings_this_month(self):
        return self.bookings.filter(status="OPEN", event__date__month=datetime.now().month)
    
    def bookings_next_month(self):
        next_month = (datetime.now().month - 12) % 12
        return self.bookings.filter(status="OPEN", event__date__month=next_month)