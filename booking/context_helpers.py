"""
Helper functions to return context and reduce logic in templates
"""
import pytz

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone
from django.urls import reverse

from accounts.utils import has_active_disclaimer, has_expired_disclaimer
from booking.models import Block, BlockType, Booking, WaitingListUser


def get_event_context(context, event, user):
    disclaimer = has_active_disclaimer(user)
    expired_disclaimer = has_expired_disclaimer(user)
    context['disclaimer'] = disclaimer
    context['expired_disclaimer'] = expired_disclaimer

    if event.event_type.event_type == 'CL':
        context['type'] = "lesson"
        event_type_str = "class"
    elif event.event_type.event_type == 'EV':
        context['type'] = "event"
        event_type_str = "workshop/event"
    else:
        context['type'] = "room_hire"
        event_type_str = "room hire"

    context['event_type_str'] = event_type_str

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
    user_bookings = Booking.objects.filter(
        event=event, user=user, status='OPEN', no_show=False
    )
    user_cancelled = Booking.objects.filter(
        event=event, user=user, status='CANCELLED'
    ).exists()
    auto_cancelled = Booking.objects.filter(
        event=event, user=user, status='CANCELLED', auto_cancelled=True
    ).exists()
    user_no_show = Booking.objects.filter(
        event=event, user=user, status='OPEN', no_show=True
    ).exists()
    booked = bool(user_bookings)
    cancelled = user_cancelled or user_no_show

    # waiting_list flag
    context['on_waiting_list'] = WaitingListUser.objects.filter(
        user=user, event=event
    ).exists()

    # booking info text and bookable
    booking_info_text = ""
    context['bookable'] = event.bookable
    if booked:
        context['bookable'] = False
        booking_info_text = "You have booked for this {}.".format(event_type_str)
        context['booked'] = True
        context['booking'] = user_bookings[0]
    elif not disclaimer:
        if expired_disclaimer:
            booking_info_text = "<strong>Please update your <a href='{}' " \
                                "target=_blank>disclaimer form</a> before " \
                                "booking.</strong>".format(
                                    reverse('disclaimer_form')
                                )
        else:
            booking_info_text = "<strong>Please complete a <a href='{}' " \
                                "target=_blank>disclaimer form</a> before " \
                                "booking.</strong>".format(
                                    reverse('disclaimer_form')
                                )
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
        if auto_cancelled:
            context['auto_cancelled'] = True
            booking_info_text_cancelled = "To rebook this {} please contact " \
                                          "{} directly.".format(
                                            event_type_str, event.contact_email
                                            )
            context['booking_info_text_cancelled'] = booking_info_text_cancelled
        elif cancelled:
            context['cancelled'] = True
            booking_info_text_cancelled = "You have previously booked for " \
                                          "this {} and your booking has been " \
                                          "cancelled.".format(event_type_str)
            context['booking_info_text_cancelled'] = booking_info_text_cancelled

        if event.event_type.subtype == "External instructor class":
            booking_info_text = "Please contact {} directly to book".format(event.contact_person)
        elif not event.booking_open:
            booking_info_text = "Bookings are not open for this {}.".format(
                event_type_str
            )
        if event.spaces_left <= 0:
            booking_info_text = "This {} is now full.".format(event_type_str)
        if event.payment_due_date:
            if event.payment_due_date < timezone.now():
                booking_info_text = "The payment due date has passed for " \
                                    "this {}.  Please make your payment as " \
                                    "soon as possible to secure your " \
                                    "place.".format(event_type_str)

    context['booking_info_text'] = booking_info_text

    # get payment due date
    uk_tz = pytz.timezone('Europe/London')

    cancellation_due_date = event.date - timedelta(
        hours=(event.cancellation_period)
    )
    cancellation_due_date = cancellation_due_date.astimezone(uk_tz)
    context['cancellation_due_date'] = cancellation_due_date

    return context


