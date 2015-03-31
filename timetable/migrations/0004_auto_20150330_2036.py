# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0003_remove_session_type'),
    ]

    operations = [
        migrations.RenameField(
            model_name='session',
            old_name='event_type',
            new_name='type',
        ),
    ]
