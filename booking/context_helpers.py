"""
Helper functions to return context and reduce logic in templates
"""
import pytz

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone
from django.urls import reverse

from accounts.models import has_active_disclaimer, has_expired_disclaimer
from booking.models import Block, BlockType, Booking, WaitingListUser


def event_strings(event):
    """
    Return
    - event_type for url matching
    - ev_type_str: formatted singular string
    """
    ev_type_code = event.event_type.event_type
    if ev_type_code == 'CL':
        ev_type_for_url, ev_type_str = "lessons", "class"
    elif ev_type_code == 'EV':
        ev_type_for_url, ev_type_str = "events", "workshop/event"
    elif ev_type_code == 'OT':
        ev_type_for_url, ev_type_str =  "online_tutorials", "online tutorial"
    else:
        assert event.event_type.event_type == 'RH'
        ev_type_for_url, ev_type_str =  "room_hires", "room hire"
    return ev_type_code, ev_type_for_url, ev_type_str

def get_event_context(context, event, user, booking=None):
    disclaimer = has_active_disclaimer(user)
    expired_disclaimer = has_expired_disclaimer(user)
    context['disclaimer'] = disclaimer
    context['expired_disclaimer'] = expired_disclaimer

    ev_type_code, ev_type_for_url, ev_type_str = event_strings(event)
    context["ev_type_code"] = ev_type_code
    context['ev_type_for_url'] = ev_type_for_url
    context['ev_type_str'] = ev_type_str

    if event.date <= timezone.now():
        context['past'] = True

    # payment info text to be displayed
    if event.cost == 0:
        payment_text = "There is no cost associated with this {}.".format(
            ev_type_str
        )
    else:
        if not event.payment_open:
            payment_text = "Online payments are not open. " + event.payment_info
        else:
            payment_text = "Online payments are open. " + event.payment_info
    context['payment_text'] = payment_text

    # booked flag
    any_user_booking = booking or user.bookings.filter(event=event).first()
    if any_user_booking:
        user_booking = (
            any_user_booking if any_user_booking.status == "OPEN" and not any_user_booking.no_show
            else None
        )
        user_cancelled = any_user_booking.status == "CANCELLED"
        auto_cancelled = user_cancelled and any_user_booking.auto_cancelled
        user_no_show = any_user_booking.status == "OPEN" and any_user_booking.no_show
        cancelled = user_cancelled or user_no_show

    else:
        user_booking = None
        cancelled = auto_cancelled = False
    

    # waiting_list flag
    context['on_waiting_list'] = user.waitinglists.filter(event=event).exists()

    # booking info text and bookable
    booking_info_text = ""
    context['bookable'] = event.bookable
    if event.event_type.subtype == "Online class":
        context["online_class"] = True
        context["show_video_link"] = event.show_video_link

    if user_booking is not None:
        context['bookable'] = False
        context['booking'] = user_booking
        context['booked'] = True
        if event.event_type.event_type == 'OT':
            if context['booking'].paid:
                booking_info_text = "You have purchased this {}.".format(ev_type_str)
        else:
            booking_info_text = "You have booked for this {}.".format(ev_type_str)

    elif not disclaimer:
        action = "purchasing" if event.event_type.event_type == 'OT' else "booking"
        if expired_disclaimer:
            booking_info_text = "<strong>Please update your <a href='{}' " \
                                "target=_blank>disclaimer form</a> before " \
                                "{}.</strong>".format(
                                    reverse('disclaimer_form'), action
                                )
        else:
            booking_info_text = "<strong>Please complete a <a href='{}' " \
                                "target=_blank>disclaimer form</a> before " \
                                "{}.</strong>".format(
                                    reverse('disclaimer_form'), action
                                )
    elif not event.has_permission_to_book(user):
        context['bookable'] = False
        context['needs_permission'] = True
        description = event.allowed_group_description
        if event.members_only:
            permission_msg = f"This {ev_type_str} is open to members only."
        else:
            extra_info = f" ({description})" if description else ""
            permission_msg = (
                f"This class requires additional permission{extra_info}. Please contact "
                f"<a href='mailto:{event.contact_email}' target=_blank>{event.contact_email}</a> "
                "to request to have your account upgraded.</span>"
            )

        booking_info_text = f"<span class='cancel-warning'>NOT AVAILABLE FOR BOOKING</br>{permission_msg}"
    else:
        if auto_cancelled:
            context['auto_cancelled'] = True
            booking_info_text_cancelled = "To rebook this {} please contact " \
                                          "{} directly.".format(
                                            ev_type_str, event.contact_email
                                            )
            context['booking_info_text_cancelled'] = booking_info_text_cancelled
        elif cancelled:
            context['cancelled'] = True
            booking_info_text_cancelled = "You have previously booked for " \
                                          "this {} and your booking has been " \
                                          "cancelled.".format(ev_type_str)
            context['booking_info_text_cancelled'] = booking_info_text_cancelled

        if event.event_type.subtype == "External instructor class":
            booking_info_text = "Please contact {} directly to book".format(event.contact_person)
        elif not event.booking_open:
            target = "Purchases" if event.event_type.event_type == 'OT' else "Bookings"
            booking_info_text = "{} are not open for this {}.".format(
                target, ev_type_str
            )
        if event.spaces_left <= 0:
            booking_info_text = "This {} is now full.".format(ev_type_str)
        if event.payment_due_date:
            if event.payment_due_date < timezone.now():
                booking_info_text = "The payment due date has passed for " \
                                    "this {}.  Please make your payment as " \
                                    "soon as possible to secure your " \
                                    "place.".format(ev_type_str)

    context['booking_info_text'] = booking_info_text

    # get payment due date
    uk_tz = pytz.timezone('Europe/London')

    cancellation_due_date = event.date - timedelta(
        hours=(event.cancellation_period)
    )
    cancellation_due_date = cancellation_due_date.astimezone(uk_tz)
    context['cancellation_due_date'] = cancellation_due_date

    return context


