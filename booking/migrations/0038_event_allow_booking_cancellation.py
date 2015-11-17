# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0037_booking_free_class_requested'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='allow_booking_cancellation',
            field=models.BooleanField(default=True),
        ),
    ]
