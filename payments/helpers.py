import random
from django.db import IntegrityError

from payments.models import PaypalBookingTransaction, PaypalBlockTransaction, \
    PaypalTicketBookingTransaction


def create_booking_paypal_transaction(user, booking):
    id_string = "-".join([user.username] +
                         ["".join([word[0] for word in
                                   booking.event.name.split()])] +
                         [booking.event.date.strftime("%d%m%y%H%M")] + ['inv#'])
    existing = PaypalBookingTransaction.objects.filter(
        invoice_id__contains=id_string, booking=booking).order_by('-invoice_id')

    if existing:
        # PaypalBookingTransaction is created when the view is called, not when
        # payment is made.  If there is no transaction id stored against it,
        # we shouldn't need to make a new one
        for transaction in existing:
            if not transaction.transaction_id:
                return transaction
        existing_counter = existing[0].invoice_id[-3:]
        counter = str(int(existing_counter) + 1).zfill(len(existing_counter))
    else:
        counter = '001'

    invoice_id = id_string + counter
    existing_inv = PaypalBookingTransaction.objects.filter(
        invoice_id=invoice_id
    )
    if existing_inv:
        # in case we already have the same invoice id for a different
        # booking (the check for existing above checked for this exact
        # combination of invoice id and booking
        random_prefix = random.randrange(100, 999)
        invoice_id = id_string + str(random_prefix) + counter

    pbt = PaypalBookingTransaction.objects.create(
        invoice_id=invoice_id, booking=booking
    )
    return pbt


def create_block_paypal_transaction(user, block):

    id_string = "-".join([user.username] +
                         ["".join([word[0] for word in
                          block.block_type.event_type.subtype.split()])] +
                         [str(block.block_type.size)] +
                         [block.start_date.strftime("%d%m%y%H%M")] + ['inv#'])

    existing = PaypalBlockTransaction.objects.filter(
        invoice_id__contains=id_string, block=block).order_by('-invoice_id')

    if existing:
        # PaypalBlockTransaction is created when the view is called, not when
        # payment is made.  If there is no transaction id stored against it,
        # we shouldn't need to make a new one
        for transaction in existing:
            if not transaction.transaction_id:
                return transaction
        existing_counter = existing[0].invoice_id[-3:]
        counter = str(int(existing_counter) + 1).zfill(len(existing_counter))
    else:
        counter = '001'

    invoice_id = id_string + counter
    existing_inv = PaypalBlockTransaction.objects.filter(
        invoice_id=invoice_id
    )

    if existing_inv:
        # in case we already have the same invoice id for a different
        # block (the check for existing above checked for this exact
        # combination of invoice id and block
        random_prefix = random.randrange(100, 999)
        invoice_id = id_string + str(random_prefix) + counter

    pbt = PaypalBlockTransaction.objects.create(
        invoice_id=invoice_id, block=block
    )
    return pbt


def create_ticket_booking_paypal_transaction(user, ticket_booking):

    existing = PaypalTicketBookingTransaction.objects.filter(
        invoice_id__contains=ticket_booking.booking_reference,
        ticket_booking=ticket_booking).order_by('-invoice_id')

    if existing:
        # PaypalTicketBookingTransaction is created when the view is called,
        # not when payment is made.  If people change their minds about the
        # quantity of tickets, we don't need to make a new one - check if
        # there is no transaction id stored against it,
        for transaction in existing:
            if not transaction.transaction_id:
                return transaction
        existing_counter = existing[0].invoice_id[-3:]
        counter = str(int(existing_counter) + 1).zfill(len(existing_counter))
    else:
        counter = '001'

    invoice_id = ticket_booking.booking_reference + counter
    existing_inv = PaypalTicketBookingTransaction.objects.filter(
        invoice_id=invoice_id
    )
    if existing_inv:
        # in case we already have the same invoice id for a different
        # booking (the check for existing above checked for this exact
        # combination of invoice id and booking
        random_prefix = random.randrange(100, 999)
        invoice_id = ticket_booking.booking_reference + str(random_prefix) + counter

    pbt = PaypalTicketBookingTransaction.objects.create(
        invoice_id=invoice_id, ticket_booking=ticket_booking
    )
    return pbt
