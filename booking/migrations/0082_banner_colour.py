# Generated by Django 4.1.1 on 2023-07-04 22:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0081_banner'),
    ]

    operations = [
        migrations.AddField(
            model_name='banner',
            name='colour',
            field=models.CharField(choices=[('info', 'light blue'), ('primary', 'blue'), ('success', 'green'), ('warning', 'yellow'), ('danger', 'red'), ('secondary', 'light grey'), ('dark', 'dark grey')], default='info', max_length=10),
        ),
    ]
