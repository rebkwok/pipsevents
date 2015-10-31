# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0033_auto_20151025_0852'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ticketedevent',
            name='payment_time_allowed',
            field=models.PositiveIntegerField(blank=True, null=True, help_text='Number of hours allowed for payment after booking (after this ticket purchases will be cancelled.  Note that the automatic cancel job allows 6 hours after booking, so 6 hours is the minimum time that will be applied.'),
        ),
    ]
