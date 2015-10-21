# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0030_ticketedevent_cancelled'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ticketedevent',
            name='show_on_site',
            field=models.BooleanField(help_text='Tick to show on the site and allow ticket bookings', default=True),
        ),
    ]
