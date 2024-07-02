from unittest.mock import MagicMock

import stripe


class MockConnector:

    def __init__(self, *args):
        self.connected_account = None
        self.connected_account_id = "id123"
        self.method_calls = {}

    def _record(self, fn, *args, **kwargs):
        self.method_calls.setdefault(fn.__name__, []).append({"args": args, "kwargs": kwargs})

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
        return MagicMock(id=subscription_id)

    def get_setup_intent(self, setup_intent_id):
        self._record(self.get_setup_intent, setup_intent_id)
    
    def create_subscription(self, *args, **kwargs):
        self._record(self.create_subscription, *args, **kwargs)

        return MagicMock(spec=stripe.Subscription, default_payment_method=kwargs.get("default_payment_method"))
    
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
