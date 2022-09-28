from paypal.standard.forms import PayPalPaymentsForm


class PayPalPaymentsBaseForm(PayPalPaymentsForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_image(self):
        super().get_image()
        return {
            (True, self.SUBSCRIBE): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_subscribe_113x26.png',
            # (True, self.BUY): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_buynow_cc_171x47.png',
            (True, self.BUY): "/static/booking/images/checkout-logo-with-cc.png",
            (True, self.DONATE): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_donate_pp_142x27.png',
            (False, self.SUBSCRIBE): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_subscribe_113x26.png',
            (False, self.BUY): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_buynow_cc_171x47.png',
            (False, self.DONATE): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_donate_pp_142x27.png',
        }[self.test_mode(), self.button_type]


class PayPalPaymentsListForm(PayPalPaymentsBaseForm):

    ...


class PayPalPaymentsUpdateForm(PayPalPaymentsBaseForm):

    ...


class PayPalPaymentsShoppingBasketForm(PayPalPaymentsBaseForm):

    def get_image(self):
        super(PayPalPaymentsShoppingBasketForm, self).get_image()
        return {
            (True, self.SUBSCRIBE): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_subscribe_113x26.png',
            (True, self.BUY): "/static/booking/images/checkout-logo-with-cc.png",
            (True, self.DONATE): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_donate_pp_142x27.png',
            (False, self.SUBSCRIBE): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_subscribe_113x26.png',
            (False, self.BUY): "/static/booking/images/checkout_button.png",
            (False, self.DONATE): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_donate_pp_142x27.png',
        }[self.test_mode(), self.button_type]

