# Generated by Django 3.2.11 on 2022-06-14 18:50

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0020_auto_20210909_1222'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='nonregistereddisclaimer',
            options={'verbose_name': 'event disclaimer'},
        ),
    ]