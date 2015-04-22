"""
Helper functions to return context and reduce logic in templates
"""
from django.conf import settings
from django.utils import timezone
from django.core.urlresolvers import reverse

from booking.models import BlockType

def get_event_context(context, event, user):

    if event.event_type.event_type == 'CL':
        context['type'] = "lesson"
    else:
        context['type'] = "event"

    if event.date <= timezone.now():
        context['past'] = True

    # payment info text to be displayed
    if event.cost == 0:
        payment_text = "There is no cost associated with this event."
    else:
        if not event.payment_open:
            payment_text = "Payments are not open. " + event.payment_info
        else:
            payment_text = "Payments are open. " + event.payment_info
    context['payment_text'] = payment_text

    # booked flag
    user_bookings = user.bookings.all()
    user_booked_events = [booking.event for booking in user_bookings]
    user_cancelled_events = [booking.event for booking in user_bookings
                             if booking.status == 'CANCELLED']
    booked = event in user_booked_events
    cancelled = event in user_cancelled_events

    # booking info text and bookable
    booking_info_text = ""
    context['bookable'] = event.bookable()
    if booked:
        context['bookable'] = False
        booking_info_text = "You have booked for this event."
        if cancelled:
            booking_info_text = "You have previously booked for this event and" \
                                " cancelled."
        context['booked'] = True
    elif not event.booking_open:
        booking_info_text = "Bookings are not open for this event."
    elif event.spaces_left() <= 0:
        booking_info_text = "This event is now full."
    elif not event.bookable():
        booking_info_text = "Bookings for this event are now closed."

    context['booking_info_text'] = booking_info_text

    return context


def get_booking_context(context, booking):

    if booking.event.event_type.event_type == 'CL':
        context['type'] = "lesson"
    else:
        context['type'] = "event"

    # past booking
    if booking.event.date < timezone.now():
        context['past'] = True

    # payment info text to be displayed
    if booking.event.cost == 0:
        payment_text = "There is no cost associated with this event."
    else:
        if not booking.event.payment_open:
            payment_text = "Payments are not yet open. Payment information " \
                           "will be provided closer to the event date."
        else:
            payment_text = "Payments are open. " + booking.event.payment_info
    context['payment_text'] = payment_text

    # confirm payment button
    if booking.event.cost > 0 and not booking.paid \
            and booking.event.payment_open:
        context['include_payment_button'] = True

    # delete button
    context['can_cancel'] = (booking.event.can_cancel() and booking.status == 'OPEN')

    return context


def get_paypal_dict(host, cost, item_name, invoice_id, custom):

    paypal_dict = {
        "business": settings.PAYPAL_RECEIVER_EMAIL,
        "amount": cost,
        "item_name": item_name,
        "custom": custom,
        "invoice": invoice_id,
        "currency_code": "GBP",
        "notify_url": host + reverse('paypal-ipn'),
        "return_url": host + reverse('payments:paypal_confirm'),
        "cancel_return": host + reverse('payments:paypal_cancel'),

    }
    return paypal_dict


def get_blocktypes_available_to_book(user):
    user_blocks = user.blocks.all()

    available_block_event_types = [block.block_type.event_type
                                   for block in user_blocks
                                   if not block.expired
                                   and not block.full]
    return BlockType.objects.exclude(
        event_type__in=available_block_event_types
    )