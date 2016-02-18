# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.utils.timezone
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Disclaimer',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('date', models.DateTimeField(default=django.utils.timezone.now)),
                ('terms_accepted', models.BooleanField()),
                ('user', models.OneToOneField(related_name='disclaimer', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
