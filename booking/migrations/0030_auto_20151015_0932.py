# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0029_auto_20151015_0846'),
    ]

    operations = [
        migrations.RenameField(
            model_name='ticketbooking',
            old_name='event',
            new_name='ticketed_event',
        ),
    ]
