# Generated by Django 2.2.6 on 2019-11-15 19:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0062_data_migration_warning_dates_sent'),
    ]

    operations = [
        migrations.AddField(
            model_name='basevoucher',
            name='activated',
            field=models.BooleanField(default=True),
        ),
    ]
