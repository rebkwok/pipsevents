from django.conf.urls import include, url
from payments.views import paypal_confirm_return, paypal_cancel_return, \
    paypal_form_post

urlpatterns = [
    url(r'^confirm/$', paypal_confirm_return,
        name='paypal_confirm'),
    url(r'^cancel/$', paypal_cancel_return,
        name='paypal_cancel'),
    url(r'^form/$', paypal_form_post,
        name='paypal_form_post'),
    ]