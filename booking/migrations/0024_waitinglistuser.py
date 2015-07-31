# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.utils.timezone
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('booking', '0023_auto_20150730_1002'),
    ]

    operations = [
        migrations.CreateModel(
            name='WaitingListUser',
            fields=[
                ('id', models.AutoField(primary_key=True, verbose_name='ID', auto_created=True, serialize=False)),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now)),
                ('event', models.ForeignKey(related_name='waitinglistusers', to='booking.Event')),
                ('user', models.ForeignKey(related_name='waitinglists', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
