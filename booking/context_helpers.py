"""
Helper functions to return context and reduce logic in templates
"""

from django.utils import timezone

def get_event_context(context, event, user):

        # payment info text to be displayed
        if event.cost == 0:
            payment_text = "There is no cost associated with this event."
        else:
            if not event.payment_open:
                payment_text = "Payments are not yet open. Payment information will be" \
                               "provided closer to the event date."
            else:
                payment_text = event.payment_info
        context['payment_text'] = payment_text

        # booked flag
        user_bookings = user.bookings.all()
        user_booked_events = [booking.event for booking in user_bookings]
        booked = event in user_booked_events

        # booking info text and book button
        booking_info_text = ""
        if booked:
            context['booked'] = True
            booking_info_text = "You have booked for this event."
        else:
            if event.max_participants:
                if event.spaces_left():
                    context['include_book_button'] = True
                else:
                    booking_info_text = "This event is now full."
            else:
                context['include_book_button'] = True
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


    return context



