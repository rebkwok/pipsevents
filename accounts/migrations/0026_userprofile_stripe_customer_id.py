# Generated by Django 4.1.1 on 2024-05-19 08:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0025_archiveddisclaimer_pronouns'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='stripe_customer_id',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
    ]
