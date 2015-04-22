# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0012_auto_20150411_1143'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='attended',
            field=models.BooleanField(help_text='Student has attended this event', default=False),
        ),
        migrations.AddField(
            model_name='event',
            name='register_comments',
            field=models.TextField(blank=True, help_text='Enter any comments on the register for this event e.g. notes on drop in students who do not have an online account yet.', null=True),
        ),
        migrations.AlterField(
            model_name='booking',
            name='paid',
            field=models.BooleanField(help_text='Payment has been made by user', default=False),
        ),
    ]
