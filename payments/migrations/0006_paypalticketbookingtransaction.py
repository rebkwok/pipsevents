# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0029_auto_20151020_1527'),
        ('payments', '0005_auto_20150407_2105'),
    ]

    operations = [
        migrations.CreateModel(
            name='PaypalTicketBookingTransaction',
            fields=[
                ('id', models.AutoField(serialize=False, verbose_name='ID', primary_key=True, auto_created=True)),
                ('invoice_id', models.CharField(max_length=255, unique=True, blank=True, null=True)),
                ('transaction_id', models.CharField(max_length=255, unique=True, blank=True, null=True)),
                ('ticket_booking', models.ForeignKey(null=True, to='booking.TicketBooking', on_delete=models.SET_NULL)),
            ],
        ),
    ]
