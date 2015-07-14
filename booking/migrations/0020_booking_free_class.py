# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0019_auto_20150608_2058'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='free_class',
            field=models.BooleanField(default=False),
        ),
    ]
