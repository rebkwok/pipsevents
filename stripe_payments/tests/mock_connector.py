from unittest.mock import MagicMock, Mock

import stripe

from ..utils import StripeConnector


class MockConnector:

    def __init__(
            self,
            request=None, 
            default_payment_method=None, 
            invoice_secret=None, 
            setup_intent_secret=None, 
            setup_intent_status="payment_method_required",
            payment_intent_status="incomplete",
            subscriptions={},
            get_payment_intent=None,
            subscription_status=None,
            no_subscription=False,
            discount=None,
        ):
        super().__init__()
        self.connector = StripeConnector()
        self.connected_account = None
        self.connected_account_id = "id123"
        self.connector.connected_account =  self.connected_account
        self.connector.account_id = self.connected_account_id

        # record method calls and args/kwargs
        self.method_calls = {}
        
        # Provide invoice secret OR setup intent secret: 
        # used in get_subscription; determines how a new subscription is being set up 
        self.invoice = None
        self.pending_setup_intent = None
        self.invoice_secret = invoice_secret
        if self.invoice_secret:
            self.invoice = Mock(payment_intent=Mock(client_secret=self.invoice_secret))
        elif setup_intent_secret:
            self.pending_setup_intent = Mock(id="su", client_secret=setup_intent_secret)
        
        self.subscription_status = subscription_status

        # setup_intent_status: used in get_setup_intent to override the usual status
        self.setup_intent_status = setup_intent_status
        self.payment_intent_status = payment_intent_status

        # default_payment_method: used when changing a subscription, transferred to the new one
        self.default_payment_method = default_payment_method

        # subscriptions for customer
        self.subscriptions = subscriptions

        # resp from get_payment_intent
        self.payment_intent = get_payment_intent

        # no subscrption == return None from get_subscription
        self.no_subscription = no_subscription

        # discount - return with get_subscription
        self.discount = discount
        
    def _record(self, fn, *args, **kwargs):
        self.method_calls.setdefault(fn.__name__, []).append({"args": args, "kwargs": kwargs})

    def get_subscription_kwargs(self, customer_id, price_id, backdate=True, default_payment_method=None, discounts=None):
        return self.connector.get_subscription_kwargs(customer_id, price_id, backdate, default_payment_method, discounts)

    def create_stripe_product(self,  *args, **kwargs):
        self._record(self.create_stripe_product, *args, **kwargs)
        return MagicMock(spec=stripe.Product, default_price="price_1234")

    def update_stripe_product(self,  *args, **kwargs):
        self._record(self.update_stripe_product,  *args, **kwargs)
        return MagicMock(spec=stripe.Product, default_price="price_2345")

    def get_or_create_stripe_price(self, *args, **kwargs):
        self._record(self.get_or_create_stripe_price, *args, **kwargs)
        return "price_234"

    def archive_stripe_price(self, *args, **kwargs):
        self._record(self.archive_stripe_price, *args, **kwargs)

    def archive_stripe_product(self, *args, **kwargs):
        self._record(self.archive_stripe_product, *args, **kwargs)

    def get_or_create_stripe_customer(self, *args, **kwargs):
        self._record(self.get_or_create_stripe_customer, *args, **kwargs)
        user = args[0]
        if user.userprofile.stripe_customer_id:
            return user.userprofile.stripe_customer_id

        user.userprofile.stripe_customer_id = "cus_234"
        user.userprofile.save()
        return "cus_234"

    def update_stripe_customer(self, *args, **kwargs):
        self._record(self.update_stripe_customer, *args, **kwargs)

    def get_subscription(self, subscription_id):
        self._record(self.get_subscription, subscription_id)
        if self.no_subscription:
            return None
        return MagicMock(
            id=subscription_id,
            latest_invoice=self.invoice,
            pending_setup_intent=self.pending_setup_intent,
            default_payment_method=self.default_payment_method,
            status=self.subscription_status,
            discounts=[Mock(**self.discount)] if self.discount else []
        )

    def get_subscriptions_for_customer(self, customer_id, status="all"):
        self._record(self.get_subscriptions_for_customer, customer_id, status=status )
        return self.subscriptions

    def get_setup_intent(self, setup_intent_id):
        self._record(self.get_setup_intent, setup_intent_id)
        return Mock(id=setup_intent_id, status=self.setup_intent_status)

    def get_payment_intent(self, payment_intent_id):
        self._record(self.get_payment_intent, payment_intent_id)
        return self.payment_intent or Mock(id=payment_intent_id, status="incomplete", client_secret="bar")
    
    def create_subscription(self, *args, **kwargs):
        self._record(self.create_subscription, *args, **kwargs)
        return MagicMock(
            spec=stripe.Subscription,
            latest_invoice=self.invoice,
            pending_setup_intent=self.pending_setup_intent,
            default_payment_method=kwargs.get("default_payment_method")
        )
    
    def get_or_create_subscription_schedule(self, subscription_id):
        self._record(self.get_or_create_subscription_schedule, subscription_id)

    def update_subscription_price(self, subscription_id, new_price_id):
        self._record(self.get_or_create_subscription_schedule, subscription_id, new_price_id)
        raise NotImplementedError
    
    def cancel_subscription(self, subscription_id, cancel_immediately=False):
        self._record(self.cancel_subscription, subscription_id, cancel_immediately=cancel_immediately)
        return MagicMock(
            id=subscription_id, status="canceled" if cancel_immediately else "active",    
        )
    
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
        self._record(
            self.create_promo_code, 
            code, 
            product_ids, 
            amount_off=amount_off,
            percent_off=percent_off, 
            duration=duration, 
            duration_in_months=duration_in_months, 
            max_redemptions=max_redemptions, 
            redeem_by=redeem_by
        )
        return MagicMock(id="promo-id")

    def update_promo_code(self, promo_code_id, active):
        raise NotImplementedError
    
    def get_promo_code(self, promo_code_id):
        raise NotImplementedError

    def get_upcoming_invoice(self, subscription_id):
        raise NotImplementedError
    
    def remove_discount_from_subscription(self, subscription_id):
        self._record(self.remove_discount_from_subscription, [subscription_id])
        return Mock()

    def add_discount_to_subscription(self, subscription_id, promo_code_id=None):
        self._record(self.add_discount_to_subscription, [subscription_id])
        return Mock()

    def customer_portal_configuration(self):
        self._record(self.customer_portal_configuration)
        raise NotImplementedError
    
    def customer_portal_url(self, customer_id):
        self._record(self.customer_portal_url, [customer_id])
        return f"https://example.com/portal/{customer_id}/"
