# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0004_auto_20150330_2033'),
        ('timetable', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='session',
            name='event_type',
            field=models.ForeignKey(null=True, to='booking.EventType', on_delete=models.SET_NULL),
            preserve_default=True,
        ),
    ]
