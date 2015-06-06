# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0016_auto_20150522_1753'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='booking',
            name='date_space_confirmed',
        ),
    ]
