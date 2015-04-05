# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0004_auto_20150330_2036'),
    ]

    operations = [
        migrations.RenameField(
            model_name='session',
            old_name='type',
            new_name='event_type',
        ),
        migrations.AlterField(
            model_name='session',
            name='contact_email',
            field=models.EmailField(max_length=254, default='thewatermelonstudio@hotmail.com'),
        ),
    ]
