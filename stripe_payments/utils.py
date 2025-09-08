from datetime import datetime, UTC
import logging
from dateutil.relativedelta import relativedelta

from django.conf import settings
from django.contrib.sites.models import Site
from django.urls import reverse
import stripe

from activitylog.models import ActivityLog
from .emails import send_processed_payment_emails, send_gift_voucher_email
from .exceptions import StripeProcessingError
from .models import Invoice, Seller, StripePaymentIntent


logger = logging.getLogger(__name__)


def get_utcdate_from_timestamp(timestamp):
    return datetime.fromtimestamp(timestamp, tz=UTC)

def get_first_of_next_month_from_timestamp(timestamp):
    next_month = get_utcdate_from_timestamp(timestamp) + relativedelta(months=1)
    return next_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)


def get_invoice_from_event_metadata(event_object, raise_immediately=False):
    # Don't raise the exception here so we don't expose it to the user; leave it for the webhook
    # Get the invoice from the event metadata if available
    invoice_id = event_object.metadata.get("invoice_id")
    if not invoice_id:
        # Try to get invoice from a matching payment intent
        # Refunds may be returned with no invoice metadata
        payment_intent = getattr(event_object, "payment_intent", None)
        if payment_intent:
            try:
                return StripePaymentIntent.objects.get(payment_intent_id=payment_intent).invoice
            except StripePaymentIntent.DoesNotExist:
                ...
        # don't raise exception here, it may validly not have an invoice id (e.g. subscriptions)
        return None
    try:
        invoice = Invoice.objects.get(invoice_id=invoice_id)
        if not invoice.username:
            # if there's no username on the invoice, it's from a guest checkout
            # Add the username from the billing email
            billing_email = event_object.charges.data[0]["billing_details"]["email"]
            invoice.username = billing_email
            invoice.save()
        return invoice
    except Invoice.DoesNotExist:
        logger.error("Error processing stripe %s %s; could not find invoice", event_object.object, event_object.id)
        if raise_immediately:
            raise StripeProcessingError(f"Error processing stripe {event_object.object} {event_object.id}; could not find invoice")
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

    # LOG AND SEND EMAILS
    # There is a race condition here between the stripe success view and the
    # webhook. If the webhook is fast enough, both call this method (the webhook
    # checks if the invoice is paid, but it might have been called by the view but
    # not marked paid yet); we don't care
    # that it attemps to set the invoice items again, but we don't want to create
    # duplicate logs or senf duplicate emails.
    _, created = ActivityLog.objects.get_or_create(
        log=f"Invoice {invoice.invoice_id} (user {invoice.username}) paid by {payment_method}"
    )
    if created:
        send_processed_payment_emails(invoice)
        for gift_voucher in invoice.gift_vouchers:
            send_gift_voucher_email(gift_voucher)


def process_completed_stripe_payment(payment_intent, invoice, seller=None, request=None):
    if invoice is None:
        # no invoice == subscription payment (handled with subscription events) or oob payment (direct from stripe)
        # nothing to do
        return
    if not invoice.paid:
        logger.info("Updating items to paid for invoice %s", invoice.invoice_id)
        check_stripe_data(payment_intent, invoice)
        logger.info("Stripe check OK")
        process_invoice_items(invoice, payment_method="Stripe", request=request)
        # update/create the django model PaymentIntent - this is just for records
        StripePaymentIntent.update_or_create_payment_intent_instance(payment_intent, invoice, seller)
    else:
        logger.info(
            "Payment Intents signal received for invoice %s; already processed", invoice.invoice_id
        )


