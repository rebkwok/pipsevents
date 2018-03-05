from django.urls import include, path
from payments.views import paypal_confirm_return, paypal_cancel_return


app_name = 'payments'

urlpatterns = [
    path('confirm/', paypal_confirm_return,
        name='paypal_confirm'),
    path('cancel/', paypal_cancel_return,
        name='paypal_cancel'),

    ]