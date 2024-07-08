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
        
    def _record(self, fn, *args, **kwargs):
        self.method_calls.setdefault(fn.__name__, []).append({"args": args, "kwargs": kwargs})

    def get_subscription_kwargs(self, customer_id, price_id, backdate=True, default_payment_method=None):
        return self.connector.get_subscription_kwargs(customer_id, price_id, backdate, default_payment_method)

    def create_stripe_product(self,  *args, **kwargs):
        self._record(self.create_stripe_product, *args, **kwargs)
        return MagicMock(spec=stripe.Product, default_price="price_1234")

    def update_stripe_product(self,  *args, **kwargs):
        self._record(self.update_stripe_product,  *args, **kwargs)
        return MagicMock(spec=stripe.Product, default_price="price_2345")

    def get_or_create_stripe_price(self, *args, **kwargs):
        self._record(self.get_or_create_stripe_price, *args, **kwargs)
        return "price_234"

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
    
    def add_discount_to_subscription(self, subscription_id):
        self._record(self.add_discount_to_subscription, [subscription_id])
        raise NotImplementedError

    def customer_portal_configuration(self):
        self._record(self.customer_portal_configuration)
        raise NotImplementedError
    
    def customer_portal_url(self, customer_id):
        self._record(self.customer_portal_url, [customer_id])
        raise NotImplementedError
