# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0020_booking_free_class'),
    ]

    operations = [
        migrations.AlterField(
            model_name='booking',
            name='block',
            field=models.ForeignKey(null=True, to='booking.Block', related_name='bookings', on_delete=django.db.models.deletion.SET_NULL, blank=True),
        ),
    ]