def get_booking_update_context(event, request, context):
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

    if event.event_type.event_type == 'EV':
        ev_type = 'workshop/event'
    elif event.event_type.event_type == 'CL':
        ev_type = 'class'
    elif event.event_type.event_type == 'OT':
        ev_type = 'online tutorial'
    else:
        ev_type = 'room hire'

    context['ev_type'] = ev_type

    return context


def get_paypal_dict(
        request, cost, item_name, invoice_id, custom,
        paypal_email=settings.DEFAULT_PAYPAL_EMAIL, quantity=1):

    paypal_dict = {
        "business": paypal_email,
        "amount": cost,
        "item_name": str(item_name)[:127],
        "custom": custom,
        "invoice": invoice_id,
        "currency_code": "GBP",
        "quantity": quantity,
        "notify_url": request.build_absolute_uri(reverse('paypal-ipn')),
        "return": request.build_absolute_uri(reverse('payments:paypal_confirm')),
        "cancel_return": request.build_absolute_uri(reverse('payments:paypal_cancel')),
    }
    return paypal_dict


def get_paypal_cart_dict(
        request, item_type, items, invoice_id, custom,
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
        "notify_url": request.build_absolute_uri(reverse('paypal-ipn')),
        "return": request.build_absolute_uri(reverse('payments:paypal_confirm')),
        "cancel_return": request.build_absolute_uri(reverse('payments:paypal_cancel')),
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

    allowed_identifiers = ["transferred", "free", "substitute", "online transfer"]
    # A user can only purchase blocks if they don't already have another block of the 
    # same type that is either:
    #  - active (paid, unexpired, not full)
    #  - unpaid, unexpired, not full (i.e. in shopping cart)
    # transfers/free/substitute blocks don't count
    available_block_event_types = [
        block.block_type.event_type for block in user_blocks
        if (block.active_block() or (not block.paid and not block.expired and not block.full))
        and not any(
            [
                True for allowed_identifier in allowed_identifiers
                if block.block_type.identifier and block.block_type.identifier.lower().startswith(allowed_identifier)
            ]  
        ) 
    ]
    return BlockType.objects.filter(active=True).exclude(
        event_type__in=available_block_event_types
    )


def get_paypal_custom(item_type, item_ids, voucher_code=None, voucher_applied_to=None, user_email=None):
    if voucher_applied_to:
        voucher_applied_to = ",".join([str(applied_id) for applied_id in voucher_applied_to])
    # we use k=v pairs for diambiguation in the custom field, but abbreviate because
    # there is a 256 char limit
    custom = f"obj={item_type} ids={item_ids}"
    if user_email:
        custom = f"{custom} usr={user_email}"
    if voucher_code:
        custom = f"{custom} cde={voucher_code}"
    if voucher_applied_to:
        custom = f"{custom} apd={voucher_applied_to}"
    return custom
