# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0009_auto_20150126_2214'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='cost',
            field=models.DecimalField(default=0, max_digits=8, decimal_places=2),
            preserve_default=True,
        ),
    ]
