from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from paypal.standard.forms import PayPalPaymentsForm


"""
def view_that_asks_for_money(request):

    # What you want the button to do.
    paypal_dict = {
        "business": settings.PAYPAL_RECEIVER_EMAIL,
        "amount": "10.00",
        "item_name": "Watermeloon Class",
        "invoice": "unique-invoice-id",
        "currency_code": "GBP",
        "notify_url": reverse('paypal-ipn'),
        "return_url": reverse('payments:paypal_confirm'),
        "cancel_return": reverse('payments:paypal_cancel'),

    }

    # Create the instance.
    form = PayPalPaymentsForm(initial=paypal_dict)
    context = {"form": form}
    return render_to_response("payment.html", context)
"""

@csrf_exempt
def paypal_confirm_return(request):
    #TODO add link to your bookings
    #TODO reference the event the booking was made for, state that payment is being
    #TODO processed and will show as paid and confirmed once processed (should
    #TODO happen within a few minutes
    return render(request, 'payments/confirmed_payment.html')


@csrf_exempt
def paypal_cancel_return(request):
    # TODO delete PaypalTransaction? Or add cancelled flag?
    #TODO reference the event the booking was made for

    return render(request, 'payments/cancelled_payment.html')
