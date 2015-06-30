# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0010_session_advance_payment_required'),
    ]

    operations = [
        migrations.AlterField(
            model_name='session',
            name='description',
            field=models.TextField(blank=True, default=''),
        ),
    ]
