# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0004_auto_20150330_2033'),
    ]

    operations = [
        migrations.AlterField(
            model_name='block',
            name='block_type',
            field=models.ForeignKey(to='booking.BlockType'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='blocktype',
            name='event_type',
            field=models.ForeignKey(to='booking.EventType'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='event',
            name='description',
            field=models.TextField(null=True, blank=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='event',
            name='event_type',
            field=models.ForeignKey(to='booking.EventType'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='eventtype',
            name='subtype',
            field=models.CharField(help_text='Type of class/event. Use this to categorise events/classes.  If an event can be block booked, this should match the event type used in the Block Type.', max_length=255),
            preserve_default=True,
        ),
    ]
