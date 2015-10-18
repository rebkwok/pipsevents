# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0035_auto_20151018_2134'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticketedevent',
            name='extra_ticket_info1_required',
            field=models.BooleanField(help_text='Tick if this information is mandatory when booking tickets', default=False),
        ),
        migrations.AddField(
            model_name='ticketedevent',
            name='extra_ticket_info_required',
            field=models.BooleanField(help_text='Tick if this information is mandatory when booking tickets', default=False),
        ),
    ]
