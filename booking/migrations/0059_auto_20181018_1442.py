# Generated by Django 2.0.3 on 2018-10-18 13:42

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0058_auto_20180722_1210'),
    ]

    operations = [
        migrations.AddField(
            model_name='usedblockvoucher',
            name='block_id',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='usedeventvoucher',
            name='booking_id',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AlterField(
            model_name='basevoucher',
            name='discount',
            field=models.PositiveIntegerField(help_text='Enter a number between 1 and 100'),
        ),
    ]
