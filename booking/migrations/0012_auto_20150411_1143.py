# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0011_remove_event_payment_link'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='description',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='event',
            name='payment_due_date',
            field=models.DateTimeField(null=True, blank=True, help_text='If this date is set, make sure that it is earlier than the cancellation period.  Booking that are not paid will be automatically cancelled (a warning email will be sent to users first).'),
        ),
        migrations.AlterField(
            model_name='event',
            name='payment_open',
            field=models.BooleanField(default=True),
        ),
    ]
