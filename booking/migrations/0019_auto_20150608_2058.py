# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0018_auto_20150608_0642'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='reminder_sent',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='booking',
            name='warning_sent',
            field=models.BooleanField(default=False),
        ),
    ]
