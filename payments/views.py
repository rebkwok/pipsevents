# -*- coding: utf-8 -*-
import requests

from django.conf import settings

from django.core.exceptions import MultipleObjectsReturned
from django.shortcuts import render, HttpResponseRedirect

from django.template.response import TemplateResponse
from django.views.decorators.csrf import csrf_exempt

from paypal.standard.ipn.models import PayPalIPN

from booking.models import Block, Booking, TicketBooking
from payments.models import PaypalBookingTransaction, PaypalBlockTransaction, \
    PaypalTicketBookingTransaction


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
    objs = ['unknown']
    test_ipn_complete = False
    custom = request.POST.get('custom', '')
    custom = custom.replace('+', ' ').split()
    context = {}

    if custom:
        obj_type = custom[0]
        ids = custom[1]
        obj_ids = [int(id) for id in ids.split(',')]

        if obj_type == "booking":
            objs = Booking.objects.filter(id__in=obj_ids)
        elif obj_type == "block":
            objs = Block.objects.filter(id__in=obj_ids)
        elif obj_type == "ticket_booking":
            objs = TicketBooking.objects.filter(id__in=obj_ids)
        elif obj_type == "paypal_test":
            objs = ["paypal_test"]
            # custom in a test payment is in form
            # 'test 0 <invoice_id> <paypal email being tested> <user's email>'
            test_ipn_complete = bool(
                PayPalIPN.objects.filter(
                    invoice=custom[2], payment_status='Completed'
                )
            )

        # Possible payment statuses:
        # Canceled_, Reversal, Completed, Denied, Expired, Failed, Pending,
        # Processed, Refunded, Reversed, Voided
        # NOTE: We can check for completed payment status for displaying
        # information in the template, but we can only confirm payment if the
        # booking or block has already been set to paid (i.e. the post from
        # paypal has been successfully processed
        context = {'objs': objs,
                   'obj_type': obj_type,
                   'payment_status': request.POST.get('payment_status'),
                   'sender_email': settings.DEFAULT_FROM_EMAIL,
                   'organiser_email': settings.DEFAULT_STUDIO_EMAIL,
                   'test_ipn_complete': test_ipn_complete,
                   'test_paypal_email': custom[3] if objs[0] == 'paypal_test'
                   else ''
                   }

    if not custom or objs == ['unknown']:
        # find cart items; check they're not paid yet set and paypal pending
        # we should get here if there was a successful return from paypal, so
        # should be safe to assume these items are just
        # awaiting paypal confirmation
        cart_items = request.session.get('cart_items', [])
        if cart_items:
            cart_items, item_type, cart_item_names, _ = get_cart_item_names(cart_items)
            # cart items will be the same as custom, will be split to 2 or 3
            # depending on whether voucher code is applied
            del request.session['cart_items']
            if item_type in ["booking", "block"]:
                for item in cart_items:
                    if not item.paid:  # in case payment is processed during this view
                        item.paypal_pending = True
                        item.save()

        context = {
            'obj_unknown': True,
            'cart_items':  cart_item_names if cart_items else [],
            'organiser_email': settings.DEFAULT_STUDIO_EMAIL
        }

    return TemplateResponse(request, 'payments/confirmed_payment.html', context)


@csrf_exempt
def paypal_cancel_return(request):
    cart_items_from_session = request.session.get('cart_items')
    ppipn = None
    already_paid = False
    if cart_items_from_session and not request.user.is_anonymous():
        # check for a paypal ipn with custom==cart_items and status completed
        # if user resubmitted a paid invoice, the "Return to merchant" from
        # paypal will return them here too
        # set relevant bookings/blocks to paid and add transaction id to
        # paypal transaction objects
        # Display "already" to user instead of cancelled
        cart_items, item_type, _, user_email = get_cart_item_names(
            cart_items_from_session
        )
        try:
            if user_email == request.user.email:
                # make sure we got an email back in custom so the ppipn we
                # retrieve definitely belongs to this user
                ppipn = PayPalIPN.objects.get(
                    payment_status='Completed', flag=False,
                    custom=cart_items_from_session
                )
                already_paid = True
        except (PayPalIPN.DoesNotExist, MultipleObjectsReturned):
            # if we can't identify a single completed PPIPN that matches this
            # user and items, don't risk updating
            pass

        if ppipn:
            # update
            if item_type == 'booking':
                PaypalBookingTransaction.objects.filter(
                    invoice_id=ppipn.invoice, booking__in=cart_items
                ).update(transaction_id=ppipn.txn_id)
                for item in cart_items:
                    item.paid = True
                    item.payment_confirmed = True
                    item.paypal_pending = False
                    item.save()
            elif item_type == 'block':
                PaypalBlockTransaction.objects.filter(
                    invoice_id=ppipn.invoice, block__in=cart_items
                ).update(transaction_id=ppipn.txn_id)
                for item in cart_items:
                    item.paid = True
                    item.paypal_pending = False
                    item.save()
            elif item_type == 'ticket_booking':
                PaypalTicketBookingTransaction.objects.filter(
                    invoice_id=ppipn.invoice, ticket_booking__in=cart_items
                ).update(transaction_id=ppipn.txn_id)
                for item in cart_items:
                    item.paid = True
                    item.save()

        del request.session['cart_items']
    return render(
        request, 'payments/cancelled_payment.html',
        {'already_paid': already_paid}
    )


def get_cart_item_names(cart_items):
    items = cart_items.split(' ')
    if not (3 <= len(items) <= 4):
        # incorrect cart_items format
        item_type = 'unknown'
        user_email = None
    else:
        item_type = items[0]
        item_ids = items[1]
        user_email = items[2]
        ids = item_ids.split(',')
        obj_ids = [int(id) for id in ids]

    if item_type == 'booking':
        cart_items = Booking.objects.filter(id__in=obj_ids)
        cart_item_names = [bk.event for bk in cart_items]
    elif item_type == 'block':
        cart_items = Block.objects.filter(id__in=obj_ids)
        cart_item_names = [block.block_type for block in cart_items]
    elif item_type == 'ticket_booking':
        cart_items = TicketBooking.objects.filter(id__in=obj_ids)
        cart_item_names = [
            '{} - {}'.format(bk.ticketed_event.name, bk.booking_reference)
            for bk in cart_items
            ]
    else:
        # we can't identify the item type
        cart_items = []
        cart_item_names = []

    return cart_items, item_type, cart_item_names, user_email


@csrf_exempt
def paypal_form_post(request):
    """
    interim view to add cart items to session before redirecting to the paypal
    endpoint
    """
    # add cart booking ids to the session so we can set paypal pending
    request.session['cart_items'] = request.POST['custom']
    endpoint = request.POST['endpoint']
    resp = requests.post(endpoint, request.POST)
    return HttpResponseRedirect(resp.url)
