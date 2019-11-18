import hashlib
import random


from payments.models import PaypalBookingTransaction, PaypalBlockTransaction, \
    PaypalGiftVoucherTransaction, PaypalTicketBookingTransaction


def create_booking_paypal_transaction(user, booking):
    # truncate username to avoid making invoice ids that
    # are too long for the django-paypal ipn invoice model field
    username = user.username[:50]
    id_string = "-".join([username] + [
        "".join([word[0] for word in booking.event.name.split()])
    ] + [booking.event.date.strftime("%d%m%y%H%M")] + ['inv#'])
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


def create_multibooking_paypal_transaction(user, bookings):
    # invoice number is a hash of bookings so we can make sure the same cart
    # has the same invoice number (i.e. user doesn't paypal and then return to
    # the cart before paypal has update and resubmit
    username = user.username[:50]
    bookings_hash = hashlib.md5(
        ', '.join([str(booking) for booking in bookings]).encode('utf-8')
    ).hexdigest()
    invoice_id = '{}-{}'.format(username, bookings_hash)

    for booking in bookings:
        # check for existing PBT without transaction id stored and delete
        # so we replace with this one
        PaypalBookingTransaction.objects.filter(
            booking=booking, transaction_id__isnull=True
        ).exclude(invoice_id=invoice_id).delete()
        # get_or_create in case we're going back to this same shopping basket
        # again; PBT is created when the shopping basket view is called
        PaypalBookingTransaction.objects.get_or_create(
            invoice_id=invoice_id, booking=booking
        )

    return invoice_id


def create_multiblock_paypal_transaction(user, blocks):
    # invoice number is a hash of block id and block so we can make sure the same cart
    # has the same invoice number (i.e. user doesn't paypal and then return to
    # the cart before paypal has update and resubmit
    # need to use id here as well as a block might be deleted and re-added
    username = user.username[:50]
    bookings_hash = hashlib.md5(
        ', '.join(['{}{}'.format(block.id, block) for block in blocks]).encode('utf-8')
    ).hexdigest()
    invoice_id = '{}-{}'.format(username, bookings_hash)

    for block in blocks:
        # check for existing PBT without transaction id stored and delete
        # so we replace with this one
        PaypalBlockTransaction.objects.filter(
            block=block, transaction_id__isnull=True
        ).exclude(invoice_id=invoice_id).delete()
        # get_or_create in case we're going back to this same shopping basket
        # again; PBT is created when the shopping basket view is called
        PaypalBlockTransaction.objects.get_or_create(
            invoice_id=invoice_id, block=block
        )

    return invoice_id


def create_block_paypal_transaction(user, block):
    username = user.username[:50]
    id_string = "-".join([username] +
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


def create_gift_voucher_paypal_transaction(voucher_type, voucher_code):
    id_string = f"gift-voucher-{voucher_type}-{voucher_code}-inv#"
    existing = PaypalGiftVoucherTransaction.objects.filter(
        invoice_id__contains=id_string, voucher_type=voucher_type, voucher_code=voucher_code
    ).order_by('-invoice_id')

    if existing:
        # PaypalGiftVoucherTransaction is created when the view is called, not when
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
    existing_inv = PaypalGiftVoucherTransaction.objects.filter(invoice_id=invoice_id)
    if existing_inv:
        # in case we already have the same invoice id for a different
        # booking (the check for existing above checked for this exact
        # combination of invoice id and voucher_code
        random_prefix = random.randrange(100, 999)
        invoice_id = id_string + str(random_prefix) + counter

    pbt = PaypalGiftVoucherTransaction.objects.create(
        invoice_id=invoice_id, voucher_type=voucher_type, voucher_code=voucher_code
    )
    return pbt
