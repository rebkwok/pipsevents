# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0009_auto_20150407_2048'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='block',
            name='payment_confirmed',
        ),
        migrations.AlterField(
            model_name='block',
            name='paid',
            field=models.BooleanField(help_text='Payment has been made by user', default=False, verbose_name='Paid'),
        ),
        migrations.AlterField(
            model_name='booking',
            name='status',
            field=models.CharField(choices=[('OPEN', 'Open'), ('CANCELLED', 'Cancelled')], max_length=255, default='OPEN'),
        ),
        migrations.AlterField(
            model_name='event',
            name='advance_payment_required',
            field=models.BooleanField(default=True),
        ),
    ]
