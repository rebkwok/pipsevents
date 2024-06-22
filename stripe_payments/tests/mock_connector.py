from unittest.mock import MagicMock

import stripe


class MockConnector:

    def __init__(self, *args):
        self.connected_account = None
        self.connected_account_id = "id123"

    def create_stripe_product(self, product_id, name, description, price):
        return MagicMock(spec=stripe.Product, default_price="price_1234")

    def update_stripe_product(self, product_id, name, description, active, price_id):
        return MagicMock(spec=stripe.Product, default_price="price_2345")

    def get_or_create_stripe_price(self, product_id, price):
        return "price_234"

    def get_or_create_stripe_customer(self, user, **kwargs):
        if user.userprofile.stripe_customer_id:
            return user.userprofile.stripe_customer_id

        user.userprofile.stripe_customer_id = "cus_234"
        user.userprofile.save()
        return "cus_234"

    def update_stripe_customer(self, customer_id, **kwargs):
        raise NotImplementedError

    def get_subscription(self, subscription_id):
        return MagicMock(id=subscription_id)

    def get_setup_intent(self, setup_intent_id):
        raise NotImplementedError
    
    def create_subscription(self, customer_id, price_id, backdate=True):
        raise NotImplementedError
    
    def get_or_create_subscription_schedule(self, subscription_id):
        raise NotImplementedError

    def update_subscription_price(self, subscription_id, new_price_id):
        raise NotImplementedError
    
    def cancel_subscription(self, subscription_id):
        raise NotImplementedError
    
    def add_discount_to_subscription(self, subscription_id):
        raise NotImplementedError

    def customer_portal_configuration(self):
        raise NotImplementedError
    
    def customer_portal_url(self, customer_id):
        raise NotImplementedError
