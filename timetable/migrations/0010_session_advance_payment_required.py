# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0009_session_email_studio_when_booked'),
    ]

    operations = [
        migrations.AddField(
            model_name='session',
            name='advance_payment_required',
            field=models.BooleanField(default=True),
        ),
    ]
