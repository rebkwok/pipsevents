#TODO
'''
Email warnings for unpaid bookings
Check for bookings where:
event.payment_open == True
booking.status == OPEN
booking.paid = False

event.date - event.payment_due_date is less than a certain amount
OR
event.date - cancellation_period is less than a certain amount

Add first_warning_sent and second_warning_sent flags to booking model so
we don't keep sending
'''