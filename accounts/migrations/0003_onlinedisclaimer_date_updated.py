# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_auto_20160110_2059'),
    ]

    operations = [
        migrations.AddField(
            model_name='onlinedisclaimer',
            name='date_updated',
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]
