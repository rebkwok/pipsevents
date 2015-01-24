# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django_extensions.db.fields


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0004_event_slug'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='slug',
            field=django_extensions.db.fields.AutoSlugField(editable=False, populate_from=b'name', max_length=40, blank=True, unique=True),
            preserve_default=True,
        ),
    ]
