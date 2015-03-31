# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0003_auto_20150330_2032'),
    ]

    operations = [
        migrations.RenameField(
            model_name='blocktype',
            old_name='eventtype',
            new_name='event_type',
        ),
        migrations.RenameField(
            model_name='event',
            old_name='eventtype',
            new_name='event_type',
        ),
    ]
