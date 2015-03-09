# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Session',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=255)),
                ('day', models.CharField(max_length=5, choices=[('01MON', 'Monday'), ('02TUE', 'Tuesday'), ('03WED', 'Wednesday'), ('04THU', 'Thursday'), ('05FRI', 'Friday'), ('06SAT', 'Saturday'), ('07SUN', 'Sunday')])),
                ('time', models.TimeField()),
                ('type', models.CharField(max_length=2, choices=[('PC', 'Pole level class'), ('CL', 'Other class')], default='PC')),
                ('description', models.TextField(blank=True)),
                ('location', models.CharField(max_length=255, default='Watermelon Studio')),
                ('max_participants', models.PositiveIntegerField(blank=True, default=15, null=True, help_text='Leave blank if no max number of participants')),
                ('contact_person', models.CharField(max_length=255, default='Gwen Burns')),
                ('contact_email', models.EmailField(max_length=75, default='thewatermelonstudio@hotmail.com')),
                ('cost', models.DecimalField(default=7, max_digits=8, decimal_places=2)),
                ('payment_open', models.BooleanField(default=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
    ]
