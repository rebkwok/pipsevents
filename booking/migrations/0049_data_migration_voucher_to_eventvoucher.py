# -*- coding: utf-8 -*-
# Generated by Django 1.9.1 on 2016-07-07 17:40
from __future__ import unicode_literals

from django.db import migrations


def create_event_vouchers(apps, schema_editor):
    Voucher = apps.get_model('booking', 'Voucher')
    EventVoucher = apps.get_model('booking', 'EventVoucher')
    UsedEventVoucher = apps.get_model('booking', 'UsedEventVoucher')

    for voucher in Voucher.objects.all():
        ev = EventVoucher.objects.create(
            code=voucher.code, discount=voucher.discount,
            start_date=voucher.start_date, expiry_date=voucher.expiry_date,
            max_vouchers=voucher.max_vouchers,
            max_per_user=1
        )
        for event_type in voucher.event_types.all():
            ev.event_types.add(event_type)
        for user in voucher.users.all():
            UsedEventVoucher.objects.create(voucher=ev, user=user)



class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0048_auto_20160705_1938'),
    ]

    operations = [
        migrations.RunPython(
            create_event_vouchers, reverse_code=migrations.RunPython.noop
        )
    ]
