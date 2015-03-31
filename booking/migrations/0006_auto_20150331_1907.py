# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0005_auto_20150331_1728'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='eventtype',
            unique_together=set([('type', 'subtype')]),
        ),
    ]
