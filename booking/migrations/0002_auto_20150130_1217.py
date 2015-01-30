# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='advance_payment_required',
            field=models.BooleanField(default=False),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='event',
            name='payment_link',
            field=models.URLField(default=b'http://www.paypal.co.uk', blank=True),
            preserve_default=True,
        ),
    ]
