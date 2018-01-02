from django.utils.html import format_html
from paypal.standard.forms import PayPalPaymentsForm


class PayPalPaymentsListForm(PayPalPaymentsForm):

    def get_image(self):
        super(PayPalPaymentsListForm, self).get_image()
        return {
            (True, self.SUBSCRIBE): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_subscribe_113x26.png',
            (True, self.BUY): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_buynow_pp_142x27.png',
            (True, self.DONATE): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_donate_pp_142x27.png',
            (False, self.SUBSCRIBE): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_subscribe_113x26.png',
            (False, self.BUY): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_buynow_pp_142x27.png',
            (False, self.DONATE): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_donate_pp_142x27.png',
        }[self.test_mode(), self.button_type]

    def render(self):
        return format_html(
            """<form class="paypal-btn-form" action="{0}" method="post">
            {1}<input type="image" style="height: 75%; width: width: 8em;" src="{2}" border="0" name="submit" alt="Buy it Now" />
            </form>""", self.get_endpoint(), self.as_p(), self.get_image()
       )

class PayPalPaymentsUpdateForm(PayPalPaymentsForm):

    def get_image(self):
        super(PayPalPaymentsUpdateForm, self).get_image()
        return {
            (True, self.SUBSCRIBE): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_subscribe_113x26.png',
            (True, self.BUY): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_buynow_cc_171x47.png',
            (True, self.DONATE): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_donate_pp_142x27.png',
            (False, self.SUBSCRIBE): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_subscribe_113x26.png',
            (False, self.BUY): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_buynow_cc_171x47.png',
            (False, self.DONATE): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_donate_pp_142x27.png',
        }[self.test_mode(), self.button_type]

    def render(self):
        return format_html(
            """<form class="paypal-btn-form" action="{0}" method="post">
            {1}<input type="image" src="{2}" border="0" name="submit" alt="Buy it Now" />
            </form>""", self.get_endpoint(), self.as_p(), self.get_image()
       )


class PayPalPaymentsShoppingBasketForm(PayPalPaymentsForm):

    def get_image(self):
        super(PayPalPaymentsShoppingBasketForm, self).get_image()
        return {
            (True, self.SUBSCRIBE): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_subscribe_113x26.png',
            (True, self.BUY): "/static/booking/images/checkout_button.png",
            (True, self.DONATE): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_donate_pp_142x27.png',
            (False, self.SUBSCRIBE): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_subscribe_113x26.png',
            (False, self.BUY): "/static/booking/images/checkout_button.png",
            (False, self.DONATE): 'https://www.paypalobjects.com/webstatic/en_US/btn/btn_donate_pp_142x27.png',
        }[self.test_mode(), self.button_type]

    def render(self):
        return format_html(
            """<form class="paypal-btn-form" action="{0}" method="post">
            {1}<input type="image" style="height: 65%; width: width: 8em;"
            src="{2}" border="0" name="submit" alt="Checkout Now" />
            </form>""", self.get_endpoint(), self.as_p(), self.get_image()
       )