class StripeConnector:
    
    def __init__(self, request=None):
        stripe.api_key = settings.STRIPE_SECRET_KEY
        stripe.max_network_retries = 3
        self.connected_account = None
        self.connected_account_id = self.get_connected_account_id(request)

    def get_connected_account_id(self, request=None):
        self.connected_account = Seller.objects.filter(site=Site.objects.get_current(request=request)).first()
        if self.connected_account:
            return self.connected_account.stripe_user_id
        else:
            raise Seller.DoesNotExist

    def get_test_clocks(self):  # pragma: no cover
        return stripe.test_helpers.TestClock.list(limit=3, stripe_account=self.connected_account_id)
    
    def delete_test_clock(self, clock_id):  # pragma: no cover
        return stripe.test_helpers.TestClock.delete(clock_id, stripe_account=self.connected_account_id)

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

    def archive_stripe_price(self, price_id):
        """Archive a product"""
        # archive the price
        stripe.Price.modify(price_id, product=None, active=False, stripe_account=self.connected_account_id)
    
    def archive_stripe_product(self, product_id, price_id):
        """Archive a product"""
        # archive the product
        product = stripe.Product.modify(product_id, active=False, stripe_account=self.connected_account_id)
        # archive the price
        self.archive_stripe_price(price_id)
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
            # ensure stripe customer exists and is not deleted
            customer = stripe.Customer.retrieve(
                user.userprofile.stripe_customer_id,
                stripe_account=self.connected_account_id,
            ) 
            if customer and not hasattr(customer, "deleted"):
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

    def get_payment_intent(self, payment_intent_id):
        return stripe.PaymentIntent.retrieve(
            id=payment_intent_id, stripe_account=self.connected_account_id
        )
    
    def get_setup_intent(self, setup_intent_id):
        return stripe.SetupIntent.retrieve(
            id=setup_intent_id, stripe_account=self.connected_account_id
        )
    
    def get_subscription(self, subscription_id):
        kwargs = dict(
            id=subscription_id, stripe_account=self.connected_account_id, 
            expand=['latest_invoice.payment_intent', 'latest_invoice.discounts', 'pending_setup_intent', 'schedule', "discounts"]
        )
        return stripe.Subscription.retrieve(**kwargs)

    def get_subscriptions_for_customer(self, customer_id, status="all"):
        subscriptions = stripe.Subscription.list(
            status=status, 
            customer=customer_id, 
            stripe_account=self.connected_account_id,
            expand=['data.discounts', 'data.latest_invoice.payment_intent', 'data.latest_invoice.discounts', 'data.pending_setup_intent'],
        )
        all_subscriptions = {sub["id"]: sub for sub in subscriptions.data}

        while subscriptions["has_more"]:
            subscriptions = stripe.Subscription.list(
                status=status, 
                customer=customer_id, 
                stripe_account=self.connected_account_id,
                expand=['data.latest_invoice.payment_intent', 'data.latest_invoice.discounts', 'data.pending_setup_intent'],
                starting_after=subscriptions.data[-1].id
            )
            all_subscriptions.update({sub["id"]: sub for sub in subscriptions.data})
            
        return all_subscriptions
        

    def get_subscription_cycle_start_dates(self, reference_date=None):
        """
        Return tuple of current start date, next start date and a boolean indicating whether backdating is required for the 
        NEXT month's membership.
        Memberships start on 1st; billing subscription starts on the 25th of the month before.
        If it's currently the 25th or later in the month, we have to backdate in order to subscribe to a membership for the
        next month (and backdating to the previous month is not allowed)  
        reference_date is a datetime and will usually be now
        """
        reference_date = reference_date or datetime.now()
        reference_day = reference_date.day
        if reference_day >= 25:
            # 25th of this month or later
            current_cycle_start_date = reference_date.replace(day=25, hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)
            next_cycle_start_date = current_cycle_start_date + relativedelta(months=1)
            backdate_for_next_month = True
        else:
            next_cycle_start_date = reference_date.replace(day=25, hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)
            current_cycle_start_date = next_cycle_start_date - relativedelta(months=1)
            backdate_for_next_month = False
        return current_cycle_start_date, next_cycle_start_date, backdate_for_next_month

    def get_subscription_kwargs(
        self, customer_id, price_id, backdate=True, default_payment_method=None, discounts=None
    ):
        current_cycle_start_date, next_cycle_start_date, backdate_for_next_month = self.get_subscription_cycle_start_dates()
        
        kwargs = dict(
            customer=customer_id,
            items=[{'price': price_id, 'quantity': 1}],
            default_payment_method=default_payment_method,
            billing_cycle_anchor=int(next_cycle_start_date.timestamp()),
            payment_behavior='default_incomplete',  # create subscription as incomplete
            payment_settings={'save_default_payment_method': 'on_subscription'},   # save customer default payment
            expand=['latest_invoice.payment_intent', 'latest_invoice.discounts', 'pending_setup_intent'],
            stripe_account=self.connected_account_id,
        )
        if backdate_for_next_month or backdate:
            # backdating: backdate to start of current cycle
            # proration invoice will be for the full month
            kwargs["backdate_start_date"] = int(current_cycle_start_date.timestamp())
            kwargs["proration_behavior"] = "create_prorations"
        else:
            # no backdating; set proration to none so stripe doesn't try to collect
            # prorated payment for now to end of cycle
            kwargs["proration_behavior"] = "none"
        
        if discounts:
            kwargs["discounts"] = discounts
        return kwargs


    def create_subscription(self, customer_id, price_id, backdate=True, default_payment_method=None, subscription_kwargs=None):
        """
        Create subscription for this customer and price

        Memberships run for 1 calendar month from 1st month
        Subscriptions run from 25th of the previous month
        i.e. a subscription running from 25th April - 25th May is valid for a membership in May

        Backdate:
        Can only backdate if the current date is < 25th of the month
        Backdate to 25th of previous month if backdate is True; proration will generate an invoice from 25th of previous
        month to 25th of this month (i.e.)
        Start billing_cycle_anchor to 25th of this month (always in the future)

        e.g. now is 20th April. User chooses to backdate.
        Payment taken immediately for one full month from 25th March (for April Membership)
        Payment will be taken again on 25th April (for May membership) - billing_cycle_anchor = 25th April

        e.g. now is 20th April. User chooses NOT to backdate.
        No payment immediately
        Payment will be taken on 25th April (for May membership) - billing_cycle_anchor = 25th April

        e.g. now is 27th April. User cannot choose to backdate for April, but we need to backdate to 25th April
        to take May payment.
        Payment taken immediately for one full month from 25th April (for May Membership)
        Payment will be taken again on 25th May (for June membership) - billing_cycle_anchor = 25th May
        This scenario applies until 1st May. After 1st May (up to 25th), user gets option to start subscription in May or June

        NOTE: If not backdating, will create setup intent; if backdating, creates payment intent
        """
        subscription_kwargs = subscription_kwargs or self.get_subscription_kwargs(
            customer_id, price_id, backdate, default_payment_method
        )
        subscription = stripe.Subscription.create(**subscription_kwargs)

        return subscription
    
    def get_or_create_subscription_schedule(self, subscription_id):
        subscription = self.get_subscription(subscription_id)  # returned with subscription schedule expanded
        if not subscription.schedule:
            return stripe.SubscriptionSchedule.create(
                from_subscription=subscription_id,
                stripe_account=self.connected_account_id,
            )
        return subscription.schedule

    def update_subscription_price(self, subscription_id, new_price_id):
        """
        For when a Membership price changes (apply to every subscription with
        the membership), or when a user changes their plan
        Create a subscription schedule for each subscription
        Phases = current phase to end of billing period, then new phase with 
        new price
        On next billing period, subscription price will increase.
        """
        # retrieve or create schedule from subscription id
        schedule = self.get_or_create_subscription_schedule(subscription_id)
        # check schedule for end_behavior
        # if end_behavior is cancel, don't update, it's going to cancel at the end of the current billing period
        if schedule.end_behavior == "release":
            current_phase_items = [
                {
                    "price": phase["items"][0].price,
                    "quantity": phase["items"][0].quantity,
                } for phase in schedule.phases 
                if phase.start_date == schedule.current_phase.start_date and phase.end_date == schedule.current_phase.end_date
            ]

            # Update schedule to end current phase and create new phase for the new price
            schedule = stripe.SubscriptionSchedule.modify(
                schedule.id,
                end_behavior="release",
                phases=[
                        {
                            'items': current_phase_items,
                            'start_date': schedule.current_phase.start_date,
                            'end_date': schedule.current_phase.end_date,
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
                stripe_account=self.connected_account_id,
            )

        return schedule
    
    def cancel_subscription(self, subscription_id, cancel_immediately=False):
        """
        Usually we cancel from end of period
        Update schedule to contain only the current phase, and to cancel at the end
        Subscriptions that start in the future are cancelled immediately
        """
        if cancel_immediately:
            return stripe.Subscription.delete(subscription_id, stripe_account=self.connected_account_id)
        # retrieve or create schedule from subscription id
        schedule = self.get_or_create_subscription_schedule(subscription_id)
        current_phase_items = [
            {
                "price": phase["items"][0].price,
                "quantity": phase["items"][0].quantity,
            } for phase in schedule.phases 
            if phase.start_date == schedule.current_phase.start_date and phase.end_date == schedule.current_phase.end_date
        ]

        schedule = stripe.SubscriptionSchedule.modify(
            schedule.id,
            end_behavior="cancel",
            phases=[
                {
                    'items': current_phase_items,
                    'start_date': schedule.current_phase.start_date,
                    'end_date': schedule.current_phase.end_date,
                    "proration_behavior": "none"
                }
            ],
            expand=['subscription'],
            stripe_account=self.connected_account_id
        )
        return schedule.subscription
            
    def pause_subscription(self, subscription_id, months, pause_from):
        # Create a one-time promo code for 100% off this subscription's membership, lasting for <months>
        # Apply to subscription
        # Set pause_from/pause_to date
        # TODO In checks for whether membership is valid for booking, also check pause_from/pause_to date
        
        # TODO in ensure_subscription_up_to_date, and booking checks check for active subscriptions
        # that are currently between pause_from/pause_to dates and change subscription_status and
        # override_subscription_status to paused
        # TODO Needs model field for pause_from/pause_to
        ...

    def create_promo_code(
            self, 
            code, 
            product_ids,
            *,
            amount_off=None,
            percent_off=None,
            duration="once", 
            duration_in_months=None, 
            max_redemptions=None, 
            redeem_by=None, 
        ):
        """
        Create a coupon on stripe and an associated promotion code
        code: promotional code
        amount_off (int, pence) OR percent_off (float)
        duration: one of forever/once/repeating
        duration_in_months: int, if duration is repeating, number of months to repeat for
        max_redemptions: total number of times coupon can be used in total across all customers
        redeem_by: Date after which the coupon can no longer be redeemed
        product_ids: list of product ids to pass to applies_to {"products": []}
        """
        coupon = stripe.Coupon.create(
            applies_to={"products": product_ids},
            amount_off=amount_off,
            percent_off=percent_off,
            duration=duration,
            duration_in_months=duration_in_months,
            max_redemptions=max_redemptions,
            redeem_by=redeem_by,
            stripe_account=self.connected_account_id,
            currency="gbp",
        )
        promo_code = stripe.PromotionCode.create(
            code=code,
            coupon=coupon.id,
            stripe_account=self.connected_account_id,
        )
        return promo_code

    def update_promo_code(self, promo_code_id, active):
        return stripe.PromotionCode.modify(promo_code_id, active=active, stripe_account=self.connected_account_id)
    
    def get_promo_code(self, promo_code_id):
        try:
            return stripe.PromotionCode.retrieve(promo_code_id, stripe_account=self.connected_account_id)
        except stripe.InvalidRequestError as e:
            logger.error("Attempt to retrieve invalid promo code: %s", str(e))

    def get_upcoming_invoice(self, subscription_id):
        return stripe.Invoice.upcoming(
            subscription=subscription_id, expand=["discounts"], stripe_account=self.connected_account_id
        )

    def add_discount_to_subscription(self, subscription_id, promo_code_id=None):
        # for an existing suscription, add a discount
        # it will be applied to the next X months, as specified in the stripe coupon object
        # check if subscription already has the discount applied

        # Also add option to apply a discount when a subscription is created
        # check what happens when the subscription has a schedule (e.g. if price is changing)
        discounts = [{"promotion_code": promo_code_id}]
        subscription = stripe.Subscription.modify(
            subscription_id, discounts=discounts,
            stripe_account=self.connected_account_id,    
        )
        return subscription
    
    def remove_discount_from_subscription(self, subscription_id):
        stripe.Subscription.delete_discount(subscription_id, stripe_account=self.connected_account_id)

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
            # find the first config that returns to the booking site profile page
            config = next(
                (
                    config_it for config_it in configs.data
                    if config_it.default_return_url == "https://booking.thewatermelonstudio.co.uk/accounts/profile"
                ),
                None
            )
            if config is not None:
                # Check the config matches the expected data
                try:
                    assert config.business_profile.privacy_policy_url == config_data["business_profile"]["privacy_policy_url"]
                    assert config.business_profile.terms_of_service_url == config_data["business_profile"]["terms_of_service_url"]
                    assert config.features.customer_update.allowed_updates == ["email", "name", "address"]
                    assert config.features.customer_update.enabled
                    assert config.features.payment_method_update.enabled
                    assert config.features.invoice_history.enabled
                    assert not config.features.subscription_cancel.enabled
                    assert not config.features.subscription_update.enabled
                    return config
                except AssertionError:
                    return stripe.billing_portal.Configuration.modify(config.id, **config_data)
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
