# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0031_auto_20151021_1127'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='ticketbooking',
            name='date_rebooked',
        ),
        migrations.AddField(
            model_name='ticketbooking',
            name='purchase_confirmed',
            field=models.BooleanField(default=False),
        ),
    ]
