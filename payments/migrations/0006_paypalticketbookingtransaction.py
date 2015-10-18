# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0034_ticketbooking_booking_reference'),
        ('payments', '0005_auto_20150407_2105'),
    ]

    operations = [
        migrations.CreateModel(
            name='PaypalTicketBookingTransaction',
            fields=[
                ('id', models.AutoField(primary_key=True, auto_created=True, verbose_name='ID', serialize=False)),
                ('invoice_id', models.CharField(null=True, blank=True, unique=True, max_length=255)),
                ('transaction_id', models.CharField(null=True, blank=True, unique=True, max_length=255)),
                ('ticket_booking', models.ForeignKey(null=True, to='booking.TicketBooking')),
            ],
        ),
    ]
