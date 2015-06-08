# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0017_remove_booking_date_space_confirmed'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='email_studio_when_booked',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='eventtype',
            name='event_type',
            field=models.CharField(help_text="This determines whether events of this type are listed on the 'Classes' or 'Events' page", choices=[('CL', 'Class'), ('EV', 'Event')], max_length=2),
        ),
    ]
