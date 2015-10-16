# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0033_auto_20151016_0812'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticketbooking',
            name='booking_reference',
            field=models.CharField(default=1, max_length=255),
            preserve_default=False,
        ),
    ]
