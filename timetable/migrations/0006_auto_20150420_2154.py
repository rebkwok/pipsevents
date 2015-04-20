# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0005_auto_20150405_1030'),
    ]

    operations = [
        migrations.AddField(
            model_name='session',
            name='booking_open',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='session',
            name='payment_info',
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name='session',
            name='max_participants',
            field=models.PositiveIntegerField(help_text='Leave blank if no max number of participants', blank=True, default=10, null=True),
        ),
    ]
