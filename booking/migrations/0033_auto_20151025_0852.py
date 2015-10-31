# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0032_auto_20151021_1221'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='ticketbooking',
            name='date_payment_confirmed',
        ),
        migrations.RemoveField(
            model_name='ticketbooking',
            name='payment_confirmed',
        ),
    ]
