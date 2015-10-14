# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings
import django_extensions.db.fields


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('booking', '0027_booking_date_rebooked'),
    ]

    operations = [
        migrations.CreateModel(
            name='Ticket',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False, verbose_name='ID', auto_created=True)),
                ('extra_info', models.TextField(blank=True, max_length=255)),
            ],
        ),
        migrations.CreateModel(
            name='TicketBooking',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False, verbose_name='ID', auto_created=True)),
                ('quantity', models.PositiveIntegerField(default=1)),
            ],
        ),
        migrations.CreateModel(
            name='TicketedEvent',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False, verbose_name='ID', auto_created=True)),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True, default='')),
                ('date', models.DateTimeField()),
                ('location', models.CharField(default='Watermelon Studio', max_length=255)),
                ('max_tickets', models.PositiveIntegerField(null=True, blank=True, help_text='Leave blank if no max number')),
                ('contact_person', models.CharField(default='Gwen Burns', max_length=255)),
                ('contact_email', models.EmailField(default='thewatermelonstudio@hotmail.com', max_length=254)),
                ('ticket_cost', models.DecimalField(default=0, max_digits=8, decimal_places=2)),
                ('advance_payment_required', models.BooleanField(default=True)),
                ('show_on_site', models.BooleanField(default=True, help_text='Tick to show on the site')),
                ('payment_open', models.BooleanField(default=True)),
                ('payment_info', models.TextField(blank=True)),
                ('payment_due_date', models.DateTimeField(null=True, blank=True, help_text='Tickets that are not paid by the payment due date will be automatically cancelled (a warning email will be sent to users first).')),
                ('email_studio_when_purchased', models.BooleanField(default=False)),
                ('slug', django_extensions.db.fields.AutoSlugField(editable=False, unique=True, populate_from='name', blank=True, max_length=40)),
            ],
            options={
                'ordering': ['-date'],
            },
        ),
        migrations.AddField(
            model_name='ticketbooking',
            name='event',
            field=models.ForeignKey(to='booking.TicketedEvent', related_name='ticket_bookings'),
        ),
        migrations.AddField(
            model_name='ticketbooking',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='ticket',
            name='ticket_booking',
            field=models.ForeignKey(to='booking.TicketBooking', related_name='tickets'),
        ),
    ]
