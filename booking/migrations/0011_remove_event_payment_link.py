# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0010_auto_20150410_0713'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='event',
            name='payment_link',
        ),
    ]
