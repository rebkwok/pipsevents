# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0036_event_payment_time_allowed'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='free_class_requested',
            field=models.BooleanField(default=False),
        ),
    ]
