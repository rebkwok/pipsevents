# Generated by Django 2.2.6 on 2019-11-23 08:00

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0063_basevoucher_activated'),
    ]

    operations = [
        migrations.AddField(
            model_name='basevoucher',
            name='is_gift_voucher',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='basevoucher',
            name='message',
            field=models.TextField(blank=True, help_text='Message (max 500 characters)', max_length=500, null=True),
        ),
        migrations.AddField(
            model_name='basevoucher',
            name='name',
            field=models.CharField(blank=True, help_text='Name of recipient', max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='basevoucher',
            name='purchaser_email',
            field=models.EmailField(blank=True, max_length=254, null=True),
        ),
        migrations.CreateModel(
            name='GiftVoucherType',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('block_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='block_gift_vouchers', to='booking.BlockType')),
                ('event_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='event_gift_vouchers', to='booking.EventType')),
            ],
        ),
    ]