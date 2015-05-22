# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0015_merge'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='event',
            name='register_comments',
        ),
        migrations.AddField(
            model_name='event',
            name='external_instructor',
            field=models.BooleanField(default=False, help_text='Run by external instructor; booking and payment to be made with instructor directly'),
        ),
    ]