def get_booking_create_context(event, request, context):
    # find if block booking is available for this type of event
    blocktypes = BlockType.objects.filter(active=True).values_list('event_type__id', flat=True)
    blocktype_available = event.event_type.id in blocktypes
    context['blocktype_available'] = blocktype_available
    # Add in the event name
    context['event'] = event
    user_blocks = Block.objects.filter(
        user=request.user, block_type__event_type=event.event_type
    )
    active_user_block = [block for block in user_blocks if block.active_block()]
    if active_user_block:
        context['active_user_block'] = True

    active_user_block_unpaid = [
        block for block in user_blocks if not block.expired
        and not block.full and not block.paid
         ]
    if active_user_block_unpaid:
        context['active_user_block_unpaid'] = True

    if event.event_type.event_type == 'EV':
        ev_type = 'workshop/event'
    elif event.event_type.event_type == 'CL':
        ev_type = 'class'
    else:
        ev_type = 'room hire'

    context['ev_type'] = ev_type

    if event.event_type.subtype in ["Pole level class", "Pole practice"] \
            and request.user.has_perm('booking.can_request_free_class'):
        context['can_be_free_class'] = True

    bookings_count = event.bookings.filter(status='OPEN').count()
    if event.max_participants:
        event_full = True if \
            (event.max_participants - bookings_count) <= 0 else False
        context['event_full'] = event_full


    try:
        # if reopening an already paid booking, we don't want to give option to
        # book with block
        Booking.objects.get(event=event, user=request.user, paid=True)
        context['reopening_paid_booking'] = True
    except Booking.DoesNotExist:
        pass

    return context


def get_paypal_dict(
        host, cost, item_name, invoice_id, custom,
        paypal_email=settings.DEFAULT_PAYPAL_EMAIL, quantity=1):

    paypal_dict = {
        "business": paypal_email,
        "amount": cost,
        "item_name": str(item_name)[:127],
        "custom": custom,
        "invoice": invoice_id,
        "currency_code": "GBP",
        "quantity": quantity,
        "notify_url": host + reverse('paypal-ipn'),
        "return": host + reverse('payments:paypal_confirm'),
        "cancel_return": host + reverse('payments:paypal_cancel'),

    }
    return paypal_dict


def get_paypal_cart_dict(
        host, item_type, items, invoice_id, custom,
        voucher_applied_items=None,
        voucher=None, paypal_email=settings.DEFAULT_PAYPAL_EMAIL
    ):

    paypal_dict = {
        "cmd": "_cart",
        "upload": 1,
        "business": paypal_email,
        "custom": custom,
        "invoice": invoice_id,
        "currency_code": "GBP",
        "notify_url": host + reverse('paypal-ipn'),
        "return": host + reverse('payments:paypal_confirm'),
        "cancel_return": host + reverse('payments:paypal_cancel'),
    }

    for i, item in enumerate(items):
        amount = item.event.cost if item_type == 'booking' else item.block_type.cost
        item_name = str(item.event) if item_type == 'booking' else str(item.block_type)
        if voucher_applied_items and item.id in voucher_applied_items:
            amount = Decimal(
                float(amount) * ((100 - voucher.discount) / 100)
            ).quantize(Decimal('.05'))

        paypal_dict.update(
            {
                'item_name_{}'.format(i + 1): item_name,
                'amount_{}'.format(i + 1): amount,
                'quantity_{}'.format(i + 1): 1,
            }
        )

    return paypal_dict


def get_blocktypes_available_to_book(user):
    user_blocks = user.blocks.all()

    available_block_event_types = [block.block_type.event_type
                                   for block in user_blocks
                                   if not block.expired
                                   and not block.full]
    return BlockType.objects.filter(active=True).exclude(
        event_type__in=available_block_event_types
    )


def get_paypal_custom(item_type, item_ids, voucher_code, user_email):
    return '{} {}{}{}'.format(
        item_type,
        item_ids,
        ' {}'.format(user_email),
        ' {}'.format(voucher_code) if voucher_code else '',
    )