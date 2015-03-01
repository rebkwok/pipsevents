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
                ('id', models.AutoField(primary_key=True, serialize=False, auto_created=True, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('day', models.CharField(choices=[('01MON', 'Monday'), ('02TUE', 'Tuesday'), ('03WED', 'Wednesday'), ('04THU', 'Thursday'), ('05FRI', 'Friday'), ('06SAT', 'Saturday'), ('07SUN', 'Sunday')], max_length=5)),
                ('time', models.TimeField()),
                ('type', models.CharField(choices=[('PC', 'Pole level class'), ('CL', 'Other class')], default='PC', max_length=2)),
                ('description', models.TextField(blank=True)),
                ('location', models.CharField(default='Watermelon Studio', max_length=255)),
                ('max_participants', models.PositiveIntegerField(help_text='Leave blank if no max number of participants', blank=True, default=15, null=True)),
                ('contact_person', models.CharField(default='Gwen Burns', max_length=255)),
                ('contact_email', models.EmailField(default='thewatermelonstudio@hotmail.com', max_length=75)),
                ('cost', models.DecimalField(decimal_places=2, default=7, max_digits=8)),
                ('payment_open', models.BooleanField(default=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
    ]
