# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0002_session_event_type'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='session',
            name='type',
        ),
    ]
