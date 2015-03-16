# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='cancellation_period',
            field=models.PositiveIntegerField(default=24, help_text='Minimum hours/days/weeks prior to event when cancellation is allowed'),
            preserve_default=True,
        ),
    ]
