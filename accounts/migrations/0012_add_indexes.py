# Generated by Django 2.2.6 on 2019-12-05 10:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_auto_20190816_1701'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='onlinedisclaimer',
            index=models.Index(fields=['user'], name='accounts_on_user_id_03aad6_idx'),
        ),
    ]
