# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0008_auto_20150405_1030'),
        ('payments', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoiceid',
            name='booking',
            field=models.ForeignKey(null=True, to='booking.Booking'),
        ),
    ]
