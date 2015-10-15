# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0031_auto_20151015_1006'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='ticketbooking',
            name='quantity',
        ),
    ]
