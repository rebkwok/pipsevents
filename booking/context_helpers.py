"""
Helper functions to return context and reduce logic in templates
"""
from django.conf import settings
from django.utils import timezone
from django.core.urlresolvers import reverse

from booking.models import BlockType, WaitingListUser

def get_event_context(context, event, user):

    if event.event_type.event_type == 'CL':
        context['type'] = "lesson"
        event_type_str = "class"
    else:
        context['type'] = "event"
        event_type_str = "event"

    if event.date <= timezone.now():
        context['past'] = True

    # payment info text to be displayed
    if event.cost == 0:
        payment_text = "There is no cost associated with this {}.".format(
            event_type_str
        )
    else:
        if not event.payment_open:
            payment_text = "Online payments are not open. " + event.payment_info
        else:
            payment_text = "Online payments are open. " + event.payment_info
    context['payment_text'] = payment_text

    # booked flag
    user_bookings = user.bookings.all()
    user_booked_events = [booking.event for booking in user_bookings
                             if booking.status == 'OPEN']
    user_cancelled_events = [booking.event for booking in user_bookings
                             if booking.status == 'CANCELLED']
    booked = event in user_booked_events
    cancelled = event in user_cancelled_events

    # waiting_list flag
    try:
        WaitingListUser.objects.get(user=user, event=event)
        context['waiting_list'] = True
    except WaitingListUser.DoesNotExist:
        pass

    # booking info text and bookable
    booking_info_text = ""
    context['bookable'] = event.bookable()
    if booked:
        context['bookable'] = False
        booking_info_text = "You have booked for this {}.".format(event_type_str)
        context['booked'] = True
    elif event.event_type.subtype == "Pole practice" \
        and not user.has_perm("booking.is_regular_student"):
        context['bookable'] = False
        context['unbookable_pole_practice'] = True
        booking_info_text = "<span class='cancel-warning'>NOT AVAILABLE FOR BOOKING</br>" \
                            "Pole practice is " \
                            "only open to regular students. If " \
                            "you are seeing this message and you are a regular " \
                            "student, please contact " \
                            "<a href='mailto:{}' target=_blank>{}</a> to have your account " \
                            "upgraded.</span>".format(event.contact_email, event.contact_email)
    else:
        if cancelled:
            context['cancelled'] = True
            booking_info_text_cancelled = "You have previously booked for this {} and" \
                                    " cancelled.".format(event_type_str)
            context['booking_info_text_cancelled'] = booking_info_text_cancelled

        if event.event_type.subtype == "External instructor class":
            booking_info_text = "Please contact {} directly to book".format(event.contact_person)

        if not event.booking_open:
            booking_info_text = "Bookings are not open for this {}.".format(
                event_type_str
            )
        if event.spaces_left() <= 0:
            booking_info_text = "This {} is now full.".format(event_type_str)
        if event.payment_due_date:
            if event.payment_due_date < timezone.now():
                booking_info_text = "Bookings for this event are now closed."

    context['booking_info_text'] = booking_info_text
    return context


def get_booking_context(context, booking):

    if booking.event.event_type.event_type == 'CL':
        context['type'] = "lesson"
        event_type_str = "class"
    else:
        context['type'] = "event"
        event_type_str = "event"

    # past booking
    if booking.event.date < timezone.now():
        context['past'] = True

    # payment info text to be displayed
    if booking.event.cost == 0:
        payment_text = "There is no cost associated with this {}.".format(
            event_type_str
        )
    else:
        if not booking.event.payment_open:
            payment_text = "Online payments are not open. " + booking.event.payment_info
        else:
            payment_text = "Online payments are open. " + booking.event.payment_info
    context['payment_text'] = payment_text

    # confirm payment button
    if booking.event.cost > 0 and not booking.paid \
            and booking.event.payment_open:
        context['include_payment_button'] = True

    # delete button
    context['can_cancel'] = (booking.event.can_cancel() and booking.status == 'OPEN')

    return context


def get_booking_create_context(event, request, context):
    # find if block booking is available for this type of event
    blocktypes = [
        blocktype.event_type for blocktype in BlockType.objects.all()
        ]
    blocktype_available = event.event_type in blocktypes
    context['blocktype_available'] = blocktype_available

    # Add in the event name
    context['event'] = event
    user_blocks = request.user.blocks.all()
    active_user_block = [
        block for block in user_blocks
        if block.block_type.event_type == event.event_type
        and block.active_block()
        ]
    if active_user_block:
        context['active_user_block'] = True

    active_user_block_unpaid = [
        block for block in user_blocks
        if block.block_type.event_type == event.event_type
        and not block.expired
        and not block.full
        and not block.paid
         ]
    if active_user_block_unpaid:
        context['active_user_block_unpaid'] = True

    ev_type = 'event' if \
        event.event_type.event_type == 'EV' else 'class'

    context['ev_type'] = ev_type

    if event.event_type.subtype == "Pole level class" or \
        (event.event_type.subtype == "Pole practice" and \
        request.user.has_perm('booking.can_book_free_pole_practice')):
        context['can_be_free_class'] = True

    bookings_count = event.bookings.filter(status='OPEN').count()
    if event.max_participants:
        event_full = True if \
            (event.max_participants - bookings_count) <= 0 else False
        context['event_full'] = event_full

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
