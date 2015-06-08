# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0008_session_external_instructor'),
    ]

    operations = [
        migrations.AddField(
            model_name='session',
            name='email_studio_when_booked',
            field=models.BooleanField(default=False),
        ),
    ]
