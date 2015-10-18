# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0034_ticketbooking_booking_reference'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticketedevent',
            name='extra_ticket_info1_help',
            field=models.CharField(max_length=255, blank=True, default='', help_text='Description/details/help text to display under the extra info field'),
        ),
        migrations.AddField(
            model_name='ticketedevent',
            name='extra_ticket_info_help',
            field=models.CharField(max_length=255, blank=True, default='', help_text='Description/details/help text to display under the extra info field'),
        ),
        migrations.AlterField(
            model_name='ticketedevent',
            name='max_ticket_purchase',
            field=models.PositiveIntegerField(null=True, blank=True, help_text='Limit the number of tickets that can be purchased at one time'),
        ),
        migrations.AlterField(
            model_name='ticketedevent',
            name='payment_time_allowed',
            field=models.PositiveIntegerField(null=True, blank=True, help_text='Number of hours allowed for payment after booking (after this ticket purchases will be cancelled.  This will be ignored if there is a payment due date set on the event itself. '),
        ),
    ]
