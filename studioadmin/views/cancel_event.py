from booking.models import Block, BlockType, Booking
from activitylog.models import ActivityLog

def cancel_event(event, transfer_direct_paid=True, transfer_expired_blocks=True):
    open_bookings = Booking.objects.filter(
        event=event, status='OPEN', no_show=False
    )
    open_free_non_block = [
        bk for bk in open_bookings if bk.free_class and not bk.block
        ]
    open_direct_paid = [
        bk for bk in open_bookings if not bk.block
        and not bk.free_class and bk.paid
    ]

    for booking in open_bookings:
        direct_paid = booking in open_direct_paid or booking in open_free_non_block

        if booking.block and not booking.block.expired:
            booking.block = None
            booking.deposit_paid = False
            booking.paid = False
            booking.payment_confirmed = False
            # in case this was paid with a free class block
            booking.free_class = False

        elif (direct_paid and transfer_direct_paid) or (booking.block and booking.block.expired and transfer_expired_blocks):
            # direct paid = paypal and free non-block paid
            # create transfer block and make this booking unpaid
            if booking.event.event_type.event_type != 'EV':
                block_type = BlockType.get_transfer_block_type(booking.event.event_type)
                Block.objects.create(
                    block_type=block_type, user=booking.user,
                    transferred_booking_id=booking.id
                )

                booking.block = None  # need to reset block if booked
                # with block that's now expired
                booking.deposit_paid = False
                booking.paid = False
                booking.payment_confirmed = False
                booking.free_class = False

        booking.status = "CANCELLED"
        booking.save()

    event.cancelled = True
    event.booking_open = False
    event.payment_open = False
    event.save()

    ActivityLog.objects.create(
        log=f"Class {event} cancelled offline by admin user rebkwok; {open_bookings.count()} bookings cancelled"
    )
