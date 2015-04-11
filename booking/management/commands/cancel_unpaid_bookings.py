#TODO
'''
Check for unpaid bookings and cancel where:
booking.status = OPEN
paid = False
payment_due_date < timezone.now()
Email user that their booking has been cancelled
'''