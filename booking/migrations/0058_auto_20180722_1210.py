# Generated by Django 2.0.3 on 2018-07-22 11:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0057_block_paypal_pending'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='contact_person',
            field=models.CharField(default='Gwen Holbrey', max_length=255),
        ),
    ]
