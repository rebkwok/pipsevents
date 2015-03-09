# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django_extensions.db.fields
import django.utils.timezone
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Block',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False, auto_created=True, verbose_name='ID')),
                ('block_size', models.CharField(default='SM', max_length=2, verbose_name='Number of classes in block', choices=[('SM', '5'), ('LG', '10')])),
                ('start_date', models.DateTimeField(default=django.utils.timezone.now)),
                ('paid', models.BooleanField(default=False, verbose_name='Payment made (as confirmed by participant)', help_text='Payment has been made by user')),
                ('payment_confirmed', models.BooleanField(default=False, help_text='Payment confirmed by admin/organiser')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, related_name='blocks')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Booking',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False, auto_created=True, verbose_name='ID')),
                ('paid', models.BooleanField(default=False, verbose_name='Payment made (as confirmed by participant)', help_text='Payment has been made by user')),
                ('date_booked', models.DateTimeField(default=django.utils.timezone.now)),
                ('payment_confirmed', models.BooleanField(default=False, help_text='Payment confirmed by admin/organiser')),
                ('date_payment_confirmed', models.DateTimeField(blank=True, null=True)),
                ('date_space_confirmed', models.DateTimeField(blank=True, null=True)),
                ('block', models.ForeignKey(related_name='bookings', to='booking.Block', null=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False, auto_created=True, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('type', models.CharField(default='PC', max_length=2, choices=[('PC', 'Pole level class'), ('WS', 'Workshop'), ('CL', 'Other class'), ('EV', 'Other event')])),
                ('description', models.TextField(blank=True)),
                ('date', models.DateTimeField()),
                ('location', models.CharField(default='Watermelon Studio', max_length=255)),
                ('max_participants', models.PositiveIntegerField(blank=True, help_text='Leave blank if no max number of participants', null=True)),
                ('contact_person', models.CharField(default='Gwen Burns', max_length=255)),
                ('contact_email', models.EmailField(default='thewatermelonstudio@hotmail.com', max_length=75)),
                ('cost', models.DecimalField(default=0, max_digits=8, decimal_places=2)),
                ('advance_payment_required', models.BooleanField(default=False)),
                ('booking_open', models.BooleanField(default=True)),
                ('payment_open', models.BooleanField(default=False)),
                ('payment_info', models.TextField(blank=True)),
                ('payment_link', models.URLField(default='http://www.paypal.co.uk', blank=True)),
                ('payment_due_date', models.DateTimeField(blank=True, null=True)),
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
    ]
