# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0028_auto_20151014_1355'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticket',
            name='extra_info1',
            field=models.TextField(default='', blank=True),
        ),
        migrations.AddField(
            model_name='ticket',
            name='extra_info1_label',
            field=models.CharField(max_length=255, default='', blank=True),
        ),
        migrations.AddField(
            model_name='ticket',
            name='extra_info_label',
            field=models.CharField(max_length=255, default='', blank=True),
        ),
        migrations.AddField(
            model_name='ticketbooking',
            name='date_booked',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name='ticketbooking',
            name='date_payment_confirmed',
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='ticketbooking',
            name='paid',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='ticketbooking',
            name='payment_confirmed',
            field=models.BooleanField(help_text='Payment confirmed by admin/organiser', default=False),
        ),
        migrations.AddField(
            model_name='ticketbooking',
            name='reminder_sent',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='ticketbooking',
            name='warning_sent',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='ticketedevent',
            name='max_ticket_purchase',
            field=models.PositiveIntegerField(help_text='Limit the number of tickets that can be purchased at one time', null=True),
        ),
        migrations.AddField(
            model_name='ticketedevent',
            name='payment_time_allowed',
            field=models.PositiveIntegerField(help_text='Number of days allowed for payment after booking (after this ticket purchases will be cancelled.  This will be ignored if there is a payment due date set on the event itself. ', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='ticket',
            name='extra_info',
            field=models.TextField(default='', blank=True),
        ),
    ]
