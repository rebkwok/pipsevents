# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0009_auto_20150407_2048'),
        ('payments', '0004_auto_20150407_2048'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='paypalblocktransaction',
            name='booking',
        ),
        migrations.AddField(
            model_name='paypalblocktransaction',
            name='block',
            field=models.ForeignKey(null=True, to='booking.Block'),
        ),
    ]
