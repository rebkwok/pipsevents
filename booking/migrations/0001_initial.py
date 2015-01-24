# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Booking',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('date', models.DateTimeField()),
                ('max_participants', models.PositiveIntegerField(null=True, blank=True)),
                ('contact_person', models.CharField(default=b'Gwen Burns', max_length=255)),
                ('contact_email', models.EmailField(default=b'thewatermelonstudio@hotmail.com', max_length=75)),
                ('payment_info', models.TextField(blank=True)),
                ('payment_due_date', models.DateTimeField(null=True, blank=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Location',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=255)),
                ('address', models.CharField(max_length=255)),
                ('city', models.CharField(max_length=255)),
                ('postcode', models.CharField(max_length=255)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.AddField(
            model_name='event',
            name='location',
            field=models.ForeignKey(related_name='events', to='booking.Location'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='booking',
            name='event',
            field=models.ForeignKey(related_name='bookings', to='booking.Event'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='booking',
            name='user',
            field=models.ForeignKey(related_name='bookings', to=settings.AUTH_USER_MODEL),
            preserve_default=True,
        ),
    ]
