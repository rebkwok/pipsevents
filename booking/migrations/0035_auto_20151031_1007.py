# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0034_auto_20151031_0922'),
    ]

    operations = [
        migrations.AlterField(
            model_name='eventtype',
            name='event_type',
            field=models.CharField(choices=[('CL', 'Class'), ('EV', 'Event'), ('RH', 'Room hire')], max_length=2, help_text="This determines whether events of this type are listed on the 'Classes', 'Workshops' or 'Room Hire' pages"),
        ),
    ]
