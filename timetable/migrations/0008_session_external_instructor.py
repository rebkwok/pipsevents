# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0007_session_cancellation_period'),
    ]

    operations = [
        migrations.AddField(
            model_name='session',
            name='external_instructor',
            field=models.BooleanField(default=False),
        ),
    ]
