# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='EventType',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False, verbose_name='ID', auto_created=True)),
                ('type', models.CharField(choices=[('CL', 'Class'), ('EV', 'Event')], help_text="This determines whether events of thistype are listed on the 'Classes' or 'Events' page", max_length=2)),
                ('subtype', models.CharField(help_text='Type of class/event. Use this to categorise events/classes, especiallyfor use with block bookings.', max_length=255)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.AddField(
            model_name='blocktype',
            name='eventtype',
            field=models.ForeignKey(null=True, to='booking.EventType'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='event',
            name='eventtype',
            field=models.ForeignKey(null=True, to='booking.EventType'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='blocktype',
            name='event_type',
            field=models.CharField(choices=[('EV', 'Other event'), ('CL', 'Other class'), ('PC', 'Pole level class'), ('WS', 'Workshop')], default='PC', max_length=2),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='event',
            name='payment_link',
            field=models.URLField(default='https://www.paypal.com/uk/webapps/mpp/send-money-online', blank=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='event',
            name='type',
            field=models.CharField(choices=[('EV', 'Other event'), ('CL', 'Other class'), ('PC', 'Pole level class'), ('WS', 'Workshop')], default='PC', max_length=2),
            preserve_default=True,
        ),
    ]
