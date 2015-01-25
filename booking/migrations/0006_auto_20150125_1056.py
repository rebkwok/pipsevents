# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0005_auto_20150124_2340'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='booking',
            unique_together=set([('user', 'event')]),
        ),
    ]
