# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0030_auto_20151015_0932'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticketbooking',
            name='cancelled',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='ticketbooking',
            name='date_rebooked',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
