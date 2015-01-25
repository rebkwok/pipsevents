# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0006_auto_20150125_1056'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='payment_confirmed',
            field=models.BooleanField(default=False),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='event',
            name='payment_open',
            field=models.BooleanField(default=False),
            preserve_default=True,
        ),
    ]
