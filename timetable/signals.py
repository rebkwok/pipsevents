from django.db.models.signals import pre_save
from django.dispatch import receiver

from booking.models import Event
from timetable.models import Session


@receiver(pre_save, sender=Session)
def session_pre_save(sender, instance, *args, **kwargs):
    instance.location_index = Event.LOCATION_INDEX_MAP[instance.location]
    if not instance.cost:
        instance.advance_payment_required = False
        instance.payment_open = False
        instance.payment_time_allowed = None
    if instance.payment_time_allowed:
        instance.advance_payment_required = True
    if instance.external_instructor:
        # if external_instructor, make sure payment_open and booking_open
        # are False
        instance.payment_open = False
        instance.booking_open = False