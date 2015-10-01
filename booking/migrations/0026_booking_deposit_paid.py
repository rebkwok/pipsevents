# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0025_auto_20150828_1447'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='deposit_paid',
            field=models.BooleanField(default=False, help_text='Deposit payment has been made by user'),
        ),
    ]
