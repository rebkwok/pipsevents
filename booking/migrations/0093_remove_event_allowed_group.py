# Generated by Django 4.1.1 on 2023-12-29 12:07

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0092_alter_allowedgroup_options_alter_eventtype_options_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='event',
            name='allowed_group',
        ),
    ]
