# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0032_remove_ticketbooking_quantity'),
    ]

    operations = [
        migrations.RenameField(
            model_name='ticket',
            old_name='extra_info',
            new_name='extra_ticket_info',
        ),
        migrations.RenameField(
            model_name='ticket',
            old_name='extra_info1',
            new_name='extra_ticket_info1',
        ),
        migrations.RemoveField(
            model_name='ticket',
            name='extra_info1_label',
        ),
        migrations.RemoveField(
            model_name='ticket',
            name='extra_info_label',
        ),
        migrations.AddField(
            model_name='ticketedevent',
            name='extra_ticket_info1_label',
            field=models.CharField(max_length=255, blank=True, default=''),
        ),
        migrations.AddField(
            model_name='ticketedevent',
            name='extra_ticket_info_label',
            field=models.CharField(max_length=255, blank=True, default=''),
        ),
    ]
