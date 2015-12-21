# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0038_event_allow_booking_cancellation'),
    ]

    operations = [
        migrations.AddField(
            model_name='blocktype',
            name='active',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='blocktype',
            name='identifier',
            field=models.CharField(max_length=255, blank=True, help_text='Optional identifier for individual or group of block types (e.g. sale blocks)', null=True),
        ),
    ]
