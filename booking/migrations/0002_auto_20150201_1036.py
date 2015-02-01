# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
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
                ('block_size', models.CharField(default=b'SM', max_length=2, verbose_name=b'Number of classes in block', choices=[(b'SM', b'Five classes'), (b'LG', b'Ten classes')])),
                ('start_date', models.DateTimeField(auto_now_add=True)),
                ('paid', models.BooleanField(default=False, help_text=b'Payment has been made by user', verbose_name=b'Payment made (as confirmed by participant)')),
                ('payment_confirmed', models.BooleanField(default=False, help_text=b'Payment confirmed by admin/organiser')),
                ('user', models.ForeignKey(related_name='blocks', to=settings.AUTH_USER_MODEL)),
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
            model_name='event',
            name='advance_payment_required',
            field=models.BooleanField(default=False),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='event',
            name='payment_link',
            field=models.URLField(default=b'http://www.paypal.co.uk', blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='event',
            name='type',
            field=models.CharField(default=b'PC', max_length=2, choices=[(b'PC', b'Pole level class'), (b'WS', b'Workshop'), (b'CL', b'Other class'), (b'EV', b'Other event')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='booking',
            name='paid',
            field=models.BooleanField(default=False, help_text=b'Payment has been made by user', verbose_name=b'Payment made (as confirmed by participant)'),
            preserve_default=True,
        ),
    ]
