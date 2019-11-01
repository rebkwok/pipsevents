# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
from django.utils import timezone

def update_warning_dates(apps, schema_editor):
    # Add a date_warning_sent for any bookings for future events that have already had warning sent before the timestamp field existed
    Booking = apps.get_model('booking', 'Booking')
    TicketBooking = apps.get_model('booking', 'TicketBooking')
    now = timezone.now()

    for booking in Booking.objects.filter(event__date__gte=now, paid=False, warning_sent=True, status="OPEN"):
        if not booking.date_warning_sent:
            booking.date_warning_sent = now
            booking.save()

    for ticket_booking in TicketBooking.objects.filter(ticketed_event__date__gte=now, paid=False, warning_sent=True, cancelled=False):
        if not ticket_booking.date_warning_sent:
            ticket_booking.date_warning_sent = now
            ticket_booking.save()


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0061_auto_20191101_0908'),
    ]

    operations = [
        migrations.RunPython(
            update_warning_dates, reverse_code=migrations.RunPython.noop
        )
    ]
