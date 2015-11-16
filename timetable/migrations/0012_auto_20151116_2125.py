# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0011_auto_20150630_2328'),
    ]

    operations = [
        migrations.AddField(
            model_name='session',
            name='allow_booking_cancellation',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='session',
            name='payment_time_allowed',
            field=models.PositiveIntegerField(help_text='Number of hours allowed for payment after booking (after this bookings will be cancelled.  Note that the automatic cancel job allows 6 hours after booking, so 6 hours is the minimum time that will be applied.', null=True, blank=True),
        ),
    ]
