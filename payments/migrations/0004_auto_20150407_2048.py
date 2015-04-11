# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0009_auto_20150407_2048'),
        ('payments', '0003_auto_20150406_1629'),
    ]

    operations = [
        migrations.CreateModel(
            name='PaypalBlockTransaction',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('invoice_id', models.CharField(null=True, unique=True, max_length=255, blank=True)),
                ('transaction_id', models.CharField(null=True, unique=True, max_length=255, blank=True)),
                ('booking', models.ForeignKey(to='booking.Booking', null=True)),
            ],
        ),
        migrations.CreateModel(
            name='PaypalBookingTransaction',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('invoice_id', models.CharField(null=True, unique=True, max_length=255, blank=True)),
                ('transaction_id', models.CharField(null=True, unique=True, max_length=255, blank=True)),
                ('booking', models.ForeignKey(to='booking.Booking', null=True)),
            ],
        ),
        migrations.RemoveField(
            model_name='paypaltransaction',
            name='booking',
        ),
        migrations.DeleteModel(
            name='PaypalTransaction',
        ),
    ]
