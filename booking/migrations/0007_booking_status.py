# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0006_auto_20150331_1907'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='status',
            field=models.CharField(choices=[('OPEN', 'Cancelled'), ('CANCELLED', 'Cancelled')], default='OPEN', max_length=255),
            preserve_default=True,
        ),
    ]
