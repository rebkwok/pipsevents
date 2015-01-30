"""
Helper functions to return context and reduce logic in templates
"""


def get_event_context(context, event, user):

        # payment info text to be displayed
        if event.cost == 0:
            payment_text = "There is no cost associated with this event."
        if event.cost > 0 and not event.payment_open:
            payment_text = "Payments are not yet open. Payment information will be" \
                           "provided closer to the event date."
        if event.cost > 0 and event.payment_open:
            payment_text = event.payment_info
        context['payment_text'] = payment_text

        # booked flag
        user_bookings = user.bookings.all()
        user_booked_events = [booking.event for booking in user_bookings]
        booked = event in user_booked_events

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





