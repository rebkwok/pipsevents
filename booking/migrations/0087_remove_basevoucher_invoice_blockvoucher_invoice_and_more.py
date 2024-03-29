# Generated by Django 4.1.1 on 2023-09-11 10:17

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('stripe_payments', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('booking', '0086_block_voucher_code_booking_voucher_code'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='basevoucher',
            name='invoice',
        ),
        migrations.AddField(
            model_name='blockvoucher',
            name='invoice',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='block_gift_vouchers', to='stripe_payments.invoice'),
        ),
        migrations.AddField(
            model_name='eventvoucher',
            name='invoice',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='event_gift_vouchers', to='stripe_payments.invoice'),
        ),
        migrations.AlterField(
            model_name='ticketbooking',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ticket_bookings', to=settings.AUTH_USER_MODEL),
        ),
    ]
