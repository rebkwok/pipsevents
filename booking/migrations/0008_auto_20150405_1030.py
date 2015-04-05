# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0007_booking_status'),
    ]

    operations = [
        migrations.RenameField(
            model_name='eventtype',
            old_name='type',
            new_name='event_type',
        ),
        migrations.AlterField(
            model_name='event',
            name='contact_email',
            field=models.EmailField(max_length=254, default='thewatermelonstudio@hotmail.com'),
        ),
        migrations.AlterUniqueTogether(
            name='eventtype',
            unique_together=set([('event_type', 'subtype')]),
        ),
    ]
