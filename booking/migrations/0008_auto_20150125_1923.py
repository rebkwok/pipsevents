# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0007_auto_20150125_1456'),
    ]

    operations = [
        migrations.AlterField(
            model_name='booking',
            name='paid',
            field=models.BooleanField(default=False, help_text=b'Tick to confirm payment has been made', verbose_name=b'Paid'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='event',
            name='location',
            field=models.CharField(default=b'Watermelon Studio', max_length=255),
            preserve_default=True,
        ),
        migrations.DeleteModel(
            name='Location',
        ),
        migrations.AlterField(
            model_name='event',
            name='max_participants',
            field=models.PositiveIntegerField(help_text=b'Leave blank if no max number of participants', null=True, blank=True),
            preserve_default=True,
        ),
    ]
