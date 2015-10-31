# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.utils.timezone
import django_extensions.db.fields
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('booking', '0028_event_cancelled'),
    ]

    operations = [
        migrations.CreateModel(
            name='Ticket',
            fields=[
                ('id', models.AutoField(serialize=False, verbose_name='ID', primary_key=True, auto_created=True)),
                ('extra_ticket_info', models.TextField(default='', blank=True)),
                ('extra_ticket_info1', models.TextField(default='', blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='TicketBooking',
            fields=[
                ('id', models.AutoField(serialize=False, verbose_name='ID', primary_key=True, auto_created=True)),
                ('date_booked', models.DateTimeField(default=django.utils.timezone.now)),
                ('date_rebooked', models.DateTimeField(null=True, blank=True)),
                ('paid', models.BooleanField(default=False)),
                ('payment_confirmed', models.BooleanField(help_text='Payment confirmed by admin/organiser', default=False)),
                ('date_payment_confirmed', models.DateTimeField(null=True, blank=True)),
                ('cancelled', models.BooleanField(default=False)),
                ('reminder_sent', models.BooleanField(default=False)),
                ('warning_sent', models.BooleanField(default=False)),
                ('booking_reference', models.CharField(max_length=255)),
            ],
        ),
        migrations.CreateModel(
            name='TicketedEvent',
            fields=[
                ('id', models.AutoField(serialize=False, verbose_name='ID', primary_key=True, auto_created=True)),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(default='', blank=True)),
                ('date', models.DateTimeField()),
                ('location', models.CharField(max_length=255, default='Watermelon Studio')),
                ('max_tickets', models.PositiveIntegerField(help_text='Leave blank if no max number', null=True, blank=True)),
                ('contact_person', models.CharField(max_length=255, default='Gwen Burns')),
                ('contact_email', models.EmailField(max_length=254, default='thewatermelonstudio@hotmail.com')),
                ('ticket_cost', models.DecimalField(default=0, decimal_places=2, max_digits=8)),
                ('advance_payment_required', models.BooleanField(default=True)),
                ('show_on_site', models.BooleanField(help_text='Tick to show on the site', default=True)),
                ('payment_open', models.BooleanField(default=True)),
                ('payment_info', models.TextField(blank=True)),
                ('payment_due_date', models.DateTimeField(help_text='Tickets that are not paid by the payment due date will be automatically cancelled (a warning email will be sent to users first).', null=True, blank=True)),
                ('payment_time_allowed', models.PositiveIntegerField(help_text='Number of hours allowed for payment after booking (after this ticket purchases will be cancelled.  This will be ignored if there is a payment due date set on the event itself. ', null=True, blank=True)),
                ('email_studio_when_purchased', models.BooleanField(default=False)),
                ('max_ticket_purchase', models.PositiveIntegerField(help_text='Limit the number of tickets that can be purchased at one time', null=True, blank=True)),
                ('extra_ticket_info_label', models.CharField(max_length=255, default='', blank=True)),
                ('extra_ticket_info_help', models.CharField(help_text='Description/details/help text to display under the extra info field', max_length=255, default='', blank=True)),
                ('extra_ticket_info_required', models.BooleanField(help_text='Tick if this information is mandatory when booking tickets', default=False)),
                ('extra_ticket_info1_label', models.CharField(max_length=255, default='', blank=True)),
                ('extra_ticket_info1_help', models.CharField(help_text='Description/details/help text to display under the extra info field', max_length=255, default='', blank=True)),
                ('extra_ticket_info1_required', models.BooleanField(help_text='Tick if this information is mandatory when booking tickets', default=False)),
                ('slug', django_extensions.db.fields.AutoSlugField(max_length=40, unique=True, populate_from='name', blank=True, editable=False)),
            ],
            options={
                'ordering': ['-date'],
            },
        ),
        migrations.AddField(
            model_name='ticketbooking',
            name='ticketed_event',
            field=models.ForeignKey(related_name='ticket_bookings', to='booking.TicketedEvent'),
        ),
        migrations.AddField(
            model_name='ticketbooking',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='ticket',
            name='ticket_booking',
            field=models.ForeignKey(related_name='tickets', to='booking.TicketBooking'),
        ),
    ]
