# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0008_auto_20150405_1030'),
        ('payments', '0002_invoiceid_booking'),
    ]

    operations = [
        migrations.CreateModel(
            name='PaypalTransaction',
            fields=[
                ('id', models.AutoField(primary_key=True, verbose_name='ID', serialize=False, auto_created=True)),
                ('invoice_id', models.CharField(max_length=255, unique=True, blank=True, null=True)),
                ('transaction_id', models.CharField(max_length=255, unique=True, blank=True, null=True)),
                ('booking', models.ForeignKey(to='booking.Booking', null=True)),
            ],
        ),
        migrations.RemoveField(
            model_name='invoiceid',
            name='booking',
        ),
        migrations.DeleteModel(
            name='InvoiceId',
        ),
    ]
