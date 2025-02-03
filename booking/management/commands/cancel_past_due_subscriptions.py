'''
Run ON 28th each month
Cancel all subscriptions with status past due
(First get subscription from stripe and verify that subscription is past due)

Email user that their subscription has been cancelled
'''
import logging
from datetime import timedelta
import stripe

from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import get_template
from django.core.management.base import BaseCommand

from booking.models import UserMembership
from booking.views.membership_views import ensure_subscription_up_to_date
from activitylog.models import ActivityLog
from stripe_payments.utils import StripeConnector
from common.management import write_command_name


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Cancel past due subscriptions on 28th each month'

    def handle(self, *args, **options):
        write_command_name(self, __file__)
        client = StripeConnector()
        past_due = UserMembership.objects.filter(subscription_status="past_due")
        for user_membership in past_due:
            stripe_subscription = client.get_subscription(user_membership.subscription_id)
            user_membership = ensure_subscription_up_to_date(user_membership, stripe_subscription)
            if user_membership.subscription_status == "active":
                continue
            elif user_membership.subscription_status != "past_due":
                logger.error("Could not cancel subscription %s in unexpected status %s", user_membership.subscription_id, user_membership.subscription_status)
            else:
                try:
                    client.cancel_subscription(user_membership.subscription_id, cancel_immediately=True)
                    # Don't reallocate bookings because it'll be done in the webhook
                except Exception as err:
                    logger.error(err)
                    self.stdout.write(f"Error cancelling subscription: {str(err)}")
                else:
                    ctx = {
                        'host': "http://booking.thewatermelonstudio.co.uk",
                        'user_membership': user_membership
                    }
                    send_mail(
                        f'{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Your membership has been cancelled',
                        get_template(
                            'booking/email/membership_auto_cancelled_email.txt'
                        ).render(ctx),
                        settings.DEFAULT_FROM_EMAIL,
                        [user_membership.user.email],
                        html_message=get_template(
                            'booking/email/membership_auto_cancelled_email.html'
                            ).render(ctx),
                        fail_silently=False
                    )
                    message = f"Past due membership {user_membership.membership.name} for {user_membership.user} has been cancelled"
                    ActivityLog.objects.create(log=message)
                    self.stdout.write(message)
