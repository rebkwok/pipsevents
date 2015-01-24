# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0002_auto_20150124_2136'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='paid',
            field=models.BooleanField(default=False),
            preserve_default=True,
        ),
    ]
