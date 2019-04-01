# Generated by Django 2.1.2 on 2019-03-24 20:07

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_archiveddisclaimer'),
    ]

    operations = [
        migrations.AddField(
            model_name='nonregistereddisclaimer',
            name='user_uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
