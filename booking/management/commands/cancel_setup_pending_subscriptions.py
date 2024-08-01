'''
Run hourly?
Cancel all subscriptions with status setup_pending
(First get subscription from stripe and verify that subscription is still setup_pending)
Delete the UserMembership because this never started and can't have been used for
booking - should only be here if a user started setting up a membership and then 
abandoned it.
No emails sent to users.
'''
import logging
from datetime import timedelta
import pytz

from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import get_template
from django.core.management.base import BaseCommand

from booking.models import UserMembership
from booking.views.membership_views import ensure_subscription_up_to_date
from activitylog.models import ActivityLog
from stripe_payments.utils import StripeConnector


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Cancel and delete setup pending subscriptions 23 hrs after creation'

    def handle(self, *args, **options):
        client = StripeConnector()
        setup_pending = UserMembership.objects.filter(subscription_status="setup_pending")
        for user_membership in setup_pending:
            stripe_subscription = client.get_subscription(user_membership.subscription_id)
            user_membership = ensure_subscription_up_to_date(user_membership, stripe_subscription)
            if user_membership.subscription_status == "active":
                continue
            elif user_membership.subscription_status != "setup_pending":
                logger.error("Could not cancel subscription %s in unexpected status %s", user_membership.subscription_id, user_membership.subscription_status)
            else:
                if (timezone.now() - user_membership.subscription_start_date) > timedelta(hours=23):
                    client.cancel_subscription(user_membership.subscription_id, cancel_immediately=True)
                
                    message = f"Setup pending membership {user_membership.membership.name} for {user_membership.user} was unpaid after 23 hrs and has been deleted"
                    ActivityLog.objects.create(log=message)
                    self.stdout.write(message)
                    user_membership.delete()
