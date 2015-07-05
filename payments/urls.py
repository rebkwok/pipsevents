from django.conf.urls import patterns, include, url

urlpatterns = patterns('',
    url(r'^confirm/$', 'payments.views.paypal_confirm_return',
        name='paypal_confirm'),
    url(r'^cancel/$', 'payments.views.paypal_cancel_return',
        name='paypal_cancel'),
    )
