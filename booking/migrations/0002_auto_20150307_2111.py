# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django_extensions.db.fields
import django.utils.timezone
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('booking', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Block',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('block_size', models.CharField(verbose_name='Number of classes in block', default='SM', max_length=2, choices=[('SM', '5'), ('LG', '10')])),
                ('start_date', models.DateTimeField(default=django.utils.timezone.now)),
                ('paid', models.BooleanField(verbose_name='Payment made (as confirmed by participant)', help_text='Payment has been made by user', default=False)),
                ('payment_confirmed', models.BooleanField(help_text='Payment confirmed by admin/organiser', default=False)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, related_name='blocks')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.AddField(
            model_name='booking',
            name='block',
            field=models.ForeignKey(related_name='bookings', to='booking.Block', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='booking',
            name='date_booked',
            field=models.DateTimeField(default=django.utils.timezone.now),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='booking',
            name='date_payment_confirmed',
            field=models.DateTimeField(blank=True, null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='booking',
            name='date_space_confirmed',
            field=models.DateTimeField(blank=True, null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='event',
            name='advance_payment_required',
            field=models.BooleanField(default=False),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='event',
            name='booking_open',
            field=models.BooleanField(default=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='event',
            name='payment_link',
            field=models.URLField(blank=True, default='http://www.paypal.co.uk'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='event',
            name='type',
            field=models.CharField(default='PC', max_length=2, choices=[('PC', 'Pole level class'), ('WS', 'Workshop'), ('CL', 'Other class'), ('EV', 'Other event')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='booking',
            name='paid',
            field=models.BooleanField(verbose_name='Payment made (as confirmed by participant)', help_text='Payment has been made by user', default=False),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='booking',
            name='payment_confirmed',
            field=models.BooleanField(help_text='Payment confirmed by admin/organiser', default=False),
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
            name='cost',
            field=models.DecimalField(verbose_name='Cost (GBP)', default=0, max_digits=8, decimal_places=2),
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
            field=models.PositiveIntegerField(blank=True, help_text='Leave blank if no max number of participants', null=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='event',
            name='slug',
            field=django_extensions.db.fields.AutoSlugField(blank=True, max_length=40, editable=False, unique=True, populate_from='name'),
            preserve_default=True,
        ),
    ]
