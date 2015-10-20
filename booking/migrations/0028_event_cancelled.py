# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0027_booking_date_rebooked'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='cancelled',
            field=models.BooleanField(default=False),
        ),
    ]
