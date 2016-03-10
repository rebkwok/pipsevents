# -*- coding: utf-8 -*-

from django.conf import settings
from django.shortcuts import render
from django.template.response import TemplateResponse
from django.views.decorators.csrf import csrf_exempt

from paypal.standard.ipn.models import PayPalIPN

from booking.models import Block, Booking, TicketBooking

"""
def view_that_asks_for_money(request):

    # What you want the button to do.
    paypal_dict = {
        "business": settings.DEFAULT_PAYPAL_EMAIL,
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
    obj = 'unknown'
    test_ipn_complete = False
    custom = request.POST.get('custom', '').split()

    if custom:
        obj_type = custom[0]
        obj_id = int(custom[1])

        if obj_type == "booking":
            obj = Booking.objects.get(id=obj_id)
        elif obj_type == "block":
            obj = Block.objects.get(id=obj_id)
        elif obj_type == "ticket_booking":
            obj = TicketBooking.objects.get(id=obj_id)
        elif obj_type == "paypal_test":
            obj = "paypal_test"
            # custom in a test payment is in form
            # 'test 0 <invoice_id> <paypal email being tested> <user's email>'
            test_ipn_complete = bool(
                PayPalIPN.objects.filter(
                    invoice=custom[2], payment_status='Completed'
                )
            )
        else:
            obj = 'unknown'

        # Possible payment statuses:
        # Canceled_, Reversal, Completed, Denied, Expired, Failed, Pending,
        # Processed, Refunded, Reversed, Voided
        # NOTE: We can check for completed payment status for displaying
        # information in the template, but we can only confirm payment if the
        # booking or block has already been set to paid (i.e. the post from
        # paypal has been successfully processed
        context = {'obj': obj,
                   'obj_type': obj_type,
                   'payment_status': request.POST.get('payment_status'),
                   'purchase': request.POST.get('item_name'),
                   'sender_email': settings.DEFAULT_FROM_EMAIL,
                   'organiser_email': settings.DEFAULT_STUDIO_EMAIL,
                   'test_ipn_complete': test_ipn_complete,
                   'test_paypal_email': custom[3] if obj == 'test' else ''
                   }

    if not custom or obj == 'unknown':
        context = {
            'obj_unknown': True,
            'organiser_email': settings.DEFAULT_STUDIO_EMAIL
        }
    return TemplateResponse(request, 'payments/confirmed_payment.html', context)


@csrf_exempt
def paypal_cancel_return(request):
    return render(request, 'payments/cancelled_payment.html')

