# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django_extensions.db.fields


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0002_auto_20150130_1217'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='type',
            field=models.CharField(default=b'PC', max_length=2, choices=[(b'PC', b'Pole level class'), (b'WS', b'Workshop'), (b'CL', b'Other class'), (b'EV', b'Other event')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='event',
            name='slug',
            field=django_extensions.db.fields.AutoSlugField(editable=False, populate_from=models.CharField(max_length=255), max_length=40, blank=True, unique=True),
            preserve_default=True,
        ),
    ]
