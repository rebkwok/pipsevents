# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings
import django_extensions.db.fields


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Booking',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('paid', models.BooleanField(default=False, help_text=b'Payment has been made by user', verbose_name=b'Payment made (as confirmed by particpant')),
                ('payment_confirmed', models.BooleanField(default=False, help_text=b'Payment confirmed by admin/organiser')),
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
                ('location', models.CharField(default=b'Watermelon Studio', max_length=255)),
                ('max_participants', models.PositiveIntegerField(help_text=b'Leave blank if no max number of participants', null=True, blank=True)),
                ('contact_person', models.CharField(default=b'Gwen Burns', max_length=255)),
                ('contact_email', models.EmailField(default=b'thewatermelonstudio@hotmail.com', max_length=75)),
                ('cost', models.DecimalField(default=0, max_digits=8, decimal_places=2)),
                ('payment_open', models.BooleanField(default=False)),
                ('payment_info', models.TextField(blank=True)),
                ('payment_due_date', models.DateTimeField(null=True, blank=True)),
                ('slug', django_extensions.db.fields.AutoSlugField(editable=False, populate_from=b'name', max_length=40, blank=True, unique=True)),
            ],
            options={
            },
            bases=(models.Model,),
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
        migrations.AlterUniqueTogether(
            name='booking',
            unique_together=set([('user', 'event')]),
        ),
    ]
