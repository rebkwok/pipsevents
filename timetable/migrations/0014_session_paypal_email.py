# -*- coding: utf-8 -*-
# Generated by Django 1.9.1 on 2016-03-10 09:21
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0013_auto_20160206_1026'),
    ]

    operations = [
        migrations.AddField(
            model_name='session',
            name='paypal_email',
            field=models.EmailField(default='test-paypal@watermelon.com', help_text='Email for the paypal account to be used for payment.  Check this carefully!', max_length=254),
        ),
    ]
