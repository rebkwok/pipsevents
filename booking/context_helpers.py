"""
Helper functions to return context and reduce logic in templates
"""

from django.utils import timezone


def get_event_context(context, event, user, event_type):

    context['type'] = event_type

    if event.date <= timezone.now():
        context['past'] = True

    # payment info text to be displayed
    if event.cost == 0:
        payment_text = "There is no cost associated with this event."
    else:
        if not event.payment_open:
            payment_text = "Payments are not yet open. Payment " \
                           "information will be provided closer to the " \
                           "event date."
        else:
            payment_text = event.payment_info
    context['payment_text'] = payment_text

    # booked flag
    user_bookings = user.bookings.all()
    user_booked_events = [booking.event for booking in user_bookings]
    booked = event in user_booked_events

    # booking info text and bookable
    booking_info_text = ""
    context['bookable'] = event.bookable()
    if booked:
        context['booked'] = True
        booking_info_text = "You have booked for this event."
        context['bookable'] = False
    elif not event.booking_open:
        booking_info_text = "Bookings are not yet open for this event."
    elif event.spaces_left() <= 0:
        booking_info_text = "This event is now full."
    elif not event.bookable():
        booking_info_text = "Bookings for this event are now closed."

    context['booking_info_text'] = booking_info_text

    return context


def get_booking_context(context, booking):

    # past booking
    if booking.event.date < timezone.now():
        context['past'] = True

    # payment info text to be displayed
    if booking.event.cost == 0:
        payment_text = "There is no cost associated with this event."
    else:
        if not booking.event.payment_open:
            payment_text = "Payments are not yet open. Payment information will " \
                           "be provided closer to the event date."
        else:
            payment_text = "Payments are open. " + booking.event.payment_info
    context['payment_text'] = payment_text

    # confirm payment button
    if booking.event.cost > 0 and not booking.paid \
            and booking.event.payment_open:
        context['include_confirm_payment_button'] = True

    # delete button
    context['can_cancel'] = booking.event.can_cancel()

    return context



