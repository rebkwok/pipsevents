from django.db import models

from paypal.standard.models import ST_PP_COMPLETED
from paypal.standard.ipn.signals import valid_ipn_received, invalid_ipn_received

from booking.models import Booking


class InvoiceId(models.Model):
    invoice_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    booking = models.ForeignKey(Booking, null=True)

    def __str__(self):
        return self.invoice_id


def create_invoice_id(user, booking):

    id_string = "-".join([user.username] +
                         booking.event.name.split() +
                         booking.event.date.strftime("%d %b %y %H:%M"
                                                     ).split() + ['inv#'])

    existing = InvoiceId.objects.filter(
        invoice_id__contains=id_string, booking=booking).order_by('-invoice_id')

    if existing:
        existing_counter = existing[0].invoice_id[-2:]
        counter = str(int(existing_counter) + 1).zfill(len(existing_counter))
    else:
        counter = '01'
    return InvoiceId.objects.create(
        invoice_id=id_string+counter, booking=booking
    )


def payment_received(sender, **kwargs):
    ipn_obj = sender
    import ipdb; ipdb.set_trace()
    if ipn_obj.payment_status == ST_PP_COMPLETED:
        # Undertake some action depending upon `ipn_obj`.
        booking = Booking.objects.get(id=int(ipn_obj.custom))
        booking.paid = True
        booking.payment_confirmed = True
        booking.date_payment_confirmed = True
        booking.save()

def payment_not_received(sender, **kwargs):
    ipn_obj = sender
    import ipdb; ipdb.set_trace()
    if ipn_obj.payment_status == ST_PP_COMPLETED:
        # Undertake some action depending upon `ipn_obj`.
        booking = Booking.objects.get(id=int(ipn_obj.custom))
        booking.paid = True
        booking.payment_confirmed = True
        booking.date_payment_confirmed = True
        booking.save()

valid_ipn_received.connect(payment_received)
invalid_ipn_received.connect(payment_not_received)