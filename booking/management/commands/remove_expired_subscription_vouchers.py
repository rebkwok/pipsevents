'''
Find all subscriptions with discounts applied.
Check if discount voucher code expires before next payment date
Remove discount if necessary
'''
import logging
from datetime import timedelta
import stripe

from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import get_template
from django.core.management.base import BaseCommand

from booking.models import UserMembership, StripeSubscriptionVoucher
from booking.views.membership_views import ensure_subscription_up_to_date
from activitylog.models import ActivityLog
from stripe_payments.utils import StripeConnector


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Remove expired discounts'

    def handle(self, *args, **options):
        client = StripeConnector()
        active = UserMembership.objects.filter(subscription_status="active")
        for user_membership in active:
            stripe_subscription = client.get_subscription(user_membership.subscription_id)
            if stripe_subscription.discounts:
                discount = stripe_subscription.discounts[0]
                voucher = StripeSubscriptionVoucher.objects.get(promo_code_id=discount.promotion_code)
                if voucher.expires_before_next_payment_date():
                    client.remove_discount_from_subscription(stripe_subscription.id)
                    self.stdout.write(
                        f"Expired discount code {voucher.code} removed from subscription from user {user_membership.username}"
                    )
