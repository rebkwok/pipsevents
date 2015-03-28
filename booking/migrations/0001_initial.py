# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings
import django.utils.timezone
import django_extensions.db.fields


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Block',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, primary_key=True, auto_created=True)),
                ('start_date', models.DateTimeField(default=django.utils.timezone.now)),
                ('paid', models.BooleanField(verbose_name='Payment made (as confirmed by participant)', help_text='Payment has been made by user', default=False)),
                ('payment_confirmed', models.BooleanField(help_text='Payment confirmed by admin/organiser', default=False)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='BlockType',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, primary_key=True, auto_created=True)),
                ('size', models.PositiveIntegerField(help_text='Number of classes in block')),
                ('event_type', models.CharField(max_length=2, default='PC', choices=[('PC', 'Pole level class'), ('WS', 'Workshop'), ('CL', 'Other class'), ('EV', 'Other event')])),
                ('cost', models.DecimalField(max_digits=8, decimal_places=2)),
                ('duration', models.PositiveIntegerField(help_text='Number of months until block expires')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Booking',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, primary_key=True, auto_created=True)),
                ('paid', models.BooleanField(verbose_name='Payment made (as confirmed by participant)', help_text='Payment has been made by user', default=False)),
                ('date_booked', models.DateTimeField(default=django.utils.timezone.now)),
                ('payment_confirmed', models.BooleanField(help_text='Payment confirmed by admin/organiser', default=False)),
                ('date_payment_confirmed', models.DateTimeField(null=True, blank=True)),
                ('date_space_confirmed', models.DateTimeField(null=True, blank=True)),
                ('block', models.ForeignKey(to='booking.Block', related_name='bookings', null=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, primary_key=True, auto_created=True)),
                ('name', models.CharField(max_length=255)),
                ('type', models.CharField(max_length=2, default='PC', choices=[('PC', 'Pole level class'), ('WS', 'Workshop'), ('CL', 'Other class'), ('EV', 'Other event')])),
                ('description', models.TextField(blank=True)),
                ('date', models.DateTimeField()),
                ('location', models.CharField(max_length=255, default='Watermelon Studio')),
                ('max_participants', models.PositiveIntegerField(help_text='Leave blank if no max number of participants', null=True, blank=True)),
                ('contact_person', models.CharField(max_length=255, default='Gwen Burns')),
                ('contact_email', models.EmailField(max_length=75, default='thewatermelonstudio@hotmail.com')),
                ('cost', models.DecimalField(default=0, max_digits=8, decimal_places=2)),
                ('advance_payment_required', models.BooleanField(default=False)),
                ('booking_open', models.BooleanField(default=True)),
                ('payment_open', models.BooleanField(default=False)),
                ('payment_info', models.TextField(blank=True)),
                ('payment_link', models.URLField(default='http://www.paypal.co.uk', blank=True)),
                ('payment_due_date', models.DateTimeField(null=True, blank=True)),
                ('cancellation_period', models.PositiveIntegerField(default=24)),
                ('slug', django_extensions.db.fields.AutoSlugField(editable=False, unique=True, max_length=40, blank=True, populate_from='name')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.AddField(
            model_name='booking',
            name='event',
            field=models.ForeignKey(to='booking.Event', related_name='bookings'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='booking',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, related_name='bookings'),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='booking',
            unique_together=set([('user', 'event')]),
        ),
        migrations.AddField(
            model_name='block',
            name='block_type',
            field=models.ForeignKey(to='booking.BlockType', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='block',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, related_name='blocks'),
            preserve_default=True,
        ),
    ]
