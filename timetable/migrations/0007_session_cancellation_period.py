# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0006_auto_20150420_2154'),
    ]

    operations = [
        migrations.AddField(
            model_name='session',
            name='cancellation_period',
            field=models.PositiveIntegerField(default=24),
        ),
    ]
