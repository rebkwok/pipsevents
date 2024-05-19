from datetime import datetime
import logging
import requests
from dateutil.relativedelta import relativedelta

from django.conf import settings
from django.contrib.sites.models import Site
from django.urls import reverse
import stripe

from activitylog.models import ActivityLog
from .emails import send_processed_payment_emails, send_gift_voucher_email
from .exceptions import StripeProcessingError
from .models import Invoice, Seller


logger = logging.getLogger(__name__)


def get_invoice_from_payment_intent(payment_intent, raise_immediately=False):
    # Don't raise the exception here so we don't expose it to the user; leave it for the webhook
    invoice_id = payment_intent.metadata.get("invoice_id")
    if not invoice_id:
        if raise_immediately:
            raise StripeProcessingError(f"Error processing stripe payment intent {payment_intent.id}; no invoice id")
        return None
    try:
        invoice = Invoice.objects.get(invoice_id=invoice_id)
        if not invoice.username:
            # if there's no username on the invoice, it's from a guest checkout
            # Add the username from the billing email
            billing_email = payment_intent.charges.data[0]["billing_details"]["email"]
            invoice.username = billing_email
            invoice.save()
        return invoice
    except Invoice.DoesNotExist:
        logger.error("Error processing stripe payment intent %s; could not find invoice", payment_intent.id)
        if raise_immediately:
            raise StripeProcessingError(f"Error processing stripe payment intent {payment_intent.id}; could not find invoice")
        return None


def check_stripe_data(payment_intent, invoice):
    signature = payment_intent.metadata.get("invoice_signature")
    if signature != invoice.signature():
        raise StripeProcessingError(
            f"Could not verify invoice signature: payment intent {payment_intent.id}; invoice id {invoice.invoice_id}")

    if payment_intent.amount != int(invoice.amount * 100):
        raise StripeProcessingError(
            f"Invoice amount is not correct: payment intent {payment_intent.id} ({payment_intent.amount/100}); "
            f"invoice id {invoice.invoice_id} ({invoice.amount})"
        )


def process_invoice_items(invoice, payment_method, request=None):
    for booking in invoice.bookings.all():
        booking.paid = True
        booking.payment_confirmed = True
        booking.process_voucher()
        booking.save()

    for ticket_booking in invoice.ticket_bookings.all():
        ticket_booking.paid = True
        ticket_booking.save()

    for block in invoice.blocks.all():
        block.paid = True
        block.process_voucher()
        block.save()

    for gift_voucher in invoice.gift_vouchers:
        gift_voucher.activated = True
        gift_voucher.save()

    invoice.paid = True
    invoice.save()

    # SEND EMAILS
    send_processed_payment_emails(invoice)
    for gift_voucher in invoice.gift_vouchers:
        send_gift_voucher_email(gift_voucher)
    ActivityLog.objects.create(
        log=f"Invoice {invoice.invoice_id} (user {invoice.username}) paid by {payment_method}"
    )


