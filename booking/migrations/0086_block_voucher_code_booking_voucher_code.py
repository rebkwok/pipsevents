# Generated by Django 4.1.1 on 2023-09-10 15:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0085_alter_blocktype_paypal_email_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='block',
            name='voucher_code',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='booking',
            name='voucher_code',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
