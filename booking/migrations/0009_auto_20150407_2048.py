# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0008_auto_20150405_1030'),
    ]

    operations = [
        migrations.AlterField(
            model_name='booking',
            name='block',
            field=models.ForeignKey(to='booking.Block', null=True, blank=True, related_name='bookings'),
        ),
    ]
