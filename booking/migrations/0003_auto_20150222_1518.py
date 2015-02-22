# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django_extensions.db.fields
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0002_auto_20150201_1036'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='booking_open',
            field=models.BooleanField(default=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='block',
            name='block_size',
            field=models.CharField(default='SM', choices=[('SM', 'Five classes'), ('LG', 'Ten classes')], verbose_name='Number of classes in block', max_length=2),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='block',
            name='paid',
            field=models.BooleanField(default=False, verbose_name='Payment made (as confirmed by participant)', help_text='Payment has been made by user'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='block',
            name='payment_confirmed',
            field=models.BooleanField(default=False, help_text='Payment confirmed by admin/organiser'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='block',
            name='start_date',
            field=models.DateTimeField(default=django.utils.timezone.now),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='booking',
            name='paid',
            field=models.BooleanField(default=False, verbose_name='Payment made (as confirmed by participant)', help_text='Payment has been made by user'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='booking',
            name='payment_confirmed',
            field=models.BooleanField(default=False, help_text='Payment confirmed by admin/organiser'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='event',
            name='contact_email',
            field=models.EmailField(default='thewatermelonstudio@hotmail.com', max_length=75),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='event',
            name='contact_person',
            field=models.CharField(default='Gwen Burns', max_length=255),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='event',
            name='location',
            field=models.CharField(default='Watermelon Studio', max_length=255),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='event',
            name='max_participants',
            field=models.PositiveIntegerField(null=True, blank=True, help_text='Leave blank if no max number of participants'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='event',
            name='payment_link',
            field=models.URLField(blank=True, default='http://www.paypal.co.uk'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='event',
            name='slug',
            field=django_extensions.db.fields.AutoSlugField(blank=True, max_length=40, populate_from='name', editable=False, unique=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='event',
            name='type',
            field=models.CharField(default='PC', choices=[('PC', 'Pole level class'), ('WS', 'Workshop'), ('CL', 'Other class'), ('EV', 'Other event')], max_length=2),
            preserve_default=True,
        ),
    ]
