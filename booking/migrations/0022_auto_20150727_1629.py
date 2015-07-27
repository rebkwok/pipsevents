# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0021_auto_20150716_1519'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='block',
            options={'ordering': ['user__username']},
        ),
        migrations.AlterModelOptions(
            name='event',
            options={'ordering': ['-date']},
        ),
    ]
