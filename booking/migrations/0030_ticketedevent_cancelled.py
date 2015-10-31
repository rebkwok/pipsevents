# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0029_auto_20151020_1527'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticketedevent',
            name='cancelled',
            field=models.BooleanField(default=False),
        ),
    ]
