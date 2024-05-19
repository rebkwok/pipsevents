
import logging
import re

from django.db import models
from django.utils.text import slugify

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
    # first month discount (changeable, temporarily set first phase of Sub schedule with discount)

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


class MembershipItem(models.Model):
    """
    Number of eligible classes of a specific event_type per month for a membership_type
    """
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="membership_items")
    event_type = models.ForeignKey(EventType, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(null=True, help_text="Number allowed per month; leave blank for unlimited")

    class Meta:
        unique_together = ("membership", "event_type")


class UserMembership(models.Model):
    """
    Holds info about current user membership
    """
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE)
    user = models.ForeignKey("auth.User", on_delete=models.CASCADE)

    # stripe data
    subscription_id = models.TextField(null=True)
    subscription_status = models.TextField(null=True)  # active (paid), overdue, cancelled
    customer_id = models.TextField(null=True)
    
    start_date = models.DateField()
    end_date = models.DateField(null=True)

    #?
    # Create subscription without payment
    # Then create a schedule from it? https://www.youtube.com/watch?v=7z8mncrjq24
    # THEN process payment

    # A user can have at most 1 active UserMemberships
    # start date now or 1st of next month
    # User buys membership on 12th; backdate to 1st, charge monthly, set start date to 1st of this month, end date to None
    # User buys membership on 12th for next month, set start_date to 1st of next month, end_date to None
    # User changes membership plan to a higher tier one, immediately
    # - change membership on current UserMembership
    # - charge one off fee for difference in price from amount paid this month to current new membership price
    # User changes membership plan to a higher tier one, from next month
    # - update subscription schedule with phase starting from next month
    # - when next month's payment is received, update the membership
    # User changes membership plan to a lower tier one, from next month
    # - update subscription schedule with phase starting from next month
    # - reset any extra bookings after current month
    # - when next month's payment is received, update the membership
    # User cancels membership; cancel subscription. 


    # options for user to change
    # cancel membership - cancel on stripe, set end_date to end of month, remove from bookings if necessary
    # upgrade membership (from next month or immediately; if immediately, charge one-off for difference)
    # downgrade membership (from next month; remove bookings if necessary)

    # This is created when the stripe event is received by the webhook
    # User can only have one active membership at a time