class StripeConnector:
    
    def __init__(self, request=None):
        stripe.api_key = settings.STRIPE_SECRET_KEY
        stripe.max_network_retries = 3
        self.connected_account_id = self.get_connected_account_id(request)

    def get_connected_account_id(self, request=None):
        seller = Seller.objects.filter(site=Site.objects.get_current(request=request)).first()
        return seller.stripe_user_id

    def create_stripe_product(self, product_id, name, description, price):
        price_in_p = int(price * 100)
        try:
            product = stripe.Product.create(
                stripe_account=self.connected_account_id,
                id=product_id,
                name=name,
                description=description,
                default_price_data={
                    "unit_amount": price_in_p,
                    "currency": "gbp",
                    "recurring": {"interval": "month"},
                },
            )
        except stripe.error.InvalidRequestError as e:
            # We use a unique Membership slug as the product id, so we shouldn't attempt to create
            # duplicate products; if we do, it's because we deleted a Membership instance, so
            # reuse the existing Product and make sure it's active and has the details we've
            # just defined
            if "already exists" in str(e):
                price_id = self.get_or_create_stripe_price(product_id, price)
                product = self.update_stripe_product(
                    product_id, name, description, price_id=price_id, active=True 
                )
            else:
                raise
        return product

    def update_stripe_product(self, product_id, name, description, active, price_id):
        product = stripe.Product.modify(
            product_id,
            stripe_account=self.connected_account_id,
            name=name,
            description=description,
            active=active,
            default_price=price_id,
        )
        return product

    def get_or_create_stripe_price(self, product_id, price):
        price_in_p = int(price * 100)
        
        # get existing active Price for this product and amount if one exists
        matching_prices = stripe.Price.list(
            product=product_id, 
            stripe_account=self.connected_account_id, 
            unit_amount=price_in_p, 
            active=True,
            recurring={"interval": "month"}
        )
        if matching_prices.data:
            return matching_prices.data[0].id

        new_price = stripe.Price.create(
            product=product_id,
            stripe_account=self.connected_account_id,
            currency="gbp",
            unit_amount=price_in_p,
            recurring={"interval": "month"},
        )
        return new_price.id

    def get_or_create_stripe_customer(self, user, **kwargs):
        if user.userprofile.stripe_customer_id:
            return user.userprofile.stripe_customer_id

        # Find existing customers by email (Stripe allows more than one)
        customers = stripe.Customer.list(
            stripe_account=self.connected_account_id,
            email=user.email
        )
        if customers.data:
            customer_id = customers.data[0].id
        else:
            # TODO handle card errors if kwargs include payment methods
            customer = stripe.Customer.create(
                name=f"{user.first_name} {user.last_name}",
                email=user.email,
                stripe_account=self.connected_account_id,
                **kwargs
            )
            customer_id = customer.id
        user.userprofile.stripe_customer_id = customer_id
        user.userprofile.save()
        return customer_id

    def update_stripe_customer(self, customer_id, **kwargs):
        # TODO handle card errors if kwargs include payment methods
        stripe.Customer.modify(
            customer_id,
            stripe_account=self.connected_account_id,
            **kwargs
        )
    
    def create_subscription(self, customer_id, price_id):
        """
        The stripe python API doesn't accept stripe_account for subscriptions, so we need to 
        call it directly with the headers
        https://docs.stripe.com/billing/subscriptions/build-subscriptions?platform=web&ui=elements

        subscription = stripe.Subscription.create(
            customer=customer_id,
            items=[{
                'price': price_id,
            }],
            payment_behavior='default_incomplete',  # create subscription as incomplete
            payment_settings={'save_default_payment_method': 'on_subscription'},   # save customer default payment
            expand=['latest_invoice.payment_intent'],
        )

        curl https://api.stripe.com/v1/subscriptions -u : -H "Stripe-Account: acct_1LkrQXBwhuOJbY2i" -d customer=cus_Q8LyvVdwr3AQMg -d "items[0][price]"=price_1PI6o2BwhuOJbY2iLzuO8Vot -d "expand[0]"="latest_invoice.payment_intent"
        """
        url = "https://api.stripe.com/v1/subscriptions"
        headers = {"Stripe-Account": self.connected_account_id}
        auth = (settings.STRIPE_SECRET_KEY, "")
        params = {
            "customer": customer_id,
            "items[0][price]": price_id,
            "expand[0]": "latest_invoice.payment_intent"
        }
        resp = requests.post(url, headers=headers, auth=auth, params=params)
        return resp.json()

    def create_subscription(self, customer_id, price_id, backdate=True):
        """
        Create subscription for this customer and price
        Backdate to 1st of current month if backdate is True
        Start from 1st of next month (billing_cycle_anchor)
        """
        now = datetime.utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        backdate_to = int(month_start.timestamp())
        next_billing_date = int((month_start + relativedelta(months=1)).timestamp())
        subscription = stripe.Subscription.create(
            customer=customer_id,
            items=[{'price': price_id}],
            backdate_start_date=backdate_to,
            billing_cycle_anchor=next_billing_date,
            payment_behavior='default_incomplete',  # create subscription as incomplete
            payment_settings={'save_default_payment_method': 'on_subscription'},   # save customer default payment
            expand=['latest_invoice.payment_intent'],
            stripe_account=self.connected_account_id,
            proration_behavior="none"
        )
        return subscription
    
    def get_or_create_subscription_schedule(self, subscription_id):
        subscription = stripe.Subscription.retrieve(id=subscription_id, stripe_account=self.connected_account_id)
        if subscription.schedule:
            schedule = stripe.SubscriptionSchedule.retrieve(id=subscription.schedule, stripe_account=self.connected_account_id)
        else:
            schedule = stripe.SubscriptionSchedule.create(
                from_subscription=subscription_id,
                stripe_account=self.connected_account_id,
            )
        return schedule

    def update_subscription_price(self, subscription_id, new_price_id):
        """
        For when a Membership price changes
        Create a subscription schedule for each subscription
        Phases = current phase to end of billing period, then new phase with 
        new price
        On next billing period, subscription price will increase.
        """
        # retrieve or create schedule from subscription id
        schedule = self.get_or_create_subscription_schedule(subscription_id)
        # check schedule for end_behvavior
        # if end_behavior is cancel, don't update, it's going to cancel at the end of the current billing period
        if schedule.end_behavior == "release":
            schedule = stripe.SubscriptionSchedule.modify(
                schedule.id,
                end_behvavior="release",
                phases=[
                        {
                            'items': [
                                {
                                    'price': schedule.phases[0]["items"][0].price,
                                    'quantity': schedule.phases[0]["items"][0].quantity,
                                }
                            ],
                            'start_date': schedule.phases[0].start_date,
                            'end_date': schedule.phases[0].end_date,
                        },
                        {
                            'items': [
                                {
                                    'price': new_price_id,
                                    'quantity': 1,
                                }
                            ],
                        },
                    ],
            )

        return schedule
    
    def cancel_subscription(self, subscription_id):
        """
        Always cancel from end of period
        Update schedule to contain only the current phase, and to cancel at the end
        """
        # retrieve or create schedule from subscription id
        schedule = self.get_or_create_subscription_schedule(subscription_id)
        stripe.SubscriptionSchedule.modify(
            schedule.id,
            end_behavior="cancel",
            phases=[
                {
                    'items': [
                        {
                            'price': schedule.phases[0]["items"][0].price,
                            'quantity': schedule.phases[0]["items"][0].quantity,
                        }
                    ],
                    'start_date': schedule.phases[0].start_date,
                    'end_date': schedule.phases[0].end_date,
                    "proration_behavior": "none"
                }
            ],
            stripe_account=self.connected_account_id
        )

    def customer_portal_configuration(self):
        """
        Create a customer portal config to allow updating payment information
        """
        # fetch an active config and make sure it has the correct configuration
        configs = stripe.billing_portal.Configuration.list(stripe_account=self.connected_account_id, active=True)
        config_data = dict(
            business_profile={
                    "privacy_policy_url": "https://booking.thewatermelonstudio.co.uk/data-privacy-policy/",
                    "terms_of_service_url": "https://www.thewatermelonstudio.co.uk/t&c.html",
                },
            features={
                "customer_update": {"allowed_updates": ["email", "name", "address"], "enabled": True},
                "payment_method_update": {"enabled": True},
                "invoice_history": {"enabled": True},
            },
            default_return_url="https://booking.thewatermelonstudio.co.uk/accounts/profile",
            stripe_account=self.connected_account_id,
        )
        if configs.data:
            config_id = configs.data[0].id
            return stripe.billing_portal.Configuration.modify(config_id, **config_data)
        return stripe.billing_portal.Configuration.create(**config_data)
    
    def customer_portal_url(self, customer_id):
        """
        Create a portal session for this user and return a URL that they can use to access it
        This is short-lived; use a view on their account profile to generate it.
        If a subscription renewal fails, send an email with the profile link and ask them
        to update payment method.
        """
        portal = stripe.billing_portal.Session.create(
            customer=customer_id,
            configuration=self.customer_portal_configuration(),
            stripe_account=self.connected_account_id,
        )
        return portal.url
