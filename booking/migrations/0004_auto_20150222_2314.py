# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0003_auto_20150222_1518'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='date_booked',
            field=models.DateTimeField(default=django.utils.timezone.now),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='booking',
            name='date_payment_confirmed',
            field=models.DateTimeField(null=True, blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='booking',
            name='date_space_confirmed',
            field=models.DateTimeField(null=True, blank=True),
            preserve_default=True,
        ),
    ]
