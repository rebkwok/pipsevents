# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0002_auto_20150330_2031'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='blocktype',
            name='event_type',
        ),
        migrations.RemoveField(
            model_name='event',
            name='type',
        ),
    ]
