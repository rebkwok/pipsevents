# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0012_auto_20150411_1143'),
    ]

    operations = [
        migrations.AlterField(
            model_name='booking',
            name='paid',
            field=models.BooleanField(help_text='Payment has been made by user', default=False),
        ),
    ]
