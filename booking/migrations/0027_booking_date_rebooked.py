# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0026_booking_deposit_paid'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='date_rebooked',
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]
