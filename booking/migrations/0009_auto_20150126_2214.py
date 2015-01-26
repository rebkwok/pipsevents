# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0008_auto_20150125_1923'),
    ]

    operations = [
        migrations.AlterField(
            model_name='booking',
            name='paid',
            field=models.BooleanField(default=False, help_text=b'Payment has been made by user', verbose_name=b'Payment made (as confirmed by particpant'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='booking',
            name='payment_confirmed',
            field=models.BooleanField(default=False, help_text=b'Payment confirmed by admin/organiser'),
            preserve_default=True,
        ),
    ]
